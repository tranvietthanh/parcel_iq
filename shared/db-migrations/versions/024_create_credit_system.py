"""024 – Create credit system (wallet + ledger)

Revision ID: 024
Revises: 023
Create Date: 2026-05-27

Introduces the ledger-backed credit system that replaces subscription-tier
entitlement for full report downloads.

New objects:
  - credit_entry_type  enum
  - user_credit_wallet table
  - credit_ledger      table

Backfills user_credit_wallet rows for all existing users with zero balances
so the application never needs to INSERT-or-404 on wallet lookup.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Entry-type enum ────────────────────────────────────────────────────
    op.execute("""
        CREATE TYPE credit_entry_type AS ENUM (
            'DAILY_GRANT',
            'DOWNLOAD_DEBIT',
            'ADMIN_TOPUP'
        )
    """)

    # ── 2. user_credit_wallet ─────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE user_credit_wallet (
            user_id                   UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            daily_grant_credits       INT  NOT NULL DEFAULT 0
                                          CHECK (daily_grant_credits >= 0),
            daily_used_credits        INT  NOT NULL DEFAULT 0
                                          CHECK (daily_used_credits >= 0),
            purchased_credits_balance INT  NOT NULL DEFAULT 0
                                          CHECK (purchased_credits_balance >= 0),
            wallet_day_au             DATE NOT NULL DEFAULT CURRENT_DATE,
            updated_at                TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX idx_wallet_user_id ON user_credit_wallet (user_id)
    """)

    # ── 3. credit_ledger ──────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE credit_ledger (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            entry_type        credit_entry_type NOT NULL,
            delta_credits     INT  NOT NULL
                                   CHECK (
                                       (entry_type = 'DOWNLOAD_DEBIT' AND delta_credits < 0)
                                       OR (entry_type IN ('DAILY_GRANT', 'ADMIN_TOPUP') AND delta_credits > 0)
                                   ),
            balance_after     INT  NOT NULL,
            idempotency_key   VARCHAR(255) UNIQUE,
            related_property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
            related_report_id   UUID REFERENCES property_reports(id) ON DELETE SET NULL,
            metadata          JSONB NOT NULL DEFAULT '{}',
            created_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX idx_ledger_user_id    ON credit_ledger (user_id, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX idx_ledger_entry_type ON credit_ledger (entry_type, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX idx_ledger_property   ON credit_ledger (related_property_id)
        WHERE related_property_id IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX ux_ledger_idempotency ON credit_ledger (idempotency_key)
        WHERE idempotency_key IS NOT NULL
    """)

    # ── 4. Backfill wallet rows for all existing users ────────────────────────
    # Initial state: 0 purchased credits, 0 daily grant (daily grant will be
    # set to the configured value X on first access via wallet reconciliation).
    op.execute("""
        INSERT INTO user_credit_wallet (user_id, daily_grant_credits, daily_used_credits,
                                        purchased_credits_balance, wallet_day_au)
        SELECT id, 0, 0, 0, CURRENT_DATE
        FROM users
        ON CONFLICT (user_id) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS credit_ledger CASCADE")
    op.execute("DROP TABLE IF EXISTS user_credit_wallet CASCADE")
    op.execute("DROP TYPE IF EXISTS credit_entry_type CASCADE")
