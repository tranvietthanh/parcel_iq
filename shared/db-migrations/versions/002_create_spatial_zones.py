"""002 – Create spatial_zones table

Revision ID: 002
Revises: 001
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE spatial_zones (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            zone_type   VARCHAR(30) NOT NULL
                            CHECK (zone_type IN ('LGA', 'SUBURB', 'SCHOOL_CATCHMENT')),
            name        VARCHAR(255) NOT NULL,
            state       CHAR(3) NOT NULL
                            CHECK (state IN ('VIC','NSW','QLD','SA','WA','TAS','ACT','NT')),
            geom        GEOMETRY(MultiPolygon, 4326) NOT NULL,
            metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX idx_spatial_zones_geom       ON spatial_zones USING GiST (geom);")
    op.execute("CREATE INDEX idx_spatial_zones_type       ON spatial_zones (zone_type);")
    op.execute("CREATE INDEX idx_spatial_zones_state      ON spatial_zones (state);")
    op.execute("CREATE INDEX idx_spatial_zones_type_state ON spatial_zones (zone_type, state);")
    op.execute("CREATE INDEX idx_spatial_zones_name_trgm  ON spatial_zones USING GIN (name gin_trgm_ops);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS spatial_zones CASCADE;")
