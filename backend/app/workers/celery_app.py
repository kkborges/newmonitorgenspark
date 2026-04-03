"""
Nexus Platform — Celery Application
Workers para: AI analysis, baselines, alertas, testes sintéticos, coleta de métricas
"""
from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "nexus",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.baseline_worker",
        "app.workers.ai_worker",
        "app.workers.alert_worker",
        "app.workers.synthetic_worker",
        "app.workers.collector_worker",
        "app.workers.security_worker",
        "app.workers.extension_worker",
        "app.workers.report_worker",
    ]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.ai_worker.*": {"queue": "ai"},
        "app.workers.synthetic_worker.*": {"queue": "synthetic"},
        "app.workers.security_worker.*": {"queue": "security"},
        "app.workers.collector_worker.*": {"queue": "collector"},
        "app.workers.baseline_worker.*": {"queue": "baseline"},
        "app.workers.alert_worker.*": {"queue": "alerts"},
    },
)

# ─── Periodic tasks (beat) ────────────────────────────────────────────────────
celery_app.conf.beat_schedule = {
    # Baseline update every 5 minutes
    "update-baselines": {
        "task": "app.workers.baseline_worker.update_all_baselines",
        "schedule": 300,   # seconds
    },
    # AI anomaly analysis every 5 minutes
    "ai-anomaly-analysis": {
        "task": "app.workers.ai_worker.analyze_anomalies",
        "schedule": 300,
    },
    # AI security log analysis every 2 minutes
    "ai-security-analysis": {
        "task": "app.workers.security_worker.analyze_security_logs",
        "schedule": 120,
    },
    # Alert evaluation every 30 seconds
    "evaluate-alerts": {
        "task": "app.workers.alert_worker.evaluate_alert_rules",
        "schedule": 30,
    },
    # Synthetic tests dispatcher every minute
    "run-synthetic-tests": {
        "task": "app.workers.synthetic_worker.dispatch_due_tests",
        "schedule": 60,
    },
    # Cloud metrics collection every 5 minutes
    "collect-cloud-metrics": {
        "task": "app.workers.collector_worker.collect_cloud_metrics",
        "schedule": 300,
    },
    # K8s metrics collection every minute
    "collect-k8s-metrics": {
        "task": "app.workers.collector_worker.collect_k8s_metrics",
        "schedule": 60,
    },
    # Extension metrics collection every 5 minutes
    "collect-extension-metrics": {
        "task": "app.workers.extension_worker.collect_all",
        "schedule": 300,
    },
    # Network SNMP poll every minute
    "snmp-poll": {
        "task": "app.workers.collector_worker.snmp_poll_all",
        "schedule": 60,
    },
    # Daily AI summary report
    "daily-ai-report": {
        "task": "app.workers.report_worker.generate_daily_summary",
        "schedule": crontab(hour=7, minute=0),  # 7am UTC
    },
    # Clean old metrics every 6 hours (keep 90 days)
    "cleanup-old-metrics": {
        "task": "app.workers.baseline_worker.cleanup_old_data",
        "schedule": crontab(minute=0, hour="*/6"),
    },
}
