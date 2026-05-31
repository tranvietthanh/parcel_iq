"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


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

    # ── App ───────────────────────────────────────────────────────────────────
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "DEBUG"
    FRONTEND_URL: str = "http://localhost:3000"  # Public web frontend URL

    # Strip asyncpg scheme for asyncpg pool (it doesn't use SQLAlchemy-style URL)
    @property
    def asyncpg_dsn(self) -> str:
        """Return a plain postgresql:// DSN suitable for asyncpg.create_pool."""
        return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
