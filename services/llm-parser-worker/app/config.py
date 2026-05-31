"""Pydantic-settings configuration for the LLM parser worker."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── Database ─────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+psycopg2://parceliq:devpassword@localhost:5432/parceliq"

    # ── Redis ────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── OpenAI (standard) ───────────────────────────────────────────────
    # Use the official OpenAI REST API with a single set of env vars.
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-3.5-turbo"
    OPENAI_DAILY_QUOTA: int = 100000
    OPENAI_MAX_RPM: int = 60
    # Provider-specific settings removed — worker uses OpenAI (`OPENAI_*`).

    RESEND_API_KEY: str = ""
    PUBLIC_WEB_URL: str = "https://ozpropertyreport.com"

    # ── App ──────────────────────────────────────────────────────────────
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
