"""025 – Add anon_requester_id to property_reports

Revision ID: 025
Revises: 024
Create Date: 2026-05-27

Extends property_reports with an anon_requester_id column so that report
requests made by anonymous users (cookie-identified) can be claimed by an
authenticated user within a 7-day window after sign-in.

Also drops the subscription-era daily_downloads table and the subscription
columns from the users table as part of the credit-system migration.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. anon_requester_id on property_reports ──────────────────────────────
    op.execute("""
        ALTER TABLE property_reports
        ADD COLUMN anon_requester_id VARCHAR(255)
    """)
    op.execute("""
        CREATE INDEX idx_reports_anon_requester
            ON property_reports (anon_requester_id)
        WHERE anon_requester_id IS NOT NULL
    """)

    # ── 2. Drop daily_downloads table ─────────────────────────────────────────
    # Analytics and download tracking are now served from credit_ledger
    # (entry_type = 'DOWNLOAD_DEBIT').
    op.execute("DROP TABLE IF EXISTS daily_downloads CASCADE")

    # ── 3. Drop subscription columns from users ───────────────────────────────
    # Clerk Billing is decommissioned. subscription_tier was derived from the
    # Clerk JWT pla claim at runtime (not stored); the Stripe columns were
    # tracking columns for the old billing model.
    op.execute("""
        ALTER TABLE users
        DROP COLUMN IF EXISTS subscription_tier,
        DROP COLUMN IF EXISTS stripe_customer_id,
        DROP COLUMN IF EXISTS stripe_subscription_id,
        DROP COLUMN IF EXISTS subscription_status,
        DROP COLUMN IF EXISTS current_period_end
    """)

    # Drop now-orphaned indexes on users (created in 021)
    op.execute("DROP INDEX IF EXISTS idx_users_stripe_customer")
    op.execute("DROP INDEX IF EXISTS idx_users_stripe_subscription")


def downgrade() -> None:
    # Restore subscription columns on users
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS subscription_tier VARCHAR(20) NOT NULL DEFAULT 'FREE'
            CHECK (subscription_tier IN ('FREE', 'PRO', 'UNLIMITED')),
        ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255),
        ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(255),
        ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(20) DEFAULT 'active'
            CHECK (subscription_status IN ('active', 'canceled', 'past_due', 'unpaid', 'trialing')),
        ADD COLUMN IF NOT EXISTS current_period_end TIMESTAMP WITH TIME ZONE
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_stripe_customer ON users (stripe_customer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_stripe_subscription ON users (stripe_subscription_id)")

    # Recreate daily_downloads
    op.execute("""
        CREATE TABLE daily_downloads (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            property_id         UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            download_date_au    DATE NOT NULL,
            downloaded_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (user_id, property_id, download_date_au)
        )
    """)
    op.execute("CREATE INDEX idx_daily_downloads_user_date ON daily_downloads (user_id, download_date_au)")

    # Remove anon_requester_id
    op.execute("DROP INDEX IF EXISTS idx_reports_anon_requester")
    op.execute("ALTER TABLE property_reports DROP COLUMN IF EXISTS anon_requester_id")
