"""010 – Create admin_activity_log table

Revision ID: 010
Revises: 009
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE admin_activity_log (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            clerk_admin_id  VARCHAR(255) NOT NULL,
            admin_email     VARCHAR(255),
            action          VARCHAR(50) NOT NULL,
            target_id       VARCHAR(255),
            detail          TEXT,
            created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX idx_activity_clerk_admin ON admin_activity_log (clerk_admin_id);")
    op.execute("CREATE INDEX idx_activity_created     ON admin_activity_log (created_at DESC);")
    op.execute("CREATE INDEX idx_activity_action      ON admin_activity_log (action);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS admin_activity_log CASCADE;")
