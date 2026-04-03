"""
Nexus Platform v4 — Core Configuration
"""
from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, field_validator
from typing import List, Optional
import secrets


class Settings(BaseSettings):
    # ── App ────────────────────────────────────────────────────────
    APP_NAME: str = "Nexus Platform"
    APP_VERSION: str = "4.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = secrets.token_urlsafe(64)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── Server ─────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4
    PLATFORM_URL: str = "http://localhost:8000"

    # ── Database ───────────────────────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "nexus"
    POSTGRES_USER: str = "nexus"
    POSTGRES_PASSWORD: str = "nexus_password"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ── Redis / Celery ─────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def CELERY_BROKER_URL(self) -> str:
        return self.REDIS_URL

    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        return self.REDIS_URL

    # ── AI Providers ───────────────────────────────────────────────
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-3-5-haiku-20241022"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.0-flash"
    AI_PROVIDER: str = "openai"   # openai | anthropic | gemini

    # ── Email (SMTP) ───────────────────────────────────────────────
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: str = "nexus@yourdomain.com"
    SMTP_TLS: bool = True

    # ── Notification Channels ──────────────────────────────────────
    SLACK_BOT_TOKEN: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TEAMS_WEBHOOK_URL: Optional[str] = None
    WHATSAPP_TOKEN: Optional[str] = None
    PAGERDUTY_KEY: Optional[str] = None
    OPSGENIE_KEY: Optional[str] = None
    DISCORD_WEBHOOK: Optional[str] = None

    # ── Cloud Integrations ─────────────────────────────────────────
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_DEFAULT_REGION: str = "us-east-1"

    AZURE_TENANT_ID: Optional[str] = None
    AZURE_CLIENT_ID: Optional[str] = None
    AZURE_CLIENT_SECRET: Optional[str] = None
    AZURE_SUBSCRIPTION_ID: Optional[str] = None

    GCP_PROJECT_ID: Optional[str] = None
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None

    # ── Kubernetes ─────────────────────────────────────────────────
    KUBECONFIG_PATH: Optional[str] = None
    K8S_IN_CLUSTER: bool = False

    # ── VMware ─────────────────────────────────────────────────────
    VMWARE_HOST: Optional[str] = None
    VMWARE_USER: Optional[str] = None
    VMWARE_PASSWORD: Optional[str] = None
    VMWARE_PORT: int = 443

    # ── OTel Collector ─────────────────────────────────────────────
    OTEL_COLLECTOR_GRPC: str = "localhost:4317"
    OTEL_COLLECTOR_HTTP: str = "localhost:4318"

    # ── Agent / Gateway tokens ─────────────────────────────────────
    AGENT_TOKEN_PREFIX: str = "nxa"
    GATEWAY_TOKEN_PREFIX: str = "nxg"

    # ── Synthetic Tests ────────────────────────────────────────────
    SYNTHETIC_WORKERS: int = 10
    SYNTHETIC_TIMEOUT_S: int = 30
    SYNTHETIC_INTERVAL_MIN: int = 1

    # ── AI Baseline / Anomaly ──────────────────────────────────────
    BASELINE_WINDOW_HOURS: int = 168    # 1 week
    BASELINE_ANOMALY_STD: float = 3.0   # 3-sigma rule
    AI_ANALYSIS_INTERVAL_MIN: int = 5
    AI_SECURITY_ANALYSIS_INTERVAL_MIN: int = 2

    # ── CORS ───────────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = ["*"]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
