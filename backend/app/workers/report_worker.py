"""Report Worker — Daily AI summary reports."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.workers.report_worker.generate_daily_summary")
def generate_daily_summary():
    return run_async(_generate_daily_summary_async())


async def _generate_daily_summary_async():
    from app.db.base import AsyncSessionLocal
    from app.models import Tenant, Alert, IdsAlert, SyntheticResult, AnomalyEvent
    from app.ai.engine import ai_engine
    from sqlalchemy import select, func
    from app.core.config import settings

    yesterday = datetime.now(timezone.utc) - timedelta(hours=24)

    async with AsyncSessionLocal() as db:
        tenants = (await db.execute(select(Tenant).where(Tenant.status == "active"))).scalars().all()

        for tenant in tenants:
            # Gather stats
            alerts_count = (await db.execute(
                select(func.count()).where(Alert.tenant_id == tenant.id, Alert.triggered_at >= yesterday)
            )).scalar()

            critical_alerts = (await db.execute(
                select(func.count()).where(Alert.tenant_id == tenant.id,
                                           Alert.severity == "critical", Alert.triggered_at >= yesterday)
            )).scalar()

            ids_alerts = (await db.execute(
                select(func.count()).where(IdsAlert.tenant_id == tenant.id, IdsAlert.timestamp >= yesterday)
            )).scalar()

            anomalies = (await db.execute(
                select(func.count()).where(AnomalyEvent.tenant_id == tenant.id, AnomalyEvent.timestamp >= yesterday)
            )).scalar()

            synthetics_down = (await db.execute(
                select(func.count()).where(SyntheticResult.tenant_id == tenant.id,
                                           SyntheticResult.status == "down",
                                           SyntheticResult.timestamp >= yesterday)
            )).scalar()

            summary_data = {
                "tenant": tenant.name,
                "period": "últimas 24 horas",
                "alerts_total": alerts_count,
                "critical_alerts": critical_alerts,
                "ids_alerts": ids_alerts,
                "anomalies": anomalies,
                "synthetic_failures": synthetics_down,
            }

            if settings.OPENAI_API_KEY or settings.ANTHROPIC_API_KEY or settings.GEMINI_API_KEY:
                import json
                system = "You are a monitoring AI. Write a brief daily operations summary in pt-BR."
                user = f"Daily summary data:\n{json.dumps(summary_data, indent=2)}\nWrite a concise report for ops team (3-5 sentences)."
                ai_summary = await ai_engine.complete(system, user, max_tokens=400)
                logger.info(f"Daily summary for {tenant.name}:\n{ai_summary}")

    return {"generated": len(tenants)}
