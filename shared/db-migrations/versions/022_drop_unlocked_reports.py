"""022 – Drop unlocked_reports table

Revision ID: 022
Revises: 021
Create Date: 2026-03-08

Removes purchase-based unlocked_reports table since we're moving to
subscription-based access model.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS unlocked_reports CASCADE")


def downgrade() -> None:
    # Recreate unlocked_reports table with report_id (from migration 018)
    op.execute("""
        CREATE TABLE unlocked_reports (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id                 UUID REFERENCES users(id) ON DELETE CASCADE,
            property_id             UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            report_id               UUID NOT NULL REFERENCES property_reports(id),
            stripe_transaction_id   VARCHAR(255) NOT NULL,
            amount_paid_aud         NUMERIC(8, 2) NOT NULL DEFAULT 39.00,
            unlocked_at             TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_unlocked_user ON unlocked_reports (user_id)")
    op.execute("CREATE INDEX idx_unlocked_property ON unlocked_reports (property_id)")
    op.execute("CREATE INDEX idx_unlocked_report ON unlocked_reports (report_id)")
    op.execute("""
        CREATE UNIQUE INDEX ux_unlocked_user_report ON unlocked_reports (user_id, report_id)
        WHERE user_id IS NOT NULL
    """)
