from sqlalchemy import Column, String, Float, Integer, Boolean, JSON, ForeignKey, DateTime, Text
from app.db.base import Base


class Task(Base):
    __tablename__ = "tasks"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)   # network_scan|vuln_scan|ids_scan|agent_deploy|backup|report|etc.
    status = Column(String(20), default="pending")  # pending|running|completed|failed|cancelled
    priority = Column(String(10), default="medium")
    target = Column(String(500))
    description = Column(Text)

    progress = Column(Float, default=0.0)
    result = Column(JSON, default=dict)
    error = Column(Text)

    scheduled_at = Column(DateTime(timezone=True))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    recurrence = Column(String(100))   # cron expression

    celery_task_id = Column(String(255))
    created_by = Column(String(36), ForeignKey("users.id"))

    logs = Column(JSON, default=list)  # [{ts, msg, level}]
