"""007 – Create unlocked_reports table

Revision ID: 007
Revises: 006
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE unlocked_reports (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            property_id             UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            stripe_transaction_id   VARCHAR(255) NOT NULL,
            amount_paid_aud         NUMERIC(8, 2) NOT NULL DEFAULT 39.00,
            unlocked_at             TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (user_id, property_id)
        );
    """)
    op.execute("CREATE INDEX idx_unlocked_user     ON unlocked_reports (user_id);")
    op.execute("CREATE INDEX idx_unlocked_property ON unlocked_reports (property_id);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS unlocked_reports CASCADE;")
