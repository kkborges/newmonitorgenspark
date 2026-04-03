from sqlalchemy import Column, String, Integer, Boolean, JSON, Text, Enum
from app.db.base import Base
import enum


class PlanType(str, enum.Enum):
    trial = "trial"
    starter = "starter"
    professional = "professional"
    enterprise = "enterprise"


class Tenant(Base):
    __tablename__ = "tenants"

    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    plan = Column(Enum(PlanType), default=PlanType.trial)
    status = Column(String(20), default="active")
    admin_email = Column(String(255))
    admin_name = Column(String(255))

    # Limits
    max_hosts = Column(Integer, default=10)
    max_agents = Column(Integer, default=10)
    max_users = Column(Integer, default=5)
    max_synthetic_tests = Column(Integer, default=20)

    # AI config
    ai_provider = Column(String(30), default="openai")
    ai_api_key = Column(Text)       # tenant's own key (encrypted)
    ai_model = Column(String(50))

    # Feature flags
    features = Column(JSON, default=dict)
    settings = Column(JSON, default=dict)

    # License
    license_key = Column(String(255))
    license_expires_at = Column(String(30))
