"""
Extension Worker — Collects metrics from installed extensions (PostgreSQL, MySQL, etc.)
"""
import asyncio
import logging
from datetime import datetime, timezone
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.workers.extension_worker.collect_all", queue="collector")
def collect_all():
    return run_async(_collect_all_extensions_async())


async def _collect_all_extensions_async():
    from app.db.base import AsyncSessionLocal
    from app.models import ExtensionConfig, Extension
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        configs_result = await db.execute(
            select(ExtensionConfig, Extension).join(
                Extension, ExtensionConfig.extension_id == Extension.id
            ).where(ExtensionConfig.enabled == True)
        )
        configs = configs_result.fetchall()

        tasks = []
        for config, extension in configs:
            handler = _get_extension_handler(extension.slug)
            if handler:
                tasks.append(handler(config))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = sum(1 for r in results if isinstance(r, Exception))
        return {"collected": len(tasks) - errors, "errors": errors}


def _get_extension_handler(slug: str):
    handlers = {
        "postgresql": _collect_postgresql,
        "mysql": _collect_mysql,
        "mariadb": _collect_mysql,
        "sqlserver": _collect_sqlserver,
        "oracle": _collect_oracle,
        "redis": _collect_redis,
        "mongodb": _collect_mongodb,
        "elasticsearch": _collect_elasticsearch,
        "nginx": _collect_nginx,
        "apache": _collect_apache,
        "tomcat": _collect_tomcat,
    }
    return handlers.get(slug)


async def _collect_postgresql(config):
    """Collect PostgreSQL metrics via psycopg2."""
    import asyncpg
    cfg = config.config or {}
    conn = await asyncpg.connect(
        host=cfg.get("host", "localhost"),
        port=cfg.get("port", 5432),
        user=cfg.get("user", "postgres"),
        password=cfg.get("password", ""),
        database=cfg.get("database", "postgres"),
    )
    try:
        # Database size
        db_sizes = await conn.fetch(
            "SELECT datname, pg_database_size(datname) as size FROM pg_database WHERE datistemplate = false"
        )
        # Active connections
        active_conns = await conn.fetchval(
            "SELECT count(*) FROM pg_stat_activity WHERE state = 'active'"
        )
        # Longest running query
        longest = await conn.fetchval(
            "SELECT EXTRACT(EPOCH FROM max(now() - query_start)) FROM pg_stat_activity WHERE state = 'active'"
        )
        # Cache hit ratio
        cache_hit = await conn.fetchval("""
            SELECT round(
                sum(blks_hit) * 100.0 / nullif(sum(blks_hit + blks_read), 0), 2
            ) FROM pg_stat_database
        """)
        # Transactions per second (approximate)
        tps = await conn.fetchval(
            "SELECT sum(xact_commit + xact_rollback) FROM pg_stat_database"
        )

        metrics = {
            "active_connections": active_conns,
            "longest_query_s": longest or 0,
            "cache_hit_ratio": float(cache_hit or 0),
            "total_transactions": tps or 0,
            "databases": [{"name": r["datname"], "size_bytes": r["size"]} for r in db_sizes],
        }

        await _store_extension_metrics(config.id, config.tenant_id, "postgresql", metrics)
        return metrics
    finally:
        await conn.close()


async def _collect_mysql(config):
    """Collect MySQL/MariaDB metrics."""
    import aiomysql
    cfg = config.config or {}
    conn = await aiomysql.connect(
        host=cfg.get("host", "localhost"),
        port=cfg.get("port", 3306),
        user=cfg.get("user", "root"),
        password=cfg.get("password", ""),
        db=cfg.get("database", "information_schema"),
    )
    try:
        async with conn.cursor() as cur:
            await cur.execute("SHOW GLOBAL STATUS WHERE Variable_name IN ('Threads_connected','Queries','Uptime','Innodb_buffer_pool_read_requests','Innodb_buffer_pool_reads')")
            rows = await cur.fetchall()
            status = {r[0]: r[1] for r in rows}

        metrics = {
            "threads_connected": int(status.get("Threads_connected", 0)),
            "queries_total": int(status.get("Queries", 0)),
            "uptime_s": int(status.get("Uptime", 0)),
            "innodb_cache_hit_pct": round(
                100 * (1 - int(status.get("Innodb_buffer_pool_reads", 0)) /
                max(int(status.get("Innodb_buffer_pool_read_requests", 1)), 1)), 2
            ),
        }
        await _store_extension_metrics(config.id, config.tenant_id, "mysql", metrics)
        return metrics
    finally:
        conn.close()


async def _collect_sqlserver(config):
    """Collect SQL Server metrics."""
    try:
        import aioodbc
        cfg = config.config or {}
        dsn = (f"DRIVER={{ODBC Driver 17 for SQL Server}};"
               f"SERVER={cfg.get('host','localhost')},{cfg.get('port',1433)};"
               f"DATABASE={cfg.get('database','master')};"
               f"UID={cfg.get('user','sa')};PWD={cfg.get('password','')}")
        async with aioodbc.connect(dsn=dsn) as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT
                        (SELECT count(*) FROM sys.dm_exec_sessions WHERE is_user_process = 1) AS connections,
                        (SELECT cntr_value FROM sys.dm_os_performance_counters
                         WHERE counter_name = 'Batch Requests/sec' AND object_name LIKE '%SQL Statistics%') AS batch_req_s,
                        (SELECT cntr_value FROM sys.dm_os_performance_counters
                         WHERE counter_name = 'Buffer cache hit ratio' AND object_name LIKE '%Buffer Manager%') AS cache_hit
                """)
                row = await cur.fetchone()
                metrics = {
                    "connections": row[0] if row else 0,
                    "batch_requests_per_sec": row[1] if row else 0,
                    "buffer_cache_hit_pct": row[2] if row else 0,
                }
        await _store_extension_metrics(config.id, config.tenant_id, "sqlserver", metrics)
        return metrics
    except ImportError:
        return {"error": "aioodbc not installed"}


async def _collect_oracle(config):
    """Collect Oracle Database metrics."""
    try:
        import cx_Oracle
        cfg = config.config or {}
        dsn = cx_Oracle.makedsn(cfg.get("host"), cfg.get("port", 1521), service_name=cfg.get("service"))
        conn = cx_Oracle.connect(cfg.get("user"), cfg.get("password"), dsn)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT metric_name, value
            FROM v$sysmetric
            WHERE metric_name IN ('CPU Usage Per Sec','Database CPU Time Ratio',
                                  'User Transaction Per Sec','Physical Reads Per Sec')
            AND intsize_csec = (SELECT MAX(intsize_csec) FROM v$sysmetric)
        """)
        rows = cursor.fetchall()
        metrics = {row[0].lower().replace(" ", "_"): float(row[1]) for row in rows}
        conn.close()
        await _store_extension_metrics(config.id, config.tenant_id, "oracle", metrics)
        return metrics
    except ImportError:
        return {"error": "cx_Oracle not installed"}


async def _collect_redis(config):
    cfg = config.config or {}
    import redis.asyncio as aioredis
    r = await aioredis.from_url(f"redis://{cfg.get('host','localhost')}:{cfg.get('port',6379)}")
    info = await r.info()
    metrics = {
        "connected_clients": info.get("connected_clients", 0),
        "used_memory_bytes": info.get("used_memory", 0),
        "keyspace_hits": info.get("keyspace_hits", 0),
        "keyspace_misses": info.get("keyspace_misses", 0),
        "ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
    }
    await r.aclose()
    await _store_extension_metrics(config.id, config.tenant_id, "redis", metrics)
    return metrics


async def _collect_mongodb(config):
    cfg = config.config or {}
    from motor.motor_asyncio import AsyncIOMotorClient
    uri = f"mongodb://{cfg.get('user','')}:{cfg.get('password','')}@{cfg.get('host','localhost')}:{cfg.get('port',27017)}"
    client = AsyncIOMotorClient(uri)
    db = client.admin
    status = await db.command("serverStatus")
    metrics = {
        "connections_current": status.get("connections", {}).get("current", 0),
        "ops_insert": status.get("opcounters", {}).get("insert", 0),
        "ops_query": status.get("opcounters", {}).get("query", 0),
        "ops_update": status.get("opcounters", {}).get("update", 0),
        "ops_delete": status.get("opcounters", {}).get("delete", 0),
        "resident_memory_mb": status.get("mem", {}).get("resident", 0),
    }
    client.close()
    await _store_extension_metrics(config.id, config.tenant_id, "mongodb", metrics)
    return metrics


async def _collect_elasticsearch(config):
    cfg = config.config or {}
    import httpx
    base = f"http://{cfg.get('host','localhost')}:{cfg.get('port',9200)}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base}/_cluster/stats")
        data = resp.json()
    metrics = {
        "docs_count": data.get("indices", {}).get("docs", {}).get("count", 0),
        "store_size_bytes": data.get("indices", {}).get("store", {}).get("size_in_bytes", 0),
        "nodes_total": data.get("nodes", {}).get("count", {}).get("total", 0),
        "status": data.get("status", "unknown"),
    }
    await _store_extension_metrics(config.id, config.tenant_id, "elasticsearch", metrics)
    return metrics


async def _collect_nginx(config):
    cfg = config.config or {}
    import httpx
    stub_url = cfg.get("stub_status_url", "http://localhost/nginx_status")
    async with httpx.AsyncClient() as client:
        resp = await client.get(stub_url, timeout=5)
        text = resp.text
    # Parse nginx stub_status
    lines = text.strip().split("\n")
    metrics = {}
    for line in lines:
        if "Active connections" in line:
            metrics["active_connections"] = int(line.split()[-1])
        elif "Reading" in line:
            parts = line.split()
            metrics["reading"] = int(parts[1])
            metrics["writing"] = int(parts[3])
            metrics["waiting"] = int(parts[5])
    await _store_extension_metrics(config.id, config.tenant_id, "nginx", metrics)
    return metrics


async def _collect_apache(config):
    cfg = config.config or {}
    import httpx
    status_url = cfg.get("status_url", "http://localhost/server-status?auto")
    async with httpx.AsyncClient() as client:
        resp = await client.get(status_url, timeout=5)
        text = resp.text
    metrics = {}
    for line in text.split("\n"):
        if ": " in line:
            k, v = line.split(": ", 1)
            key = k.strip().lower().replace(" ", "_")
            try:
                metrics[key] = float(v.strip())
            except ValueError:
                metrics[key] = v.strip()
    await _store_extension_metrics(config.id, config.tenant_id, "apache", metrics)
    return metrics


async def _collect_tomcat(config):
    cfg = config.config or {}
    import httpx
    base = f"http://{cfg.get('host','localhost')}:{cfg.get('port',8080)}"
    user = cfg.get("user", "tomcat")
    password = cfg.get("password", "")
    async with httpx.AsyncClient(auth=(user, password)) as client:
        resp = await client.get(f"{base}/manager/status?XML=true", timeout=5)
    # Basic parse
    text = resp.text
    metrics = {"status": "ok" if resp.status_code == 200 else "error", "raw": text[:200]}
    await _store_extension_metrics(config.id, config.tenant_id, "tomcat", metrics)
    return metrics


async def _store_extension_metrics(config_id: str, tenant_id: str, ext_type: str, metrics: dict):
    """Store collected extension metrics to OtelMetric table."""
    from app.db.base import AsyncSessionLocal
    from app.models import OtelMetric, ExtensionConfig
    from sqlalchemy import select
    import uuid

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                metric = OtelMetric(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    service=ext_type,
                    timestamp=now,
                    metric_name=f"{ext_type}.{key}",
                    metric_type="gauge",
                    value=float(value),
                    labels={"extension_config_id": config_id, "source": ext_type},
                )
                db.add(metric)

        # Update last_check on config
        config = await db.get(ExtensionConfig, config_id)
        if config:
            config.last_check = now
            config.last_status = "ok"
            config.metrics_collected = (config.metrics_collected or 0) + len(metrics)

        await db.commit()
