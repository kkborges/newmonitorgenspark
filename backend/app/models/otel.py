from sqlalchemy import Column, String, Float, Integer, Boolean, JSON, ForeignKey, DateTime, Text
from app.db.base import Base


class OtelTrace(Base):
    __tablename__ = "otel_traces"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    trace_id = Column(String(64), nullable=False, index=True)
    span_id = Column(String(32), nullable=False)
    parent_span_id = Column(String(32))
    name = Column(String(500), nullable=False)
    service = Column(String(100), nullable=False, index=True)
    host_id = Column(String(36), ForeignKey("hosts.id"), nullable=True)
    host_name = Column(String(255))

    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True))
    duration_ms = Column(Float)

    status = Column(String(20), default="ok")   # ok|error|unset
    status_code = Column(Integer)
    kind = Column(String(20), default="server")  # server|client|producer|consumer|internal
    method = Column(String(10))    # HTTP method
    url = Column(String(2000))
    response_code = Column(Integer)

    # External service calls
    is_external_call = Column(Boolean, default=False)
    external_host = Column(String(255))
    external_service = Column(String(100))

    attributes = Column(JSON, default=dict)
    events = Column(JSON, default=list)
    resource = Column(JSON, default=dict)

    # AI analysis
    ai_analysed = Column(Boolean, default=False)
    ai_summary = Column(Text)
    ai_root_cause = Column(Text)
    ai_recommendation = Column(Text)
    ai_severity = Column(String(20))

    span_count = Column(Integer, default=1)
    error_count = Column(Integer, default=0)


class OtelSpan(Base):
    __tablename__ = "otel_spans"

    trace_id = Column(String(64), ForeignKey("otel_traces.trace_id"), nullable=False, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    span_id = Column(String(32), nullable=False)
    parent_span_id = Column(String(32))
    name = Column(String(500))
    service = Column(String(100))
    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))
    duration_ms = Column(Float)
    status = Column(String(20), default="ok")
    attributes = Column(JSON, default=dict)
    events = Column(JSON, default=list)


class OtelMetric(Base):
    __tablename__ = "otel_metrics"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    host_id = Column(String(36), ForeignKey("hosts.id"), nullable=True, index=True)
    service = Column(String(100), index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    metric_name = Column(String(255), nullable=False, index=True)
    metric_type = Column(String(20))   # gauge|counter|histogram|summary
    value = Column(Float)
    unit = Column(String(50))
    labels = Column(JSON, default=dict)
