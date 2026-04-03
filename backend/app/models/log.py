from sqlalchemy import Column, String, Integer, Boolean, JSON, ForeignKey, DateTime, Text
from app.db.base import Base


class LogEntry(Base):
    __tablename__ = "log_entries"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    host_id = Column(String(36), ForeignKey("hosts.id"), nullable=True, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    level = Column(String(20), nullable=False, index=True)   # debug|info|warn|error|critical
    source = Column(String(100))       # nginx|syslog|auth|app|custom
    group = Column(String(50))         # network_assets|workstations|syslog_servers|app_logs|etc.
    host_name = Column(String(255))
    host_ip = Column(String(50))
    message = Column(Text, nullable=False)
    raw = Column(Text)
    trace_id = Column(String(100), index=True)
    span_id = Column(String(50))
    service = Column(String(100))
    parsed_fields = Column(JSON, default=dict)

    # AI Security Analysis flag
    security_analysed = Column(Boolean, default=False)
    security_score = Column(Integer, default=0)  # 0-100
    security_tags = Column(JSON, default=list)
