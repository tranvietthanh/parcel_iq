"""019 – Create schools table

Stores school locations (point geometry) with metadata.
Separate from spatial_zones (which stores catchment polygons).

Revision ID: 019
Revises: 018
Create Date: 2026-03-02
"""
from typing import Sequence, Union

from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE schools (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            school_id         VARCHAR(100),  -- External ID (e.g., VIC ACARA ID)
            name              VARCHAR(255) NOT NULL,
            address           VARCHAR(255),
            suburb            VARCHAR(100),
            postcode          VARCHAR(10),
            state             CHAR(3) NOT NULL
                                CHECK (state IN ('VIC','NSW','QLD','SA','WA','TAS','ACT','NT')),
            geom              GEOMETRY(Point, 4326) NOT NULL,
            school_type       VARCHAR(50)
                                CHECK (school_type IN ('Primary', 'Secondary', 'Combined', 'Special')),
            gender            VARCHAR(20)
                                CHECK (gender IN ('Mixed', 'Boys', 'Girls')),
            sector            VARCHAR(50)
                                CHECK (sector IN ('Government', 'Catholic', 'Independent')),
            enrolments        INTEGER,
            year_range        VARCHAR(20),  -- e.g., "Prep-6", "7-12"
            catchment_zone_id UUID REFERENCES spatial_zones(id) ON DELETE SET NULL,  -- Link to catchment polygon
            website           VARCHAR(255),
            phone             VARCHAR(50),
            metadata          JSONB NOT NULL DEFAULT '{}'::jsonb,  -- Additional fields
            created_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (school_id, state)  -- Same school_id can exist in different states
        );
    """)
    
    # Spatial index for distance queries (ST_DWithin)
    op.execute("CREATE INDEX idx_schools_geom ON schools USING GiST (geom);")
    
    # Lookup indexes
    op.execute("CREATE INDEX idx_schools_state ON schools (state);")
    op.execute("CREATE INDEX idx_schools_type ON schools (school_type);")
    op.execute("CREATE INDEX idx_schools_sector ON schools (sector);")
    op.execute("CREATE INDEX idx_schools_catchment ON schools (catchment_zone_id);")
    
    # Full-text search on name
    op.execute("CREATE INDEX idx_schools_name_trgm ON schools USING GIN (name gin_trgm_ops);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS schools CASCADE;")
