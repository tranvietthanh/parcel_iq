"""003 – Create properties table + address_tokens trigger

Revision ID: 003
Revises: 002
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE properties (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            gnaf_pid            VARCHAR(50) UNIQUE NOT NULL,
            address_string      TEXT NOT NULL,
            address_tokens      TSVECTOR,
            geom                GEOMETRY(Point, 4326) NOT NULL,
            parcel_geom         GEOMETRY(Polygon, 4326),
            state               CHAR(3) NOT NULL
                                    CHECK (state IN ('VIC','NSW','QLD','SA','WA','TAS','ACT','NT')),
            beds                SMALLINT,
            baths               SMALLINT,
            cars                SMALLINT,
            land_size_sqm       INT,
            estimated_value     NUMERIC(12, 2),
            estimated_rent      NUMERIC(8, 2),
            lga_id              UUID REFERENCES spatial_zones(id),
            suburb_id           UUID REFERENCES spatial_zones(id),
            last_scraped_at     TIMESTAMP WITH TIME ZONE,
            created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)

    # Indexes
    op.execute("CREATE INDEX idx_properties_geom       ON properties USING GiST (geom);")
    op.execute("CREATE INDEX idx_properties_parcel     ON properties USING GiST (parcel_geom);")
    op.execute("CREATE INDEX idx_properties_fts        ON properties USING GIN (address_tokens);")
    op.execute("CREATE INDEX idx_properties_trgm       ON properties USING GIN (address_string gin_trgm_ops);")
    op.execute("CREATE INDEX idx_properties_scraped_at ON properties (last_scraped_at);")
    op.execute("CREATE INDEX idx_properties_state      ON properties (state);")

    # Trigger: auto-populate address_tokens tsvector on insert/update
    op.execute("""
        CREATE OR REPLACE FUNCTION sync_address_tokens()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            NEW.address_tokens := to_tsvector('english', COALESCE(NEW.address_string, ''));
            RETURN NEW;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_properties_address_tokens
            BEFORE INSERT OR UPDATE OF address_string ON properties
            FOR EACH ROW EXECUTE FUNCTION sync_address_tokens();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_properties_address_tokens ON properties;")
    op.execute("DROP FUNCTION IF EXISTS sync_address_tokens();")
    op.execute("DROP TABLE IF EXISTS properties CASCADE;")
