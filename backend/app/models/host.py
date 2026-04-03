from sqlalchemy import Column, String, Float, Integer, Boolean, JSON, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from app.db.base import Base


class Host(Base):
    __tablename__ = "hosts"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    hostname = Column(String(255), nullable=False)
    ip = Column(String(50))
    os = Column(String(100))
    os_version = Column(String(100))
    kernel = Column(String(100))
    arch = Column(String(20))
    manufacturer = Column(String(100))
    model = Column(String(100))
    serial_number = Column(String(100))
    location = Column(String(255))
    environment = Column(String(50))   # production|staging|dev
    tags = Column(JSON, default=list)
    alias = Column(String(255))

    # Agent
    agent_version = Column(String(30))
    agent_token_id = Column(String(36), ForeignKey("agent_tokens.id"))
    monitoring_mode = Column(String(30), default="infra+otel")
    last_seen = Column(DateTime(timezone=True))
    status = Column(String(20), default="unknown")  # online|offline|warning|critical|unknown

    # Current metrics (latest snapshot)
    cpu_usage = Column(Float, default=0)
    memory_usage = Column(Float, default=0)
    disk_usage = Column(Float, default=0)
    uptime = Column(Integer, default=0)
    load_avg_1 = Column(Float, default=0)
    load_avg_5 = Column(Float, default=0)
    load_avg_15 = Column(Float, default=0)
    cpu_cores = Column(Integer, default=1)
    memory_total_mb = Column(Integer, default=0)
    disk_total_gb = Column(Float, default=0)

    # Features enabled
    otel_enabled = Column(Boolean, default=False)
    log_collection = Column(Boolean, default=True)
    ids_enabled = Column(Boolean, default=False)
    vuln_scan_enabled = Column(Boolean, default=False)
    network_scan_enabled = Column(Boolean, default=False)
    apm_enabled = Column(Boolean, default=False)

    # Config
    log_paths = Column(JSON, default=list)
    custom_config = Column(JSON, default=dict)

    metrics = relationship("HostMetric", back_populates="host", cascade="all, delete-orphan")
    agent_token = relationship("AgentToken", foreign_keys=[agent_token_id])


class HostMetric(Base):
    __tablename__ = "host_metrics"

    host_id = Column(String(36), ForeignKey("hosts.id"), nullable=False, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    # CPU
    cpu_usage = Column(Float)
    cpu_steal = Column(Float)
    cpu_iowait = Column(Float)

    # Memory
    memory_usage = Column(Float)
    memory_used_mb = Column(Integer)
    memory_cached_mb = Column(Integer)

    # Disk
    disk_usage = Column(Float)
    disk_read_bytes = Column(Integer)
    disk_write_bytes = Column(Integer)
    disk_read_iops = Column(Integer)
    disk_write_iops = Column(Integer)

    # Network
    net_rx_bytes = Column(Integer)
    net_tx_bytes = Column(Integer)
    net_rx_packets = Column(Integer)
    net_tx_packets = Column(Integer)
    net_errors = Column(Integer)

    # Load
    load_avg_1 = Column(Float)
    load_avg_5 = Column(Float)
    load_avg_15 = Column(Float)

    # Process count
    processes_total = Column(Integer)
    processes_running = Column(Integer)

    host = relationship("Host", back_populates="metrics")
