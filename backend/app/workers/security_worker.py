"""
Security Worker — AI-powered analysis of IDS alerts, security events, and log anomalies.
Runs every 2 minutes.
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


@celery_app.task(bind=True, name="app.workers.security_worker.analyze_security_logs", max_retries=2)
def analyze_security_logs(self):
    """Analyze unprocessed IDS alerts and security events using AI."""
    return run_async(_analyze_security_async())


async def _analyze_security_async():
    from app.db.base import AsyncSessionLocal
    from app.models import IdsAlert, SecurityEvent, Host
    from app.ai.engine import ai_engine
    from sqlalchemy import select

    analysed_count = 0
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        # Process unanalyzed IDS alerts
        ids_result = await db.execute(
            select(IdsAlert).where(
                IdsAlert.ai_analysed == False,
                IdsAlert.severity.in_(["critical", "high", "medium"])
            ).limit(50)
        )
        ids_alerts = ids_result.scalars().all()

        for alert in ids_alerts:
            # Get host context if available
            host_info = {}
            if alert.host_id:
                host_result = await db.execute(
                    select(Host).where(Host.id == alert.host_id)
                )
                host = host_result.scalar_one_or_none()
                if host:
                    host_info = {
                        "hostname": host.hostname,
                        "os": host.os,
                        "environment": host.environment,
                        "ip": host.ip
                    }

            # Count similar events from same source IP (last 1h)
            similar_result = await db.execute(
                select(IdsAlert).where(
                    IdsAlert.source_ip == alert.source_ip,
                    IdsAlert.timestamp >= now - timedelta(hours=1)
                )
            )
            similar_count = len(similar_result.scalars().all())

            context = {
                "event_type": "ids_alert",
                "attack_type": alert.attack_type,
                "severity": alert.severity,
                "source_ip": alert.source_ip,
                "source_country": alert.source_country,
                "dest_ip": alert.dest_ip,
                "dest_port": alert.dest_port,
                "protocol": alert.protocol,
                "attempts": alert.attempts,
                "rule_name": alert.rule_name,
                "raw_log": alert.raw_log or "",
                "host_info": host_info,
                "similar_events_count": similar_count,
            }

            if settings.OPENAI_API_KEY or settings.ANTHROPIC_API_KEY or settings.GEMINI_API_KEY:
                ai_result = await ai_engine.analyze_security_event(context)
                alert.ai_summary = ai_result.get("summary", "")
                alert.ai_threat_level = ai_result.get("threat_level", "medium")
                alert.ai_recommendation = ai_result.get("recommendation", "")
                alert.ai_ioc = ai_result.get("ioc", [])
                alert.ai_ttps = ai_result.get("ttps", [])

            alert.ai_analysed = True
            analysed_count += 1

        # Process unanalyzed security events in batches
        events_result = await db.execute(
            select(SecurityEvent).where(
                SecurityEvent.ai_analysed == False,
            ).order_by(SecurityEvent.timestamp.desc()).limit(100)
        )
        events = events_result.scalars().all()

        if events and (settings.OPENAI_API_KEY or settings.ANTHROPIC_API_KEY or settings.GEMINI_API_KEY):
            # Group events by tenant and source for batch analysis
            tenant_events = {}
            for ev in events:
                key = ev.tenant_id
                if key not in tenant_events:
                    tenant_events[key] = []
                tenant_events[key].append({
                    "id": ev.id,
                    "type": ev.event_type,
                    "severity": ev.severity,
                    "src_ip": ev.src_ip,
                    "dst_ip": ev.dst_ip,
                    "action": ev.action,
                    "message": ev.message[:200],
                    "timestamp": ev.timestamp.isoformat() if ev.timestamp else None,
                })

            for tenant_id, t_events in tenant_events.items():
                context = {"tenant_id": tenant_id, "time_window": "last 2 minutes"}
                ai_result = await ai_engine.analyze_log_security(t_events, context)

                # Mark all as analysed
                for ev in events:
                    if ev.tenant_id == tenant_id:
                        ev.ai_analysed = True
                        ev.ai_is_anomaly = len(ai_result.get("anomalies", [])) > 0
                        if ev.ai_is_anomaly:
                            ev.ai_summary = ai_result.get("summary", "")
                        analysed_count += 1

        await db.commit()
        logger.info(f"Security analysis: {analysed_count} events analysed")
        return {"analysed": analysed_count}


@celery_app.task(name="app.workers.security_worker.analyze_custom_log_source")
def analyze_custom_log_source(source_id: str, tenant_id: str, logs: list):
    """
    Analyze logs from a custom source (firewall, switch, syslog, etc.)
    for intrusion attempts and anomalies.
    """
    return run_async(_analyze_custom_logs(source_id, tenant_id, logs))


async def _analyze_custom_logs(source_id: str, tenant_id: str, logs: list):
    from app.db.base import AsyncSessionLocal
    from app.models import SecurityEvent
    from app.ai.engine import ai_engine
    import uuid

    if not logs:
        return {"processed": 0}

    context = {
        "source_id": source_id,
        "tenant_id": tenant_id,
        "log_count": len(logs),
        "source_type": "custom"
    }

    ai_result = {}
    if settings.OPENAI_API_KEY or settings.ANTHROPIC_API_KEY or settings.GEMINI_API_KEY:
        ai_result = await ai_engine.analyze_log_security(logs, context)

    async with AsyncSessionLocal() as db:
        for anomaly in ai_result.get("anomalies", []):
            event = SecurityEvent(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                source_id=source_id,
                source_type="custom",
                timestamp=datetime.now(timezone.utc),
                event_type=anomaly.get("type", "anomaly"),
                severity=anomaly.get("severity", "medium"),
                message=anomaly.get("description", ""),
                ai_analysed=True,
                ai_summary=anomaly.get("description", ""),
                ai_threat_level=anomaly.get("severity", "medium"),
                ai_is_anomaly=True,
                status="new",
            )
            db.add(event)
        await db.commit()

    return {
        "processed": len(logs),
        "anomalies_found": len(ai_result.get("anomalies", [])),
        "overall_risk": ai_result.get("overall_risk", "low"),
        "summary": ai_result.get("summary", "")
    }
