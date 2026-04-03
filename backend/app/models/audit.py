from sqlalchemy import Column, String, JSON, ForeignKey, DateTime, Text
from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    username = Column(String(100))
    action = Column(String(100), nullable=False, index=True)  # create|update|delete|login|logout|etc.
    resource_type = Column(String(50))
    resource_id = Column(String(36))
    resource_name = Column(String(255))
    ip_address = Column(String(50))
    user_agent = Column(Text)
    before = Column(JSON)    # previous state
    after = Column(JSON)     # new state
    status = Column(String(20), default="success")  # success|failed
    message = Column(Text)
