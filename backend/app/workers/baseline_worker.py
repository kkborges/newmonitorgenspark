"""
Baseline Worker — Computes rolling statistical baselines for all monitored metrics.
Runs every 5 minutes via Celery Beat.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import numpy as np
from sqlalchemy import select, func, text
from app.workers.celery_app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run async coroutine from sync Celery task."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="app.workers.baseline_worker.update_all_baselines",
                 max_retries=3, default_retry_delay=60)
def update_all_baselines(self):
    """Update statistical baselines for all active tenants and their entities."""
    return run_async(_update_all_baselines_async())


async def _update_all_baselines_async():
    from app.db.base import AsyncSessionLocal
    from app.models import Host, NetworkAsset, MetricBaseline
    from app.ai.engine import ai_engine

    async with AsyncSessionLocal() as db:
        # Get all active hosts
        hosts_result = await db.execute(
            select(Host).where(Host.status != "offline")
        )
        hosts = hosts_result.scalars().all()

        updated = 0
        for host in hosts:
            metrics_to_baseline = [
                "cpu_usage", "memory_usage", "disk_usage",
                "load_avg_1", "load_avg_5",
                "net_rx_bytes", "net_tx_bytes",
                "disk_read_bytes", "disk_write_bytes",
            ]
            for metric in metrics_to_baseline:
                try:
                    await _compute_baseline(db, "host", host.id, host.tenant_id, metric)
                    updated += 1
                except Exception as e:
                    logger.warning(f"Baseline failed host {host.id}/{metric}: {e}")

        # Get all network assets
        assets_result = await db.execute(
            select(NetworkAsset).where(NetworkAsset.snmp_enabled == True)
        )
        assets = assets_result.scalars().all()

        for asset in assets:
            for metric in ["cpu_usage", "memory_usage", "bandwidth_in_mbps", "bandwidth_out_mbps"]:
                try:
                    await _compute_baseline(db, "network_asset", asset.id, asset.tenant_id, metric)
                    updated += 1
                except Exception as e:
                    logger.warning(f"Baseline failed asset {asset.id}/{metric}: {e}")

        await db.commit()
        logger.info(f"Baselines updated: {updated} entries")
        return {"updated": updated}


async def _compute_baseline(db, entity_type: str, entity_id: str,
                              tenant_id: str, metric_name: str):
    """Compute rolling 7-day statistical baseline for a single metric."""
    from app.models import MetricBaseline, HostMetric, NetworkMetric
    from sqlalchemy import select, func
    import numpy as np

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=settings.BASELINE_WINDOW_HOURS)

    # Query raw values from appropriate table
    if entity_type == "host":
        q = select(
            getattr(HostMetric, metric_name, None)
        ).where(
            HostMetric.host_id == entity_id,
            HostMetric.timestamp >= window_start
        ).where(getattr(HostMetric, metric_name, None) != None)
    else:
        q = select(
            getattr(NetworkMetric, metric_name, None)
        ).where(
            NetworkMetric.asset_id == entity_id,
            NetworkMetric.timestamp >= window_start
        ).where(getattr(NetworkMetric, metric_name, None) != None)

    if q is None:
        return

    result = await db.execute(q)
    values = [row[0] for row in result.fetchall() if row[0] is not None]

    if len(values) < 10:
        return   # not enough data

    arr = np.array(values, dtype=float)
    mean = float(np.mean(arr))
    std = float(np.std(arr))
    p50 = float(np.percentile(arr, 50))
    p75 = float(np.percentile(arr, 75))
    p90 = float(np.percentile(arr, 90))
    p95 = float(np.percentile(arr, 95))
    p99 = float(np.percentile(arr, 99))

    warn_threshold = mean + (1.5 * std)
    crit_threshold = mean + (settings.BASELINE_ANOMALY_STD * std)
    low_warn = mean - (1.5 * std)
    low_crit = mean - (settings.BASELINE_ANOMALY_STD * std)

    # Upsert baseline
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = pg_insert(MetricBaseline.__table__).values(
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        metric_name=metric_name,
        mean=mean,
        std_dev=std,
        p50=p50,
        p75=p75,
        p90=p90,
        p95=p95,
        p99=p99,
        min_val=float(np.min(arr)),
        max_val=float(np.max(arr)),
        sample_count=len(values),
        warn_threshold=warn_threshold,
        crit_threshold=crit_threshold,
        low_warn=max(0, low_warn),
        low_crit=max(0, low_crit),
        status="active",
        last_updated=now,
        window_start=window_start,
        window_end=now,
    ).on_conflict_do_update(
        index_elements=["entity_id", "metric_name"],
        set_={
            "mean": mean, "std_dev": std, "p50": p50, "p75": p75,
            "p90": p90, "p95": p95, "p99": p99,
            "min_val": float(np.min(arr)), "max_val": float(np.max(arr)),
            "sample_count": len(values),
            "warn_threshold": warn_threshold, "crit_threshold": crit_threshold,
            "low_warn": max(0, low_warn), "low_crit": max(0, low_crit),
            "status": "active", "last_updated": now,
        }
    )
    await db.execute(stmt)


@celery_app.task(name="app.workers.baseline_worker.cleanup_old_data")
def cleanup_old_data():
    """Remove metric data older than 90 days."""
    return run_async(_cleanup_async())


async def _cleanup_async():
    from app.db.base import AsyncSessionLocal
    from app.models import HostMetric, NetworkMetric, LogEntry, OtelTrace

    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    async with AsyncSessionLocal() as db:
        for model in [HostMetric, NetworkMetric, LogEntry, OtelTrace]:
            ts_col = getattr(model, "timestamp", getattr(model, "start_time", None))
            if ts_col is not None:
                await db.execute(
                    text(f"DELETE FROM {model.__tablename__} WHERE timestamp < :cutoff"),
                    {"cutoff": cutoff}
                )
        await db.commit()
    return {"cleaned_before": cutoff.isoformat()}
