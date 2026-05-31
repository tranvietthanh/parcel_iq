"""028_abs_census_sal_unique.py - Add unique constraint to support both LGA2021 and SAL2021

Revision ID: 028
Revises: 027
Create Date: 2026-05-29
"""
from typing import Sequence, Union

from alembic import op

revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Drop existing unique constraints/indexes on region_code if any
    op.execute("ALTER TABLE abs_census_data DROP CONSTRAINT IF EXISTS abs_census_data_sa2_code_2021_key")
    op.execute("ALTER TABLE abs_census_data DROP CONSTRAINT IF EXISTS abs_census_data_region_code_key")
    # Add new constraint
    op.execute("ALTER TABLE abs_census_data ADD CONSTRAINT uq_abs_census_region UNIQUE (region_code, region_type)")
    op.execute("DROP INDEX IF EXISTS idx_abs_census_region_code")
    op.execute("CREATE INDEX idx_abs_census_region_code_type ON abs_census_data (region_code, region_type)")

def downgrade() -> None:
    # Drop new constraint/index
    op.execute("ALTER TABLE abs_census_data DROP CONSTRAINT IF EXISTS uq_abs_census_region")
    op.execute("DROP INDEX IF EXISTS idx_abs_census_region_code_type")
    
    # Restore old constraint/index
    op.execute("ALTER TABLE abs_census_data ADD CONSTRAINT abs_census_data_region_code_key UNIQUE (region_code)")
    op.execute("CREATE INDEX idx_abs_census_region_code ON abs_census_data (region_code)")
