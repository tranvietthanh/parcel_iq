"""006 – Create users table

Revision ID: 006
Revises: 005
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE users (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            clerk_user_id   VARCHAR(255) UNIQUE NOT NULL,
            email           VARCHAR(255) UNIQUE NOT NULL,
            subscription_tier VARCHAR(20) NOT NULL DEFAULT 'FREE'
                                CHECK (subscription_tier IN ('FREE', 'PRO')),
            created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            last_seen_at    TIMESTAMP WITH TIME ZONE
        );
    """)
    op.execute("CREATE INDEX idx_users_clerk_id ON users (clerk_user_id);")
    op.execute("CREATE INDEX idx_users_email    ON users (email);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS users CASCADE;")
