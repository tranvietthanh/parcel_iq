"""027_add_slugs.py - Add slug columns to properties and spatial_zones

Revision ID: 027
Revises: 026a
Create Date: 2026-05-28
"""
from typing import Sequence, Union

from alembic import op

revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Add slug column to spatial_zones
    op.execute("ALTER TABLE spatial_zones ADD COLUMN slug VARCHAR(300) NOT NULL DEFAULT gen_random_uuid()::text")
    op.execute("CREATE UNIQUE INDEX idx_spatial_zones_slug ON spatial_zones (slug)")

    # Add slug column to properties
    op.execute("ALTER TABLE properties ADD COLUMN slug VARCHAR(400) NOT NULL DEFAULT gen_random_uuid()::text")
    op.execute("CREATE UNIQUE INDEX idx_properties_slug ON properties (slug)")

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_properties_slug")
    op.execute("ALTER TABLE properties DROP COLUMN IF EXISTS slug")

    op.execute("DROP INDEX IF EXISTS idx_spatial_zones_slug")
    op.execute("ALTER TABLE spatial_zones DROP COLUMN IF EXISTS slug")
