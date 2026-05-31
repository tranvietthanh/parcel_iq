"""015 – Refactor ABS cache table to region-based schema

Revision ID: 015
Revises: 014
Create Date: 2026-03-01

Renames ABS cache columns from SA2-specific naming to generic region naming,
adds region_type, and relaxes census_year for regional time-series payloads.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE abs_census_data RENAME COLUMN sa2_code_2021 TO region_code;")
    op.execute("ALTER TABLE abs_census_data RENAME COLUMN sa2_name_2021 TO region_name;")

    op.execute(
        """
        ALTER TABLE abs_census_data
        ADD COLUMN IF NOT EXISTS region_type VARCHAR(32) NOT NULL DEFAULT 'LGA2021';
        """
    )

    op.execute("DROP INDEX IF EXISTS idx_abs_census_sa2_code;")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_abs_census_region_code
        ON abs_census_data (region_code);
        """
    )

    op.execute(
        """
        ALTER TABLE abs_census_data
        ALTER COLUMN census_year DROP NOT NULL,
        ALTER COLUMN census_year DROP DEFAULT;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE abs_census_data
        ALTER COLUMN census_year SET DEFAULT 2021,
        ALTER COLUMN census_year SET NOT NULL;
        """
    )

    op.execute("DROP INDEX IF EXISTS idx_abs_census_region_code;")

    op.execute("ALTER TABLE abs_census_data DROP COLUMN IF EXISTS region_type;")

    op.execute("ALTER TABLE abs_census_data RENAME COLUMN region_name TO sa2_name_2021;")
    op.execute("ALTER TABLE abs_census_data RENAME COLUMN region_code TO sa2_code_2021;")

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_abs_census_sa2_code
        ON abs_census_data (sa2_code_2021);
        """
    )
