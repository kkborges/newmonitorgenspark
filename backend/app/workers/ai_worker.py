"""
AI Worker — Autonomous anomaly detection and AI analysis.
Compares current metrics against baselines; generates alerts with AI insights.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
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


@celery_app.task(bind=True, name="app.workers.ai_worker.analyze_anomalies", max_retries=2)
def analyze_anomalies(self):
    """
    Main AI worker: compare latest metrics against baselines,
    detect anomalies > N sigma, create AnomalyEvents and Alerts.
    """
    return run_async(_analyze_anomalies_async())


async def _analyze_anomalies_async():
    from app.db.base import AsyncSessionLocal
    from app.models import Host, HostMetric, MetricBaseline, AnomalyEvent, Alert
    from app.ai.engine import ai_engine
    from sqlalchemy import select
    import uuid

    now = datetime.now(timezone.utc)
    last_check = now - timedelta(minutes=6)  # look at data from last 6 min
    anomalies_found = 0

    async with AsyncSessionLocal() as db:
        # Get latest metrics per host
        hosts_result = await db.execute(
            select(Host).where(Host.status.in_(["online", "warning", "critical"]))
        )
        hosts = hosts_result.scalars().all()

        for host in hosts:
            # Get latest metric snapshot
            latest_result = await db.execute(
                select(HostMetric).where(
                    HostMetric.host_id == host.id,
                    HostMetric.timestamp >= last_check
                ).order_by(HostMetric.timestamp.desc()).limit(1)
            )
            latest = latest_result.scalar_one_or_none()
            if not latest:
                continue

            # Get baselines for this host
            baselines_result = await db.execute(
                select(MetricBaseline).where(
                    MetricBaseline.entity_id == host.id,
                    MetricBaseline.entity_type == "host",
                    MetricBaseline.status == "active"
                )
            )
            baselines = {b.metric_name: b for b in baselines_result.scalars().all()}

            # Check each metric
            for metric_name, baseline in baselines.items():
                if not baseline.mean or not baseline.std_dev or baseline.std_dev == 0:
                    continue

                observed = getattr(latest, metric_name, None)
                if observed is None:
                    continue

                deviation = (observed - baseline.mean) / baseline.std_dev

                if abs(deviation) < settings.BASELINE_ANOMALY_STD:
                    continue  # within normal range

                # Anomaly detected!
                severity = "low"
                if abs(deviation) >= 5:
                    severity = "critical"
                elif abs(deviation) >= 4:
                    severity = "high"
                elif abs(deviation) >= 3:
                    severity = "medium"

                anomalies_found += 1

                # Build context for AI analysis
                context = {
                    "entity_type": "host",
                    "entity_name": host.hostname,
                    "entity_id": host.id,
                    "metric_name": metric_name,
                    "observed_value": observed,
                    "expected_mean": baseline.mean,
                    "expected_std": baseline.std_dev,
                    "deviation_sigma": deviation,
                    "timestamp": now.isoformat(),
                    "related_metrics": {
                        "cpu_usage": latest.cpu_usage,
                        "memory_usage": latest.memory_usage,
                        "disk_usage": latest.disk_usage,
                        "load_avg_1": latest.load_avg_1,
                    }
                }

                # AI analysis (only if provider is configured)
                ai_result = {}
                if settings.OPENAI_API_KEY or settings.ANTHROPIC_API_KEY or settings.GEMINI_API_KEY:
                    ai_result = await ai_engine.analyze_anomaly(context)

                # Create AnomalyEvent
                anomaly = AnomalyEvent(
                    id=str(uuid.uuid4()),
                    tenant_id=host.tenant_id,
                    entity_type="host",
                    entity_id=host.id,
                    metric_name=metric_name,
                    timestamp=now,
                    observed_value=observed,
                    expected_mean=baseline.mean,
                    expected_std=baseline.std_dev,
                    deviation_sigma=deviation,
                    severity=severity,
                    status="open",
                    ai_summary=ai_result.get("summary", ""),
                    ai_root_cause=ai_result.get("root_cause", ""),
                    ai_recommendation=ai_result.get("recommendation", ""),
                    ai_confidence=ai_result.get("confidence", 0.0),
                    ai_analysis_done=bool(ai_result),
                    analysis_model=settings.AI_PROVIDER if ai_result else None,
                )
                db.add(anomaly)

                # Create Alert
                alert = Alert(
                    id=str(uuid.uuid4()),
                    tenant_id=host.tenant_id,
                    anomaly_id=anomaly.id,
                    name=f"Anomalia: {metric_name} em {host.hostname}",
                    description=f"Desvio de {deviation:.1f}σ detectado (valor: {observed:.1f}, esperado: {baseline.mean:.1f}±{baseline.std_dev:.1f})",
                    severity=severity,
                    entity_type="host",
                    entity_id=host.id,
                    entity_name=host.hostname,
                    metric=metric_name,
                    observed_value=observed,
                    threshold_value=baseline.crit_threshold,
                    condition_op="gt",
                    status="active",
                    triggered_at=now,
                    trigger_count=1,
                    ai_summary=ai_result.get("summary", ""),
                    ai_root_cause=ai_result.get("root_cause", ""),
                    ai_recommendation=ai_result.get("recommendation", ""),
                )
                db.add(alert)

                # Update anomaly with alert ID
                anomaly.alert_id = alert.id

                # Dispatch notification async
                await _dispatch_alert_notifications.apply_async(
                    args=[alert.id],
                    countdown=2
                )

        await db.commit()
        logger.info(f"AI analysis complete: {anomalies_found} anomalies detected")
        return {"anomalies_found": anomalies_found}


@celery_app.task(name="app.workers.ai_worker.analyze_trace_error")
def analyze_trace_error(trace_id: str, tenant_id: str):
    """AI analysis for a specific OTel trace error."""
    return run_async(_analyze_trace_async(trace_id, tenant_id))


async def _analyze_trace_async(trace_id: str, tenant_id: str):
    from app.db.base import AsyncSessionLocal
    from app.models import OtelTrace, OtelSpan
    from app.ai.engine import ai_engine
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        trace_result = await db.execute(
            select(OtelTrace).where(
                OtelTrace.trace_id == trace_id,
                OtelTrace.tenant_id == tenant_id
            )
        )
        trace = trace_result.scalar_one_or_none()
        if not trace:
            return {"error": "trace not found"}

        spans_result = await db.execute(
            select(OtelSpan).where(OtelSpan.trace_id == trace_id).limit(50)
        )
        spans = spans_result.scalars().all()

        context = {
            "trace_id": trace.trace_id,
            "service": trace.service,
            "method": trace.method,
            "url": trace.url,
            "status": trace.status,
            "response_code": trace.response_code,
            "duration_ms": trace.duration_ms,
            "error_count": trace.error_count,
            "spans": [
                {
                    "name": s.name, "service": s.service,
                    "duration_ms": s.duration_ms, "status": s.status,
                    "events": s.events
                } for s in spans
            ],
            "attributes": trace.attributes,
            "events": trace.events,
        }

        ai_result = await ai_engine.analyze_trace(context)

        # Update trace record
        trace.ai_analysed = True
        trace.ai_summary = ai_result.get("summary", "")
        trace.ai_root_cause = ai_result.get("root_cause", "")
        trace.ai_recommendation = str(ai_result.get("solutions", []))
        trace.ai_severity = ai_result.get("confidence", "medium")

        await db.commit()
        return ai_result


# Forward reference fix
from app.workers.alert_worker import dispatch_alert_notifications as _dispatch_alert_notifications
