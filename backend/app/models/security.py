from sqlalchemy import Column, String, Float, Integer, Boolean, JSON, ForeignKey, DateTime, Text
from app.db.base import Base


class IdsAlert(Base):
    __tablename__ = "ids_alerts"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    host_id = Column(String(36), ForeignKey("hosts.id"), nullable=True, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    severity = Column(String(20), nullable=False)   # critical|high|medium|low|info
    attack_type = Column(String(255), nullable=False)
    category = Column(String(100))   # intrusion|malware|dos|recon|exploit|anomaly
    source_ip = Column(String(50))
    source_port = Column(Integer)
    source_country = Column(String(5))
    dest_ip = Column(String(50))
    dest_port = Column(Integer)
    protocol = Column(String(20))
    attempts = Column(Integer, default=1)
    rule_id = Column(String(50))
    rule_name = Column(String(255))
    signature = Column(Text)
    raw_log = Column(Text)
    status = Column(String(20), default="open")  # open|acknowledged|resolved|false_positive

    # AI Analysis
    ai_summary = Column(Text)
    ai_threat_level = Column(String(20))
    ai_recommendation = Column(Text)
    ai_ioc = Column(JSON, default=list)    # indicators of compromise
    ai_ttps = Column(JSON, default=list)   # MITRE ATT&CK TTPs
    ai_analysed = Column(Boolean, default=False)

    # Geolocation
    geo_lat = Column(Float)
    geo_lon = Column(Float)
    geo_city = Column(String(100))
    geo_org = Column(String(255))


class SecurityEvent(Base):
    """
    Generic security events from custom log sources,
    network assets (firewall logs, switch ACL, etc.)
    """
    __tablename__ = "security_events"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    source_type = Column(String(50))   # firewall|switch|router|custom|syslog|netflow
    source_id = Column(String(36))     # network_asset.id or custom source id
    source_name = Column(String(255))
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    event_type = Column(String(100))
    severity = Column(String(20), default="medium")
    message = Column(Text, nullable=False)
    raw_log = Column(Text)
    parsed_fields = Column(JSON, default=dict)

    # Extracted IOC
    src_ip = Column(String(50))
    dst_ip = Column(String(50))
    src_port = Column(Integer)
    dst_port = Column(Integer)
    protocol = Column(String(20))
    action = Column(String(30))   # allow|deny|drop|reject|log

    # AI Analysis
    ai_analysed = Column(Boolean, default=False)
    ai_summary = Column(Text)
    ai_threat_level = Column(String(20))
    ai_is_anomaly = Column(Boolean, default=False)

    status = Column(String(20), default="new")
