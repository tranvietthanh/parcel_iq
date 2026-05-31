"""009 – Create data_source_configs table

Revision ID: 009
Revises: 008
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE data_source_configs (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            lga_name         VARCHAR(255) NOT NULL,
            state            CHAR(3) NOT NULL
                                 CHECK (state IN ('VIC','NSW','QLD','SA','WA','TAS','ACT','NT')),
            adapter_name     VARCHAR(100) NOT NULL,
            base_url         TEXT NOT NULL,
            config           JSONB NOT NULL DEFAULT '{}'::jsonb,
            enabled          BOOLEAN NOT NULL DEFAULT TRUE,
            last_verified_at TIMESTAMP WITH TIME ZONE,
            created_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (lga_name, state)
        );
    """)
    op.execute("CREATE INDEX idx_dsc_state ON data_source_configs (state);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS data_source_configs CASCADE;")
