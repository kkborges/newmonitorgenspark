from sqlalchemy import Column, String, Float, Integer, Boolean, JSON, ForeignKey, DateTime, Text
from app.db.base import Base


class NetworkAsset(Base):
    __tablename__ = "network_assets"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    hostname = Column(String(255))
    ip = Column(String(50), nullable=False)
    mac = Column(String(20))
    asset_type = Column(String(30))   # switch|router|firewall|ap|ups|printer|server
    manufacturer = Column(String(100))
    model = Column(String(100))
    os_firmware = Column(String(100))
    serial = Column(String(100))
    location = Column(String(255))
    group = Column(String(100))

    snmp_enabled = Column(Boolean, default=False)
    snmp_version = Column(String(5), default="v2c")
    snmp_community = Column(String(100))
    snmp_port = Column(Integer, default=161)
    snmp_auth_key = Column(String(255))
    snmp_priv_key = Column(String(255))

    syslog_enabled = Column(Boolean, default=False)
    syslog_port = Column(Integer, default=514)

    status = Column(String(20), default="unknown")
    last_poll = Column(DateTime(timezone=True))
    last_scan = Column(DateTime(timezone=True))

    cpu_usage = Column(Float)
    memory_usage = Column(Float)
    temperature = Column(Float)
    uptime = Column(Integer)

    port_count = Column(Integer, default=0)
    ports_up = Column(Integer, default=0)
    ports_down = Column(Integer, default=0)
    ports_fiber = Column(Integer, default=0)
    ports_copper = Column(Integer, default=0)

    modules = Column(JSON, default=list)
    features = Column(JSON, default=list)
    tags = Column(JSON, default=list)


class NetworkPort(Base):
    __tablename__ = "network_ports"

    asset_id = Column(String(36), ForeignKey("network_assets.id"), nullable=False, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)

    port_number = Column(Integer, nullable=False)
    name = Column(String(100))
    description = Column(String(255))
    media_type = Column(String(20))   # fiber|copper|sfp|qsfp
    speed_mbps = Column(Integer)
    duplex = Column(String(10))   # full|half|auto
    status = Column(String(20), default="unknown")  # up|down|admin_down
    vlan = Column(String(50))
    connected_device = Column(String(255))

    utilization = Column(Float, default=0)
    rx_bytes = Column(Integer, default=0)
    tx_bytes = Column(Integer, default=0)
    rx_packets = Column(Integer, default=0)
    tx_packets = Column(Integer, default=0)
    rx_errors = Column(Integer, default=0)
    tx_errors = Column(Integer, default=0)
    rx_drops = Column(Integer, default=0)
    tx_drops = Column(Integer, default=0)

    last_updated = Column(DateTime(timezone=True))


class NetworkMetric(Base):
    __tablename__ = "network_metrics"

    asset_id = Column(String(36), ForeignKey("network_assets.id"), nullable=False, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    cpu_usage = Column(Float)
    memory_usage = Column(Float)
    temperature = Column(Float)
    bandwidth_in_mbps = Column(Float)
    bandwidth_out_mbps = Column(Float)
    packet_loss_pct = Column(Float)
    error_rate = Column(Float)
