"""021 – Add subscription model

Revision ID: 021
Revises: 020
Create Date: 2026-03-08

Adds subscription tier (including UNLIMITED), Stripe subscription tracking,
and daily download quota tracking table.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update users table subscription tier constraint to include UNLIMITED
    op.execute("""
        ALTER TABLE users
        DROP CONSTRAINT IF EXISTS users_subscription_tier_check
    """)
    
    op.execute("""
        ALTER TABLE users
        ADD CONSTRAINT users_subscription_tier_check
        CHECK (subscription_tier IN ('FREE', 'PRO', 'UNLIMITED'))
    """)
    
    # Add Stripe subscription tracking fields
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255),
        ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(255),
        ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(20) DEFAULT 'active'
            CHECK (subscription_status IN ('active', 'canceled', 'past_due', 'unpaid', 'trialing')),
        ADD COLUMN IF NOT EXISTS current_period_end TIMESTAMP WITH TIME ZONE
    """)
    
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_stripe_customer ON users (stripe_customer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_stripe_subscription ON users (stripe_subscription_id)")
    
    # Create daily downloads tracking table
    # Uses unique constraint on (user_id, property_id, download_date_au) to enforce one count per property per day
    op.execute("""
        CREATE TABLE daily_downloads (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            property_id         UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            download_date_au    DATE NOT NULL,  -- Australia/Sydney timezone
            downloaded_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (user_id, property_id, download_date_au)
        )
    """)
    
    op.execute("CREATE INDEX idx_daily_downloads_user_date ON daily_downloads (user_id, download_date_au)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS daily_downloads CASCADE")
    
    op.execute("""
        ALTER TABLE users
        DROP COLUMN IF EXISTS stripe_customer_id,
        DROP COLUMN IF EXISTS stripe_subscription_id,
        DROP COLUMN IF EXISTS subscription_status,
        DROP COLUMN IF EXISTS current_period_end
    """)
    
    op.execute("""
        ALTER TABLE users
        DROP CONSTRAINT IF EXISTS users_subscription_tier_check
    """)
    
    op.execute("""
        ALTER TABLE users
        ADD CONSTRAINT users_subscription_tier_check
        CHECK (subscription_tier IN ('FREE', 'PRO'))
    """)
