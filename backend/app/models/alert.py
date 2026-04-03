from sqlalchemy import Column, String, Float, Integer, Boolean, JSON, ForeignKey, DateTime, Text
from app.db.base import Base


class AlertRule(Base):
    __tablename__ = "alert_rules"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    enabled = Column(Boolean, default=True)

    # Target
    entity_type = Column(String(30), default="host")
    entity_ids = Column(JSON, default=list)  # empty = all entities of type
    tags_filter = Column(JSON, default=list)

    # Condition
    metric = Column(String(100), nullable=False)
    condition_op = Column(String(10), nullable=False)   # gt|lt|gte|lte|eq|ne
    threshold_value = Column(Float, nullable=False)
    duration_seconds = Column(Integer, default=60)

    # Use AI baseline instead of fixed threshold
    use_baseline = Column(Boolean, default=False)
    baseline_sensitivity = Column(Float, default=3.0)  # sigma deviation

    severity = Column(String(20), default="medium")
    channels = Column(JSON, default=list)  # channel IDs
    suppress_seconds = Column(Integer, default=300)   # cooldown
    created_by = Column(String(36), ForeignKey("users.id"))


class Alert(Base):
    __tablename__ = "alerts"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    rule_id = Column(String(36), ForeignKey("alert_rules.id"), nullable=True)
    anomaly_id = Column(String(36), ForeignKey("anomaly_events.id"), nullable=True)

    name = Column(String(255), nullable=False)
    description = Column(Text)
    severity = Column(String(20), default="medium")  # critical|high|medium|low|info

    entity_type = Column(String(30))
    entity_id = Column(String(36), index=True)
    entity_name = Column(String(255))

    metric = Column(String(100))
    observed_value = Column(Float)
    threshold_value = Column(Float)
    condition_op = Column(String(10))

    status = Column(String(20), default="active")  # active|acknowledged|resolved
    triggered_at = Column(DateTime(timezone=True), nullable=False, index=True)
    acknowledged_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))
    acknowledged_by = Column(String(36), ForeignKey("users.id"))
    trigger_count = Column(Integer, default=1)

    # AI analysis (from anomaly or auto-generated)
    ai_summary = Column(Text)
    ai_root_cause = Column(Text)
    ai_recommendation = Column(Text)

    # Notification tracking
    notifications_sent = Column(JSON, default=list)
