"""001 – Create extensions

Revision ID: 001
Revises: None
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements;")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_stat_statements;")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm;")
    op.execute('DROP EXTENSION IF EXISTS "pgcrypto";')
    op.execute("DROP EXTENSION IF EXISTS postgis CASCADE;")
