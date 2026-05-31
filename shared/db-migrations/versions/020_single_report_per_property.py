"""020 – Single canonical report per property

Revision ID: 020
Revises: 019
Create Date: 2026-03-08

Enforces one report per property by adding UNIQUE constraint.
Removes duplicate reports keeping only the latest per property.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Delete old reports, keeping only the most recent per property
    op.execute("""
        DELETE FROM property_reports pr
        WHERE pr.id NOT IN (
            SELECT DISTINCT ON (property_id) id
            FROM property_reports
            ORDER BY property_id, updated_at DESC, created_at DESC
        )
    """)
    
    # Drop old indexes that supported multi-report queries
    op.execute("DROP INDEX IF EXISTS idx_reports_ready_latest")
    
    # Add UNIQUE constraint on property_id
    op.execute("""
        ALTER TABLE property_reports
        ADD CONSTRAINT uq_property_reports_property_id
        UNIQUE (property_id)
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE property_reports
        DROP CONSTRAINT IF EXISTS uq_property_reports_property_id
    """)
    
    # Recreate the multi-report index
    op.execute("""
        CREATE INDEX idx_reports_ready_latest ON property_reports (property_id, created_at DESC)
            WHERE status = 'READY'
    """)
