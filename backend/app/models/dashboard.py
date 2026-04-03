from sqlalchemy import Column, String, Float, Integer, Boolean, JSON, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from app.db.base import Base


class Dashboard(Base):
    __tablename__ = "dashboards"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)   # NULL = shared
    name = Column(String(255), nullable=False)
    description = Column(Text)
    icon = Column(String(50), default="chart-bar")
    is_default = Column(Boolean, default=False)
    is_system = Column(Boolean, default=False)   # built-in dashboard
    is_public = Column(Boolean, default=False)   # visible to all tenant users

    # Layout config
    layout = Column(JSON, default=dict)   # grid layout positions
    variables = Column(JSON, default=list)  # dashboard variables/filters
    time_range = Column(String(30), default="1h")
    auto_refresh = Column(Integer, default=60)  # seconds, 0=disabled

    # Tags
    tags = Column(JSON, default=list)
    category = Column(String(50), default="custom")  # custom|host|network|k8s|cloud|app|security|synthetic

    widgets = relationship("DashboardWidget", back_populates="dashboard", cascade="all, delete-orphan")


class DashboardWidget(Base):
    __tablename__ = "dashboard_widgets"

    dashboard_id = Column(String(36), ForeignKey("dashboards.id"), nullable=False, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)

    title = Column(String(255))
    description = Column(Text)

    # Visualization type
    viz_type = Column(String(30), nullable=False)
    # Types: timeseries|bar|pie|donut|gauge|stat|table|logs|
    #        honeycomb|topology|heatmap|alert_list|text|iframe

    # Position & size in grid
    grid_x = Column(Integer, default=0)
    grid_y = Column(Integer, default=0)
    grid_w = Column(Integer, default=6)
    grid_h = Column(Integer, default=4)

    # Data source config
    datasource = Column(String(30), default="nexus")  # nexus|prometheus|loki|elasticsearch
    metric = Column(String(255))           # metric name or query
    query = Column(Text)                   # raw query / PromQL / SQL
    entity_type = Column(String(30))       # host|network_asset|service|k8s
    entity_ids = Column(JSON, default=list)  # specific entity filter
    group_by = Column(String(100))
    aggregation = Column(String(20), default="avg")  # avg|sum|max|min|count|p95

    # Visualization options
    options = Column(JSON, default=dict)
    # color_scheme, thresholds, unit, legend, etc.

    # Honeycomb specific
    honeycomb_entity_type = Column(String(30))
    honeycomb_metric = Column(String(100))
    honeycomb_size_metric = Column(String(100))

    dashboard = relationship("Dashboard", back_populates="widgets")
