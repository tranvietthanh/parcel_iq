"""026a – Add PURCHASE_CREDIT to credit_entry_type enum

Revision ID: 026a
Revises: 025
Create Date: 2026-05-27

Separated from 026b because ALTER TYPE ADD VALUE cannot run inside a
transaction in Postgres. This migration commits the enum addition in
autocommit mode, then 026b creates the tables/columns that reference it.

The PURCHASE_CREDIT enum addition is NOT reversible in Postgres
(enum values cannot be removed). The downgrade is a no-op.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "026a"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Must run outside a transaction — Postgres restriction.
    # We commit any open transaction first, then run the ALTER TYPE.
    op.execute("COMMIT")
    op.execute("ALTER TYPE credit_entry_type ADD VALUE IF NOT EXISTS 'PURCHASE_CREDIT'")


def downgrade() -> None:
    # ALTER TYPE ADD VALUE is not reversible in Postgres.
    # The enum value will remain after downgrade.
    pass
