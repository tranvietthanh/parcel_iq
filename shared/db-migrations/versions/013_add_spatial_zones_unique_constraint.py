"""Add unique constraint on spatial_zones (zone_type, name, state).

This migration truncates the spatial_zones table to remove duplicates
and adds a unique constraint to prevent future duplicates.

Revision ID: 013
Revises: 012
Create Date: 2026-02-27 20:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Truncate spatial_zones and add unique constraint."""
    # Truncate the table to remove all duplicates
    op.execute("TRUNCATE TABLE spatial_zones CASCADE;")
    
    # Add unique constraint on (zone_type, name, state)
    op.create_unique_constraint(
        "uk_spatial_zones_type_name_state",
        "spatial_zones",
        ["zone_type", "name", "state"],
    )


def downgrade() -> None:
    """Remove unique constraint."""
    op.drop_constraint("uk_spatial_zones_type_name_state", "spatial_zones")
