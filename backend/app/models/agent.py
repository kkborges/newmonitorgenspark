from sqlalchemy import Column, String, Boolean, JSON, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from app.db.base import Base


class AgentToken(Base):
    __tablename__ = "agent_tokens"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    token = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255))
    description = Column(Text)
    role = Column(String(30), default="agent")   # agent|gateway|ids|otel|apm
    active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True))
    last_used = Column(DateTime(timezone=True))
    used_count = Column(Integer, default=0)
    bound_host_id = Column(String(36), ForeignKey("hosts.id"), nullable=True)
    bound_ip = Column(String(50))

    # Config to embed into installer script
    install_config = Column(JSON, default=dict)

    tenant = relationship("Tenant", foreign_keys=[tenant_id])


# Fix Integer import
from sqlalchemy import Integer
AgentToken.used_count = Column(Integer, default=0)
