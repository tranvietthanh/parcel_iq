"""008 – Create saved_properties table

Revision ID: 008
Revises: 007
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE saved_properties (
            user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            notes       TEXT,
            saved_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            PRIMARY KEY (user_id, property_id)
        );
    """)
    op.execute("CREATE INDEX idx_saved_user ON saved_properties (user_id);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS saved_properties CASCADE;")
