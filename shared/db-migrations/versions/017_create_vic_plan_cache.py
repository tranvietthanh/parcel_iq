"""017 – Create VicPlan cache table

Revision ID: 017
Revises: 016
Create Date: 2026-03-01

Adds a coordinate-keyed cache table for VicPlan adapter responses so repeated
scrapes in the same location can reuse recently fetched planning payloads.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vic_plan_cache (
            cache_key VARCHAR(64) PRIMARY KEY,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            raw_data JSONB NOT NULL,
            fetched_at TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_vic_plan_cache_expires_at
        ON vic_plan_cache (expires_at);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS vic_plan_cache;")
