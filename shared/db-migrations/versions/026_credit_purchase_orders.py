"""026 – Credit purchase orders + payment event receipts

Revision ID: 026
Revises: 026a
Create Date: 2026-05-27

Introduces payment-processor-backed credit purchases.

New objects:
  - credit_purchase_status enum     (PENDING, PAID, FAILED)
  - credit_purchase_orders table    (one row per checkout session)
  - payment_event_receipts table    (idempotency guard for webhook replays)

Existing objects modified:
  - credit_ledger.delta_credits     CHECK constraint updated to allow PURCHASE_CREDIT > 0
  - credit_ledger                   ADD COLUMN related_order_id FK

Prerequisite:
  - 026a adds 'PURCHASE_CREDIT' to credit_entry_type enum (runs outside
    transaction due to Postgres ALTER TYPE ADD VALUE restriction).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "026"
down_revision: Union[str, None] = "026a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Step 1: Update delta_credits CHECK constraint on credit_ledger ─────────
    # The existing constraint only allows positive delta for DAILY_GRANT + ADMIN_TOPUP.
    # Add PURCHASE_CREDIT to the allowlist (enum value added in 026a).
    op.execute("""
        ALTER TABLE credit_ledger
            DROP CONSTRAINT IF EXISTS credit_ledger_check
    """)
    op.execute("""
        ALTER TABLE credit_ledger
            DROP CONSTRAINT IF EXISTS credit_ledger_delta_credits_check
    """)
    op.execute("""
        ALTER TABLE credit_ledger
            ADD CONSTRAINT credit_ledger_delta_credits_check CHECK (
                (entry_type = 'DOWNLOAD_DEBIT' AND delta_credits < 0)
                OR (entry_type IN ('DAILY_GRANT', 'ADMIN_TOPUP', 'PURCHASE_CREDIT') AND delta_credits > 0)
            )
    """)

    # ── Step 3: credit_purchase_status enum ───────────────────────────────────
    op.execute("""
        CREATE TYPE credit_purchase_status AS ENUM (
            'PENDING',
            'PAID',
            'FAILED'
        )
    """)

    # ── Step 4: credit_purchase_orders table ──────────────────────────────────
    op.execute("""
        CREATE TABLE credit_purchase_orders (
            id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id                     UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            credits                     INT  NOT NULL CHECK (credits >= 5),
            unit_price_aud_cents        INT  NOT NULL CHECK (unit_price_aud_cents > 0),
            total_amount_aud_cents      INT  NOT NULL GENERATED ALWAYS AS
                                             (credits * unit_price_aud_cents) STORED,
            status                      credit_purchase_status NOT NULL DEFAULT 'PENDING',
            provider                    TEXT NOT NULL DEFAULT 'stripe',
            provider_checkout_id        TEXT UNIQUE,
            provider_payment_intent_id  TEXT UNIQUE,
            provider_event_id_last      TEXT,
            created_at                  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at                  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            paid_at                     TIMESTAMP WITH TIME ZONE
        )
    """)

    op.execute("""
        CREATE INDEX idx_purchase_orders_user_id
            ON credit_purchase_orders (user_id, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX idx_purchase_orders_status
            ON credit_purchase_orders (status, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX idx_purchase_orders_provider_checkout
            ON credit_purchase_orders (provider_checkout_id)
            WHERE provider_checkout_id IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX idx_purchase_orders_payment_intent
            ON credit_purchase_orders (provider_payment_intent_id)
            WHERE provider_payment_intent_id IS NOT NULL
    """)

    # ── Step 5: payment_event_receipts table (webhook replay guard) ───────────
    op.execute("""
        CREATE TABLE payment_event_receipts (
            provider_event_id   TEXT PRIMARY KEY,
            provider            TEXT NOT NULL DEFAULT 'stripe',
            order_id            UUID REFERENCES credit_purchase_orders(id) ON DELETE SET NULL,
            processed_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX idx_event_receipts_order_id
            ON payment_event_receipts (order_id)
            WHERE order_id IS NOT NULL
    """)

    # ── Step 6: Add related_order_id to credit_ledger ─────────────────────────
    # Allows direct JOIN from PURCHASE_CREDIT ledger entries to their originating
    # order without parsing metadata JSON.
    op.execute("""
        ALTER TABLE credit_ledger
            ADD COLUMN related_order_id UUID
                REFERENCES credit_purchase_orders(id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE INDEX idx_ledger_order_id
            ON credit_ledger (related_order_id)
            WHERE related_order_id IS NOT NULL
    """)


def downgrade() -> None:
    """Partial downgrade — drops tables/columns that reference PURCHASE_CREDIT.

    NOTE: The 'PURCHASE_CREDIT' value added to credit_entry_type cannot be
    removed in Postgres. The enum value will remain after downgrade. Any rows
    with entry_type='PURCHASE_CREDIT' must be deleted before downgrade or this
    will fail on the constraint restore.
    """
    # Drop related_order_id from credit_ledger
    op.execute("DROP INDEX IF EXISTS idx_ledger_order_id")
    op.execute("ALTER TABLE credit_ledger DROP COLUMN IF EXISTS related_order_id")

    # Restore original delta_credits constraint (without PURCHASE_CREDIT)
    op.execute("""
        ALTER TABLE credit_ledger
            DROP CONSTRAINT IF EXISTS credit_ledger_delta_credits_check
    """)
    op.execute("""
        ALTER TABLE credit_ledger
            ADD CONSTRAINT credit_ledger_delta_credits_check CHECK (
                (entry_type = 'DOWNLOAD_DEBIT' AND delta_credits < 0)
                OR (entry_type IN ('DAILY_GRANT', 'ADMIN_TOPUP') AND delta_credits > 0)
            )
    """)

    # Drop payment infrastructure tables
    op.execute("DROP TABLE IF EXISTS payment_event_receipts CASCADE")
    op.execute("DROP TABLE IF EXISTS credit_purchase_orders CASCADE")
    op.execute("DROP TYPE IF EXISTS credit_purchase_status CASCADE")

    # Note: credit_entry_type 'PURCHASE_CREDIT' value remains — not removable.
