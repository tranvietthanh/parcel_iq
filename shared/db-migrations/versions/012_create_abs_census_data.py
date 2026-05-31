"""012 – Create abs_census_data table for cached Census statistics

Revision ID: 012
Revises: 011
Create Date: 2026-02-27

Stores ABS Census 2021 data per SA2 for quick lookup.
Downloaded once via ABS API, updated via Admin refresh action.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE abs_census_data (
            id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            sa2_code_2021               VARCHAR(9) NOT NULL UNIQUE,
            sa2_name_2021               VARCHAR(255),
            median_household_income_weekly_aud  INTEGER,
            owner_occupier_percent      NUMERIC(5, 2),
            census_year                 INTEGER NOT NULL DEFAULT 2021,
            raw_data                    JSONB,
            fetched_at                  TIMESTAMP WITH TIME ZONE,
            created_at                  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at                  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX idx_abs_census_sa2_code ON abs_census_data (sa2_code_2021);
    """)
    op.execute("""
        CREATE INDEX idx_abs_census_fetched_at ON abs_census_data (fetched_at);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_abs_census_fetched_at;")
    op.execute("DROP INDEX IF EXISTS idx_abs_census_sa2_code;")
    op.execute("DROP TABLE IF EXISTS abs_census_data;")
