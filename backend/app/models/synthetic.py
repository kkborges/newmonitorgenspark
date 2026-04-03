from sqlalchemy import Column, String, Float, Integer, Boolean, JSON, ForeignKey, DateTime, Text, Enum
from sqlalchemy.orm import relationship
from app.db.base import Base
import enum


class SyntheticType(str, enum.Enum):
    url_monitor = "url_monitor"           # simple HTTP check
    api_monitor = "api_monitor"           # API with assertions
    app_flow = "app_flow"                 # multi-step login/flow (Playwright)
    ssl_check = "ssl_check"              # SSL certificate validity
    dns_check = "dns_check"
    tcp_check = "tcp_check"
    icmp_ping = "icmp_ping"


class SyntheticTest(Base):
    __tablename__ = "synthetic_tests"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    type = Column(Enum(SyntheticType), nullable=False)
    enabled = Column(Boolean, default=True)

    # Target
    url = Column(String(2000))
    method = Column(String(10), default="GET")
    headers = Column(JSON, default=dict)
    body = Column(Text)
    auth_type = Column(String(20))   # none|basic|bearer|api_key
    auth_value = Column(Text)

    # Schedule
    interval_seconds = Column(Integer, default=60)
    timeout_seconds = Column(Integer, default=30)
    locations = Column(JSON, default=list)   # probe locations

    # Assertions (for api_monitor)
    assertions = Column(JSON, default=list)
    # Example assertions:
    # [{"type": "status_code", "operator": "eq", "value": 200},
    #  {"type": "body_contains", "operator": "contains", "value": "success"},
    #  {"type": "header", "name": "content-type", "operator": "contains", "value": "json"},
    #  {"type": "response_time", "operator": "lt", "value": 2000},
    #  {"type": "json_path", "path": "$.data.id", "operator": "exists"}]

    # SSL check config
    ssl_warn_days = Column(Integer, default=30)
    ssl_crit_days = Column(Integer, default=7)

    # Playwright flow (app_flow type)
    playwright_script = Column(Text)     # JS Playwright script
    flow_steps = Column(JSON, default=list)   # visual step builder

    # Status
    last_check = Column(DateTime(timezone=True))
    last_status = Column(String(20), default="unknown")   # up|down|degraded|unknown
    last_response_ms = Column(Float)
    uptime_pct = Column(Float, default=100.0)
    avg_response_ms = Column(Float)

    # Alerting
    alert_on_failure = Column(Boolean, default=True)
    alert_channel_ids = Column(JSON, default=list)
    consecutive_failures_threshold = Column(Integer, default=2)


class SyntheticResult(Base):
    __tablename__ = "synthetic_results"

    test_id = Column(String(36), ForeignKey("synthetic_tests.id"), nullable=False, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    location = Column(String(100))

    status = Column(String(20), nullable=False)   # up|down|degraded
    response_time_ms = Column(Float)
    status_code = Column(Integer)

    # SSL details (for ssl_check)
    ssl_valid = Column(Boolean)
    ssl_expires_at = Column(DateTime(timezone=True))
    ssl_days_remaining = Column(Integer)
    ssl_issuer = Column(String(255))
    ssl_subject = Column(String(255))
    ssl_grade = Column(String(5))    # A+|A|B|C|D|F

    # Assertion results
    assertions_passed = Column(Integer, default=0)
    assertions_failed = Column(Integer, default=0)
    assertion_details = Column(JSON, default=list)

    # Response
    response_headers = Column(JSON, default=dict)
    response_body_snippet = Column(Text)   # first 500 chars
    error_message = Column(Text)

    # Playwright steps (for app_flow)
    steps_total = Column(Integer)
    steps_passed = Column(Integer)
    step_details = Column(JSON, default=list)
    screenshot_url = Column(String(500))

    test = relationship("SyntheticTest", foreign_keys=[test_id])
