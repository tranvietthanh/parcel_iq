"""004 – Create property_school_catchments table

Revision ID: 004
Revises: 003
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE property_school_catchments (
            property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            zone_id     UUID NOT NULL REFERENCES spatial_zones(id) ON DELETE CASCADE,
            PRIMARY KEY (property_id, zone_id)
        );
    """)
    op.execute("CREATE INDEX idx_psc_property ON property_school_catchments (property_id);")
    op.execute("CREATE INDEX idx_psc_zone     ON property_school_catchments (zone_id);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS property_school_catchments CASCADE;")
