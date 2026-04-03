from sqlalchemy import Column, String, Boolean, JSON, ForeignKey, DateTime, Text, Integer
from app.db.base import Base


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    type = Column(String(30), nullable=False)  # email|slack|teams|telegram|discord|webhook|pagerduty|opsgenie|whatsapp
    enabled = Column(Boolean, default=True)
    config = Column(JSON, default=dict)   # channel-specific config (encrypted)
    last_used = Column(DateTime(timezone=True))
    last_status = Column(String(20), default="unknown")


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    channel_id = Column(String(36), ForeignKey("notification_channels.id"), nullable=False)
    alert_id = Column(String(36), ForeignKey("alerts.id"), nullable=True)
    sent_at = Column(DateTime(timezone=True))
    status = Column(String(20))   # sent|failed|retry
    attempts = Column(Integer, default=1)
    error_message = Column(Text)
    payload = Column(JSON, default=dict)
