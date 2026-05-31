"""011 – Create gnaf_addresses table

Revision ID: 011
Revises: 010
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE gnaf_addresses (
            gnaf_pid       VARCHAR(50) PRIMARY KEY,
            address_string TEXT NOT NULL,
            latitude       DOUBLE PRECISION NOT NULL,
            longitude      DOUBLE PRECISION NOT NULL,
            postcode       CHAR(4),
            suburb         VARCHAR(100),
            state          CHAR(3) NOT NULL
                               CHECK (state IN ('VIC','NSW','QLD','SA','WA','TAS','ACT','NT')),
            geom           GEOMETRY(Point, 4326)
                               GENERATED ALWAYS AS (
                                   ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
                               ) STORED
        );
    """)
    op.execute("CREATE INDEX idx_gnaf_geom     ON gnaf_addresses USING GiST (geom);")
    op.execute("CREATE INDEX idx_gnaf_postcode ON gnaf_addresses (postcode);")
    op.execute("CREATE INDEX idx_gnaf_state    ON gnaf_addresses (state);")
    op.execute("CREATE INDEX idx_gnaf_suburb   ON gnaf_addresses USING GIN (suburb gin_trgm_ops);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gnaf_addresses CASCADE;")
