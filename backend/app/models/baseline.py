from sqlalchemy import Column, String, Float, Integer, Boolean, JSON, ForeignKey, DateTime, Text, Enum
from sqlalchemy.orm import relationship
from app.db.base import Base
import enum


class BaselineStatus(str, enum.Enum):
    learning = "learning"      # collecting data (< 1 week)
    active = "active"          # baseline established
    degraded = "degraded"      # too many anomalies
    stale = "stale"            # not updated recently


class MetricBaseline(Base):
    """
    Statistical baseline per metric per host/asset.
    Updated by AI workers every 5 minutes.
    Used for honeycomb visualization (green/yellow/red).
    """
    __tablename__ = "metric_baselines"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    entity_type = Column(String(30), nullable=False)   # host|network_asset|service|k8s_pod
    entity_id = Column(String(36), nullable=False, index=True)
    metric_name = Column(String(100), nullable=False)

    # Statistical parameters (rolling 7-day window)
    mean = Column(Float)
    std_dev = Column(Float)
    p50 = Column(Float)
    p75 = Column(Float)
    p90 = Column(Float)
    p95 = Column(Float)
    p99 = Column(Float)
    min_val = Column(Float)
    max_val = Column(Float)
    sample_count = Column(Integer, default=0)

    # Dynamic thresholds (derived from baseline)
    warn_threshold = Column(Float)   # mean + 1.5 * std
    crit_threshold = Column(Float)   # mean + 3.0 * std
    low_warn = Column(Float)         # mean - 1.5 * std (for disk free, etc.)
    low_crit = Column(Float)

    # Status
    status = Column(Enum(BaselineStatus), default=BaselineStatus.learning)
    last_updated = Column(DateTime(timezone=True))
    window_start = Column(DateTime(timezone=True))
    window_end = Column(DateTime(timezone=True))

    # AI-generated description
    ai_description = Column(Text)


class AnomalyEvent(Base):
    """
    Anomaly detected by AI workers against baseline.
    """
    __tablename__ = "anomaly_events"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    entity_type = Column(String(30), nullable=False)
    entity_id = Column(String(36), nullable=False, index=True)
    metric_name = Column(String(100), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    observed_value = Column(Float, nullable=False)
    expected_mean = Column(Float)
    expected_std = Column(Float)
    deviation_sigma = Column(Float)   # how many std deviations

    severity = Column(String(20), default="medium")  # low|medium|high|critical
    status = Column(String(20), default="open")       # open|acknowledged|resolved

    # AI analysis
    ai_summary = Column(Text)
    ai_root_cause = Column(Text)
    ai_recommendation = Column(Text)
    ai_confidence = Column(Float)     # 0.0 – 1.0

    # Related alerts created
    alert_id = Column(String(36), ForeignKey("alerts.id"), nullable=True)

    ai_analysis_done = Column(Boolean, default=False)
    analysis_model = Column(String(50))
