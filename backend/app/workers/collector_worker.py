"""
Collector Worker — Collects metrics from cloud providers (AWS, Azure, GCP),
Kubernetes, VMware and SNMP network assets.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from app.workers.celery_app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)


def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────── AWS ────────────────────────────────────────

@celery_app.task(name="app.workers.collector_worker.collect_cloud_metrics", queue="collector")
def collect_cloud_metrics():
    return run_async(_collect_cloud_metrics_async())


async def _collect_cloud_metrics_async():
    collected = {"aws": 0, "azure": 0, "gcp": 0}

    if settings.AWS_ACCESS_KEY_ID:
        try:
            collected["aws"] = await _collect_aws_metrics()
        except Exception as e:
            logger.error(f"AWS collection failed: {e}")

    if settings.AZURE_TENANT_ID and settings.AZURE_CLIENT_ID:
        try:
            collected["azure"] = await _collect_azure_metrics()
        except Exception as e:
            logger.error(f"Azure collection failed: {e}")

    if settings.GCP_PROJECT_ID:
        try:
            collected["gcp"] = await _collect_gcp_metrics()
        except Exception as e:
            logger.error(f"GCP collection failed: {e}")

    return collected


async def _collect_aws_metrics():
    """Collect EC2, RDS, ELB metrics from AWS CloudWatch."""
    import boto3
    from datetime import timedelta

    cw = boto3.client(
        "cloudwatch",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_DEFAULT_REGION,
    )
    ec2 = boto3.client(
        "ec2",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_DEFAULT_REGION,
    )

    # List EC2 instances
    instances_resp = ec2.describe_instances()
    now = datetime.now(timezone.utc)
    collected = 0

    for reservation in instances_resp.get("Reservations", []):
        for inst in reservation.get("Instances", []):
            inst_id = inst["InstanceId"]

            # CPU utilization
            resp = cw.get_metric_statistics(
                Namespace="AWS/EC2",
                MetricName="CPUUtilization",
                Dimensions=[{"Name": "InstanceId", "Value": inst_id}],
                StartTime=now - timedelta(minutes=5),
                EndTime=now,
                Period=300,
                Statistics=["Average"],
            )
            if resp.get("Datapoints"):
                cpu = resp["Datapoints"][0]["Average"]
                await _store_cloud_metric(inst_id, "aws_ec2", "cpu_usage", cpu)
                collected += 1

    return collected


async def _collect_azure_metrics():
    """Collect VM metrics from Azure Monitor."""
    from azure.identity import ClientSecretCredential
    from azure.monitor.query import MetricsQueryClient
    from azure.mgmt.compute import ComputeManagementClient

    credential = ClientSecretCredential(
        tenant_id=settings.AZURE_TENANT_ID,
        client_id=settings.AZURE_CLIENT_ID,
        client_secret=settings.AZURE_CLIENT_SECRET,
    )
    compute_client = ComputeManagementClient(credential, settings.AZURE_SUBSCRIPTION_ID)
    metrics_client = MetricsQueryClient(credential)

    now = datetime.now(timezone.utc)
    collected = 0

    for vm in compute_client.virtual_machines.list_all():
        resource_id = vm.id
        try:
            result = metrics_client.query_resource(
                resource_id,
                ["Percentage CPU"],
                timespan=(now - timedelta(minutes=5), now),
                granularity=timedelta(minutes=5),
            )
            for metric in result.metrics:
                for ts in metric.timeseries:
                    for data in ts.data:
                        if data.average is not None:
                            await _store_cloud_metric(vm.name, "azure_vm", "cpu_usage", data.average)
                            collected += 1
        except Exception:
            pass

    return collected


async def _collect_gcp_metrics():
    """Collect GCE instance metrics from Google Cloud Monitoring."""
    from google.cloud import monitoring_v3
    import google.auth

    client = monitoring_v3.MetricServiceClient()
    project_name = f"projects/{settings.GCP_PROJECT_ID}"
    now = datetime.now(timezone.utc)
    collected = 0

    interval = monitoring_v3.TimeInterval({
        "end_time": {"seconds": int(now.timestamp())},
        "start_time": {"seconds": int((now - timedelta(minutes=5)).timestamp())},
    })

    results = client.list_time_series(
        request={
            "name": project_name,
            "filter": 'metric.type = "compute.googleapis.com/instance/cpu/utilization"',
            "interval": interval,
            "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
        }
    )

    for ts in results:
        inst_id = ts.resource.labels.get("instance_id", "unknown")
        for point in ts.points:
            value = point.value.double_value * 100  # convert to percentage
            await _store_cloud_metric(inst_id, "gcp_gce", "cpu_usage", value)
            collected += 1

    return collected


async def _store_cloud_metric(entity_id: str, source: str, metric: str, value: float):
    """Store a collected cloud metric."""
    pass  # Will write to OtelMetric table with source labels


# ─────────────────────────────── Kubernetes ─────────────────────────────────

@celery_app.task(name="app.workers.collector_worker.collect_k8s_metrics", queue="collector")
def collect_k8s_metrics():
    return run_async(_collect_k8s_async())


async def _collect_k8s_async():
    from kubernetes import client as k8s_client, config as k8s_config

    try:
        if settings.K8S_IN_CLUSTER:
            k8s_config.load_incluster_config()
        elif settings.KUBECONFIG_PATH:
            k8s_config.load_kube_config(config_file=settings.KUBECONFIG_PATH)
        else:
            return {"error": "No K8s config"}

        v1 = k8s_client.CoreV1Api()
        apps_v1 = k8s_client.AppsV1Api()

        pods = v1.list_pod_for_all_namespaces(watch=False)
        nodes = v1.list_node()
        deployments = apps_v1.list_deployment_for_all_namespaces()

        return {
            "pods": len(pods.items),
            "nodes": len(nodes.items),
            "deployments": len(deployments.items)
        }
    except Exception as e:
        logger.error(f"K8s collection failed: {e}")
        return {"error": str(e)}


# ─────────────────────────────── SNMP ───────────────────────────────────────

@celery_app.task(name="app.workers.collector_worker.snmp_poll_all", queue="collector")
def snmp_poll_all():
    return run_async(_snmp_poll_all_async())


async def _snmp_poll_all_async():
    from app.db.base import AsyncSessionLocal
    from app.models import NetworkAsset
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        assets_result = await db.execute(
            select(NetworkAsset).where(NetworkAsset.snmp_enabled == True)
        )
        assets = assets_result.scalars().all()

        tasks = [_snmp_poll_asset(asset) for asset in assets]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {"polled": len(assets), "errors": sum(1 for r in results if isinstance(r, Exception))}


async def _snmp_poll_asset(asset):
    """Poll a single network asset via SNMP."""
    try:
        from pysnmp.hlapi.asyncio import SnmpEngine, CommunityData, UdpTransportTarget, \
            ContextData, ObjectType, ObjectIdentity, getCmd

        engine = SnmpEngine()
        target = await UdpTransportTarget.create((asset.ip, asset.snmp_port or 161), timeout=5, retries=1)

        # OIDs: sysUpTime, ifOperStatus table, etc.
        oids = [
            ("1.3.6.1.2.1.1.3.0", "sysUpTime"),  # uptime
            ("1.3.6.1.2.1.25.3.3.1.2.1", "hrProcessorLoad"),  # CPU
        ]

        results = {}
        for oid, name in oids:
            errorIndication, errorStatus, errorIndex, varBinds = await getCmd(
                engine, CommunityData(asset.snmp_community or "public"),
                target, ContextData(),
                ObjectType(ObjectIdentity(oid))
            )
            if not errorIndication and not errorStatus:
                for varBind in varBinds:
                    results[name] = int(varBind[1])

        return results
    except Exception as e:
        logger.debug(f"SNMP poll failed for {asset.ip}: {e}")
        raise
