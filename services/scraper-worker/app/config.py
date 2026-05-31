"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All configuration is read from env vars (or .env file)."""

    # ── Database (psycopg2 — sync driver for Celery workers) ─────────────────
    DATABASE_URL: str = "postgresql+psycopg2://parceliq:devpassword@localhost:5432/parceliq"

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── MinIO ─────────────────────────────────────────────────────────────────
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_USE_SSL: bool = False

    # ── Residential Proxy ─────────────────────────────────────────────────────
    PROXY_URL: str = ""
    PROXY_USERNAME: str = ""
    PROXY_PASSWORD: str = ""

    # ── Worker Config ─────────────────────────────────────────────────────────
    WORKER_CONCURRENCY: int = 1
    # Maximum requests per minute the scraper will make to external services
    SCRAPER_MAX_RPM: int = 20
    VICPLAN_CACHE_TTL_HOURS: int = 168

    # ── App ───────────────────────────────────────────────────────────────────
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "DEBUG"

    @property
    def psycopg2_dsn(self) -> str:
        """Return a plain postgresql:// DSN suitable for psycopg2."""
        return self.DATABASE_URL.replace("postgresql+psycopg2://", "postgresql://")

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
