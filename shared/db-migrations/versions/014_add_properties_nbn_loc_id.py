"""014 – Add nbn_loc_id to properties

Revision ID: 014
Revises: 013
Create Date: 2026-02-28
"""
from typing import Sequence, Union

from alembic import op

revision: str = "014"
down_revision: Union[str, Sequence[str], None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable nbn_loc_id to properties so adapters can persist resolved locIds
    op.execute("ALTER TABLE properties ADD COLUMN IF NOT EXISTS nbn_loc_id VARCHAR(50);")
    # Add index to speed lookups by loc id if needed
    op.execute("CREATE INDEX IF NOT EXISTS idx_properties_nbn_loc_id ON properties (nbn_loc_id);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_properties_nbn_loc_id;")
    op.execute("ALTER TABLE properties DROP COLUMN IF EXISTS nbn_loc_id;")
