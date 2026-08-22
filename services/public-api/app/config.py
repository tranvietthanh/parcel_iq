"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings

# Known insecure development defaults that must never be used in production.
_INSECURE_TURNSTILE_KEY = "1x0000000000000000000000000000000AA"
_INSECURE_WEBHOOK_SECRET = "dev-webhook-secret-change-in-prod"


class Settings(BaseSettings):
    """All configuration is read from env vars (or .env file)."""

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://parceliq:devpassword@localhost:5432/parceliq"

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Clerk ─────────────────────────────────────────────────────────────────
    CLERK_PUBLIC_JWKS_URL: str = ""

    # ── Cloudflare Turnstile ──────────────────────────────────────────────────
    TURNSTILE_SECRET_KEY: str = "1x0000000000000000000000000000000AA"

    # ── Clerk Billing (webhook verification via svix) ─────────────────────────
    CLERK_WEBHOOK_SECRET: str = ""  # Signing secret from Clerk Dashboard > Webhooks

    # ── Email (Resend) ────────────────────────────────────────────────────────
    RESEND_API_KEY: str = ""

    # ── Internal Webhook Secret ───────────────────────────────────────────────
    INTERNAL_WEBHOOK_SECRET: str = "dev-webhook-secret-change-in-prod"

    # ── Stripe ────────────────────────────────────────────────────────────────
    STRIPE_SECRET_KEY: str = ""              # sk_live_... or sk_test_...
    STRIPE_WEBHOOK_SECRET: str = ""          # whsec_... from Stripe Dashboard > Webhooks
    STRIPE_UNIT_PRICE_AUD_CENTS: int = 100   # 1 AUD per credit (100 cents)
    STRIPE_MIN_CREDITS: int = 5              # Minimum purchase quantity

    # ── Feature Flags ─────────────────────────────────────────────────────────
    CREDIT_PURCHASE_ENABLED: bool = False  # Set to true to enable credit purchasing

    # ── Credits ───────────────────────────────────────────────────────────────
    DAILY_CREDIT_GRANT: int = 3  # Free daily download credits granted per user

    # ── App ───────────────────────────────────────────────────────────────────
    # Fail closed: default to production so a forgotten ENVIRONMENT var never
    # silently exposes /docs, disables Turnstile, or accepts dev secrets.
    # Local dev sets ENVIRONMENT=development explicitly via .env.
    ENVIRONMENT: str = "production"
    LOG_LEVEL: str = "DEBUG"
    FRONTEND_URL: str = "http://localhost:3000"  # Public web frontend URL
    # Comma-separated list of allowed CORS origins. Dev origins are added
    # automatically only when ENVIRONMENT=development (see cors_origins).
    CORS_ALLOWED_ORIGINS: str = "https://ozpropertyreport.com"

    @property
    def cors_origins(self) -> list[str]:
        """Resolved CORS allow-list; localhost is included only in development."""
        origins = [
            o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()
        ]
        if self.ENVIRONMENT == "development":
            origins.append("http://localhost:3000")
        return origins

    # Strip asyncpg scheme for asyncpg pool (it doesn't use SQLAlchemy-style URL)
    @property
    def asyncpg_dsn(self) -> str:
        """Return a plain postgresql:// DSN suitable for asyncpg.create_pool."""
        return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    @model_validator(mode="after")
    def _reject_insecure_defaults_in_production(self) -> "Settings":
        """Refuse to boot in production with known development defaults."""
        if self.ENVIRONMENT != "production":
            return self
        problems: list[str] = []
        if "devpassword" in self.DATABASE_URL:
            problems.append("DATABASE_URL still uses the dev password")
        if not self.CLERK_PUBLIC_JWKS_URL:
            problems.append("CLERK_PUBLIC_JWKS_URL is not set")
        if self.TURNSTILE_SECRET_KEY == _INSECURE_TURNSTILE_KEY:
            problems.append("TURNSTILE_SECRET_KEY is the Cloudflare test key")
        if self.INTERNAL_WEBHOOK_SECRET == _INSECURE_WEBHOOK_SECRET:
            problems.append("INTERNAL_WEBHOOK_SECRET is the dev default")
        if self.CREDIT_PURCHASE_ENABLED and not (
            self.STRIPE_SECRET_KEY and self.STRIPE_WEBHOOK_SECRET
        ):
            problems.append(
                "CREDIT_PURCHASE_ENABLED but STRIPE_SECRET_KEY/STRIPE_WEBHOOK_SECRET missing"
            )
        if problems:
            raise ValueError(
                "Insecure production configuration: " + "; ".join(problems)
            )
        return self

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
