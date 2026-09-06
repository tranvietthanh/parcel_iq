"""Pydantic-settings configuration for the LLM parser worker."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── Database ─────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+psycopg2://parceliq:devpassword@localhost:5432/parceliq"

    # ── Redis ────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── LLM Provider Configuration ───────────────────────────────────────
    LLM_PROVIDER: Literal["openai", "anthropic", "google"] = "openai"
    LLM_MAX_RPM: int = Field(default=60, ge=1)
    LLM_DAILY_QUOTA: int = Field(default=100000, ge=1)

    # ── OpenAI (standard) ───────────────────────────────────────────────
    # Use the official OpenAI REST API with a single set of env vars.
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-3.5-turbo"

    # ── Anthropic (Phase 2 placeholders) ─────────────────────────────────
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = ""

    # ── Google AI (Phase 2 placeholders) ─────────────────────────────────
    GOOGLE_API_KEY: str = ""
    GOOGLE_MODEL: str = ""

    RESEND_API_KEY: str = ""
    PUBLIC_WEB_URL: str = "https://ozpropertyreport.com"

    # ── App ──────────────────────────────────────────────────────────────
    # Fail closed: default to production. Local dev sets ENVIRONMENT=development.
    ENVIRONMENT: str = "production"
    LOG_LEVEL: str = "INFO"

    @model_validator(mode="after")
    def _reject_insecure_defaults_in_production(self) -> "Settings":
        """Refuse to boot in production with known development defaults."""
        if self.ENVIRONMENT != "production":
            return self
        problems: list[str] = []
        if "devpassword" in self.DATABASE_URL:
            problems.append("DATABASE_URL still uses the dev password")
        if self.LLM_PROVIDER == "openai" and not self.OPENAI_API_KEY:
            problems.append("OPENAI_API_KEY is not set")
        elif self.LLM_PROVIDER == "anthropic" and not self.ANTHROPIC_API_KEY:
            problems.append("ANTHROPIC_API_KEY is not set")
        elif self.LLM_PROVIDER == "google" and not self.GOOGLE_API_KEY:
            problems.append("GOOGLE_API_KEY is not set")
        if problems:
            raise ValueError(
                "Insecure production configuration: " + "; ".join(problems)
            )
        return self

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
