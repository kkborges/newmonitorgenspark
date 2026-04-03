from sqlalchemy import Column, String, Boolean, JSON, ForeignKey, DateTime, Text, Integer
from app.db.base import Base


class Gateway(Base):
    __tablename__ = "gateways"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    type = Column(String(30), nullable=False)  # server|infra|network|logs|security|otel|proxy|apm
    host = Column(String(255))
    port = Column(Integer, default=8080)
    token = Column(String(255), unique=True, nullable=False, index=True)
    version = Column(String(30))
    status = Column(String(20), default="offline")  # online|offline|error|stale
    last_heartbeat = Column(DateTime(timezone=True))

    tls_enabled = Column(Boolean, default=False)
    compress_enabled = Column(Boolean, default=False)
    encrypt_enabled = Column(Boolean, default=False)

    config = Column(JSON, default=dict)
    tags = Column(JSON, default=list)
