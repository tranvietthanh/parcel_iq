"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All configuration is read from env vars (or .env file)."""

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://parceliq:devpassword@localhost:5432/parceliq"

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ── Service Auth ──────────────────────────────────────────────────────────
    ADMIN_SERVICE_TOKEN: str = "dev-service-token-change-in-prod"

    # ── Flower (internal ClusterIP URL) ───────────────────────────────────────
    FLOWER_INTERNAL_URL: str = "http://flower:5555"

    # ── MinIO (report PDF cache) ──────────────────────────────────────────────
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_USE_SSL: bool = False
    REPORT_PDF_BUCKET: str = "property-report-pdfs"

    # ── Property image enrichment (optional) ──────────────────────────────────
    # Note: the shared pdf-renderer reads these via os.getenv() directly.
    # These fields exist here for documentation and discoverability only.
    PROPERTY_IMAGE_ENRICHMENT_ENABLED: bool = False
    GOOGLE_MAPS_API_KEY: str | None = None
    PROPERTY_IMAGE_REQUEST_TIMEOUT_SECONDS: float = 4.0

    # ── LLM quota monitoring (matches llm-parser-worker OpenAI settings) ─────
    OPENAI_DAILY_QUOTA: int = 100000

    # ── App ───────────────────────────────────────────────────────────────────
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "DEBUG"

    # Strip asyncpg scheme for asyncpg pool
    @property
    def asyncpg_dsn(self) -> str:
        """Return a plain postgresql:// DSN suitable for asyncpg.create_pool."""
        return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
