"""
Alert Worker — Evaluates alert rules and dispatches notifications.
"""
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


@celery_app.task(name="app.workers.alert_worker.evaluate_alert_rules")
def evaluate_alert_rules():
    """Evaluate all enabled alert rules against current metrics."""
    return run_async(_evaluate_rules_async())


async def _evaluate_rules_async():
    from app.db.base import AsyncSessionLocal
    from app.models import AlertRule, Alert, Host, HostMetric
    from sqlalchemy import select
    import uuid

    now = datetime.now(timezone.utc)
    triggered = 0

    async with AsyncSessionLocal() as db:
        rules_result = await db.execute(
            select(AlertRule).where(AlertRule.enabled == True)
        )
        rules = rules_result.scalars().all()

        for rule in rules:
            try:
                # Get relevant hosts
                hosts_q = select(Host).where(Host.tenant_id == rule.tenant_id)
                if rule.entity_ids:
                    hosts_q = hosts_q.where(Host.id.in_(rule.entity_ids))
                hosts_result = await db.execute(hosts_q)
                hosts = hosts_result.scalars().all()

                for host in hosts:
                    # Get latest metric
                    metric_result = await db.execute(
                        select(HostMetric).where(
                            HostMetric.host_id == host.id,
                            HostMetric.timestamp >= now - timedelta(minutes=5)
                        ).order_by(HostMetric.timestamp.desc()).limit(1)
                    )
                    latest = metric_result.scalar_one_or_none()
                    if not latest:
                        continue

                    observed = getattr(latest, rule.metric, None)
                    if observed is None:
                        continue

                    # Check condition
                    violated = _check_condition(observed, rule.condition_op, rule.threshold_value)
                    if not violated:
                        continue

                    # Check cooldown — avoid duplicate alerts
                    recent_alert = await db.execute(
                        select(Alert).where(
                            Alert.rule_id == rule.id,
                            Alert.entity_id == host.id,
                            Alert.status == "active",
                            Alert.triggered_at >= now - timedelta(seconds=rule.suppress_seconds or 300)
                        )
                    )
                    if recent_alert.scalar_one_or_none():
                        continue  # Still in cooldown

                    # Create alert
                    alert = Alert(
                        id=str(uuid.uuid4()),
                        tenant_id=rule.tenant_id,
                        rule_id=rule.id,
                        name=rule.name,
                        description=rule.description or f"{rule.metric} {rule.condition_op} {rule.threshold_value}",
                        severity=rule.severity,
                        entity_type=rule.entity_type,
                        entity_id=host.id,
                        entity_name=host.hostname,
                        metric=rule.metric,
                        observed_value=observed,
                        threshold_value=rule.threshold_value,
                        condition_op=rule.condition_op,
                        status="active",
                        triggered_at=now,
                    )
                    db.add(alert)
                    triggered += 1

                    # Dispatch notifications
                    if rule.channels:
                        await db.flush()
                        dispatch_alert_notifications.apply_async(args=[alert.id], countdown=1)

            except Exception as e:
                logger.error(f"Error evaluating rule {rule.id}: {e}")

        await db.commit()
    return {"triggered": triggered}


@celery_app.task(name="app.workers.alert_worker.dispatch_alert_notifications")
def dispatch_alert_notifications(alert_id: str):
    """Send alert notifications to all configured channels."""
    return run_async(_dispatch_notifications_async(alert_id))


async def _dispatch_notifications_async(alert_id: str):
    from app.db.base import AsyncSessionLocal
    from app.models import Alert, AlertRule, NotificationChannel, NotificationLog
    from app.services.notification_service import NotificationService
    from sqlalchemy import select
    import uuid

    async with AsyncSessionLocal() as db:
        alert_result = await db.execute(select(Alert).where(Alert.id == alert_id))
        alert = alert_result.scalar_one_or_none()
        if not alert:
            return

        # Get channels from rule
        channel_ids = []
        if alert.rule_id:
            rule_result = await db.execute(select(AlertRule).where(AlertRule.id == alert.rule_id))
            rule = rule_result.scalar_one_or_none()
            if rule:
                channel_ids = rule.channels or []

        for channel_id in channel_ids:
            ch_result = await db.execute(
                select(NotificationChannel).where(NotificationChannel.id == channel_id)
            )
            channel = ch_result.scalar_one_or_none()
            if not channel or not channel.enabled:
                continue

            log = NotificationLog(
                id=str(uuid.uuid4()),
                tenant_id=alert.tenant_id,
                channel_id=channel.id,
                alert_id=alert.id,
                sent_at=datetime.now(timezone.utc),
            )

            try:
                svc = NotificationService(channel)
                await svc.send_alert(alert)
                log.status = "sent"
                channel.last_used = datetime.now(timezone.utc)
                channel.last_status = "ok"
            except Exception as e:
                log.status = "failed"
                log.error_message = str(e)
                channel.last_status = "error"

            db.add(log)

        await db.commit()


def _check_condition(value: float, op: str, threshold: float) -> bool:
    try:
        ops = {
            "gt": value > threshold, "gte": value >= threshold,
            "lt": value < threshold, "lte": value <= threshold,
            "eq": value == threshold, "ne": value != threshold,
        }
        return ops.get(op, False)
    except Exception:
        return False
