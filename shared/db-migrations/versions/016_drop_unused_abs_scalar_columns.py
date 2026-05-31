"""016 – Drop unused scalar columns from abs_census_data

Revision ID: 016
Revises: 015
Create Date: 2026-03-01

Drops legacy scalar columns now replaced by enriched payload in raw_data JSONB.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE abs_census_data
        DROP COLUMN IF EXISTS median_household_income_weekly_aud,
        DROP COLUMN IF EXISTS owner_occupier_percent;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE abs_census_data
        ADD COLUMN IF NOT EXISTS median_household_income_weekly_aud INTEGER,
        ADD COLUMN IF NOT EXISTS owner_occupier_percent NUMERIC(5, 2);
        """
    )
