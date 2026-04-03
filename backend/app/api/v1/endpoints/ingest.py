"""
Ingest API — Receives data from agents, gateways, OTel SDK and APM.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timezone
from app.db.base import get_db
from app.models import AgentToken, Host, HostMetric, IdsAlert, LogEntry, OtelTrace, OtelSpan, OtelMetric
from sqlalchemy import select
import uuid

router = APIRouter(prefix="/ingest", tags=["ingest"])


async def verify_agent_token(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> AgentToken:
    """Verify Bearer token and return AgentToken record."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token required")

    token_str = authorization.replace("Bearer ", "").strip()
    result = await db.execute(
        select(AgentToken).where(
            AgentToken.token == token_str,
            AgentToken.active == True
        )
    )
    token = result.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=401, detail="Invalid or revoked token")

    # Update last_used
    token.last_used = datetime.now(timezone.utc)
    await db.commit()
    return token


# ── Heartbeat & Metrics ────────────────────────────────────────────────────────

class HeartbeatPayload(BaseModel):
    hostname: str
    ip: Optional[str] = None
    os: Optional[str] = None
    os_version: Optional[str] = None
    kernel: Optional[str] = None
    arch: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    agent_version: Optional[str] = None
    uptime: Optional[int] = None
    cpu_cores: Optional[int] = None
    memory_total_mb: Optional[int] = None
    disk_total_gb: Optional[float] = None
    metrics: Optional[Dict[str, Any]] = None


@router.post("/agent/heartbeat")
async def agent_heartbeat(
    payload: HeartbeatPayload,
    agent_token: AgentToken = Depends(verify_agent_token),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    # Find or auto-register host
    host_result = await db.execute(
        select(Host).where(
            Host.tenant_id == agent_token.tenant_id,
            Host.hostname == payload.hostname,
        )
    )
    host = host_result.scalar_one_or_none()

    if not host:
        # Auto-register new host
        host = Host(
            id=str(uuid.uuid4()),
            tenant_id=agent_token.tenant_id,
            hostname=payload.hostname,
            ip=payload.ip,
            os=payload.os,
            os_version=payload.os_version,
            kernel=payload.kernel,
            arch=payload.arch,
            manufacturer=payload.manufacturer,
            model=payload.model,
            agent_version=payload.agent_version,
            agent_token_id=agent_token.id,
            monitoring_mode="infra+otel",
        )
        db.add(host)
        agent_token.bound_host_id = host.id

    # Update host
    host.status = "online"
    host.last_seen = now
    if payload.ip:
        host.ip = payload.ip
    if payload.agent_version:
        host.agent_version = payload.agent_version
    if payload.uptime:
        host.uptime = payload.uptime
    if payload.cpu_cores:
        host.cpu_cores = payload.cpu_cores

    # Update metrics snapshot
    metrics = payload.metrics or {}
    host.cpu_usage = metrics.get("cpuUsage", host.cpu_usage)
    host.memory_usage = metrics.get("memoryUsage", host.memory_usage)
    host.disk_usage = metrics.get("diskUsage", host.disk_usage)
    host.load_avg_1 = metrics.get("loadAvg1", host.load_avg_1)
    host.load_avg_5 = metrics.get("loadAvg5", host.load_avg_5)
    host.load_avg_15 = metrics.get("loadAvg15", host.load_avg_15)

    # Store time-series metric point
    if metrics:
        metric = HostMetric(
            id=str(uuid.uuid4()),
            host_id=host.id,
            tenant_id=agent_token.tenant_id,
            timestamp=now,
            cpu_usage=metrics.get("cpuUsage"),
            memory_usage=metrics.get("memoryUsage"),
            disk_usage=metrics.get("diskUsage"),
            load_avg_1=metrics.get("loadAvg1"),
            load_avg_5=metrics.get("loadAvg5"),
            load_avg_15=metrics.get("loadAvg15"),
            net_rx_bytes=metrics.get("netRxBytes"),
            net_tx_bytes=metrics.get("netTxBytes"),
            disk_read_bytes=metrics.get("diskReadBytes"),
            disk_write_bytes=metrics.get("diskWriteBytes"),
            processes_total=metrics.get("processesTotal"),
            processes_running=metrics.get("processesRunning"),
        )
        db.add(metric)

    await db.commit()
    return {"status": "ok", "host_id": host.id, "interval": 60}


@router.get("/agent/ping")
async def agent_ping(agent_token: AgentToken = Depends(verify_agent_token)):
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ── IDS Alerts ─────────────────────────────────────────────────────────────────

class IdsAlertPayload(BaseModel):
    alerts: List[Dict[str, Any]]


@router.post("/ids")
async def ingest_ids_alerts(
    payload: IdsAlertPayload,
    agent_token: AgentToken = Depends(verify_agent_token),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    created = 0

    for alert_data in payload.alerts:
        host_id = agent_token.bound_host_id

        alert = IdsAlert(
            id=str(uuid.uuid4()),
            tenant_id=agent_token.tenant_id,
            host_id=host_id,
            timestamp=now,
            severity=alert_data.get("severity", "medium"),
            attack_type=alert_data.get("attackType", "unknown"),
            category=alert_data.get("category"),
            source_ip=alert_data.get("sourceIp"),
            source_port=alert_data.get("sourcePort"),
            source_country=alert_data.get("sourceCountry"),
            dest_ip=alert_data.get("destIp"),
            dest_port=alert_data.get("destPort"),
            protocol=alert_data.get("protocol"),
            attempts=alert_data.get("attempts", 1),
            rule_id=alert_data.get("ruleId"),
            rule_name=alert_data.get("ruleName"),
            raw_log=alert_data.get("rawLog"),
            status="open",
        )
        db.add(alert)
        created += 1

    await db.commit()

    # Dispatch AI analysis for high-severity alerts
    if created > 0:
        from app.workers.security_worker import analyze_security_logs
        analyze_security_logs.apply_async(countdown=5)

    return {"status": "ok", "ingested": created}


# ── Logs ───────────────────────────────────────────────────────────────────────

class LogsPayload(BaseModel):
    logs: List[Dict[str, Any]]


@router.post("/logs")
async def ingest_logs(
    payload: LogsPayload,
    agent_token: AgentToken = Depends(verify_agent_token),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    created = 0

    for log_data in payload.logs:
        log = LogEntry(
            id=str(uuid.uuid4()),
            tenant_id=agent_token.tenant_id,
            host_id=agent_token.bound_host_id,
            timestamp=log_data.get("timestamp") or now,
            level=log_data.get("level", "info"),
            source=log_data.get("source"),
            group=log_data.get("group", "general"),
            host_name=log_data.get("hostname"),
            host_ip=log_data.get("ip"),
            message=log_data.get("message", ""),
            raw=log_data.get("raw"),
            trace_id=log_data.get("traceId"),
            service=log_data.get("service"),
            parsed_fields=log_data.get("fields", {}),
        )
        db.add(log)
        created += 1

    await db.commit()
    return {"status": "ok", "ingested": created}


# ── OTel / APM ─────────────────────────────────────────────────────────────────

@router.post("/otel/traces")
async def ingest_otel_traces(
    request: Request,
    agent_token: AgentToken = Depends(verify_agent_token),
    db: AsyncSession = Depends(get_db),
):
    """Accepts OTLP JSON trace data."""
    data = await request.json()
    resource_spans = data.get("resourceSpans", [])
    created = 0

    for rs in resource_spans:
        resource = rs.get("resource", {})
        resource_attrs = {a["key"]: a.get("value", {}) for a in resource.get("attributes", [])}
        service_name = resource_attrs.get("service.name", {}).get("stringValue", "unknown")

        for scope_span in rs.get("scopeSpans", []):
            for span in scope_span.get("spans", []):
                trace_id = span.get("traceId", "")
                span_id = span.get("spanId", "")
                parent_id = span.get("parentSpanId")
                name = span.get("name", "")
                start_ns = int(span.get("startTimeUnixNano", 0))
                end_ns = int(span.get("endTimeUnixNano", 0))
                status = span.get("status", {})
                attrs = {a["key"]: a.get("value", {}) for a in span.get("attributes", [])}

                start_dt = datetime.fromtimestamp(start_ns / 1e9, tz=timezone.utc)
                end_dt = datetime.fromtimestamp(end_ns / 1e9, tz=timezone.utc) if end_ns else None
                duration_ms = (end_ns - start_ns) / 1e6 if end_ns else None

                http_method = attrs.get("http.method", {}).get("stringValue")
                http_url = attrs.get("http.url", attrs.get("http.target", {})).get("stringValue")
                http_status = attrs.get("http.status_code", {}).get("intValue")

                is_root = not parent_id

                if is_root:
                    trace_obj = OtelTrace(
                        id=str(uuid.uuid4()),
                        tenant_id=agent_token.tenant_id,
                        trace_id=trace_id,
                        span_id=span_id,
                        parent_span_id=parent_id,
                        name=name,
                        service=service_name,
                        start_time=start_dt,
                        end_time=end_dt,
                        duration_ms=duration_ms,
                        status="error" if status.get("code") == 2 else "ok",
                        status_code=status.get("code"),
                        method=http_method,
                        url=http_url,
                        response_code=http_status,
                        attributes=attrs,
                        events=span.get("events", []),
                        resource=resource_attrs,
                        error_count=1 if status.get("code") == 2 else 0,
                    )
                    db.add(trace_obj)

                    # Trigger AI analysis for errors
                    if status.get("code") == 2:
                        from app.workers.ai_worker import analyze_trace_error
                        analyze_trace_error.apply_async(
                            args=[trace_id, agent_token.tenant_id],
                            countdown=10
                        )
                else:
                    span_obj = OtelSpan(
                        id=str(uuid.uuid4()),
                        trace_id=trace_id,
                        tenant_id=agent_token.tenant_id,
                        span_id=span_id,
                        parent_span_id=parent_id,
                        name=name,
                        service=service_name,
                        start_time=start_dt,
                        end_time=end_dt,
                        duration_ms=duration_ms,
                        status="error" if status.get("code") == 2 else "ok",
                        attributes=attrs,
                        events=span.get("events", []),
                    )
                    db.add(span_obj)

                created += 1

    await db.commit()
    return {"status": "ok", "spans_ingested": created}


@router.post("/otel/metrics")
async def ingest_otel_metrics(
    request: Request,
    agent_token: AgentToken = Depends(verify_agent_token),
    db: AsyncSession = Depends(get_db),
):
    data = await request.json()
    resource_metrics = data.get("resourceMetrics", [])
    created = 0

    for rm in resource_metrics:
        resource = rm.get("resource", {})
        resource_attrs = {a["key"]: a.get("value", {}) for a in resource.get("attributes", [])}
        service_name = resource_attrs.get("service.name", {}).get("stringValue", "unknown")

        for scope_metric in rm.get("scopeMetrics", []):
            for metric in scope_metric.get("metrics", []):
                metric_name = metric.get("name")
                unit = metric.get("unit")

                data_points = (
                    metric.get("gauge", {}).get("dataPoints", []) or
                    metric.get("sum", {}).get("dataPoints", []) or
                    metric.get("histogram", {}).get("dataPoints", [])
                )

                for dp in data_points:
                    ts_ns = int(dp.get("timeUnixNano", 0))
                    ts = datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc) if ts_ns else datetime.now(timezone.utc)
                    value = dp.get("asDouble") or dp.get("asInt") or dp.get("sum")
                    labels = {a["key"]: list(a.get("value", {}).values())[0] for a in dp.get("attributes", [])}

                    m = OtelMetric(
                        id=str(uuid.uuid4()),
                        tenant_id=agent_token.tenant_id,
                        service=service_name,
                        timestamp=ts,
                        metric_name=metric_name,
                        metric_type="gauge" if "gauge" in metric else "counter" if "sum" in metric else "histogram",
                        value=float(value) if value is not None else None,
                        unit=unit,
                        labels=labels,
                    )
                    db.add(m)
                    created += 1

    await db.commit()
    return {"status": "ok", "metrics_ingested": created}
