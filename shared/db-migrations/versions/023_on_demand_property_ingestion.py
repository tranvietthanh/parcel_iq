"""023_on_demand_property_ingestion

Revision ID: 023
Revises: 022
Create Date: 2026-05-22

"""
from typing import Sequence, Union

from alembic import op


revision: str = '023'
down_revision: Union[str, None] = '022'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add requested_by_user_id column
    op.execute("ALTER TABLE property_reports ADD COLUMN requested_by_user_id UUID REFERENCES users(id) NULL")

    # 2. Update status CHECK constraint (drop old, add new)
    op.execute("ALTER TABLE property_reports DROP CONSTRAINT IF EXISTS property_reports_status_check")
    op.execute("ALTER TABLE property_reports ADD CONSTRAINT property_reports_status_check CHECK (status IN ('QUEUING', 'PROCESSING', 'READY', 'FAILED', 'PENDING', 'SCRAPING', 'PENDING_LLM', 'PROCESSING_LLM', 'FAILED_SCRAPE', 'FAILED_LLM', 'REVIEW_REQUIRED'))")

    # 3. Migrate existing status values
    op.execute("""
        UPDATE property_reports 
        SET status = CASE 
            WHEN status IN ('SCRAPING', 'PENDING_LLM', 'PROCESSING_LLM') THEN 'PROCESSING'
            WHEN status IN ('FAILED_SCRAPE', 'FAILED_LLM') THEN 'FAILED'
            WHEN status = 'REVIEW_REQUIRED' THEN 'READY'
            ELSE status
        END
    """)

    # 4. Enforce final CHECK constraint
    op.execute("ALTER TABLE property_reports DROP CONSTRAINT IF EXISTS property_reports_status_check")
    op.execute("ALTER TABLE property_reports ADD CONSTRAINT property_reports_status_check CHECK (status IN ('QUEUING', 'PROCESSING', 'READY', 'FAILED'))")

    # 5. Drop idx_reports_review_queue
    op.execute("DROP INDEX IF EXISTS idx_reports_review_queue")

    # 6. Drop review_flag column
    op.execute("ALTER TABLE property_reports DROP COLUMN review_flag")



def downgrade() -> None:
    # 1. Add review_flag column
    op.execute("ALTER TABLE property_reports ADD COLUMN review_flag BOOLEAN DEFAULT FALSE")

    # 2. Create idx_reports_review_queue
    op.execute("CREATE INDEX idx_reports_review_queue ON property_reports (status, created_at) WHERE review_flag = TRUE")

    # 3. Update status CHECK constraint (drop old, add new allowing both old and new)
    op.execute("ALTER TABLE property_reports DROP CONSTRAINT IF EXISTS property_reports_status_check")
    op.execute("ALTER TABLE property_reports ADD CONSTRAINT property_reports_status_check CHECK (status IN ('QUEUING', 'PROCESSING', 'READY', 'FAILED', 'PENDING', 'SCRAPING', 'PENDING_LLM', 'PROCESSING_LLM', 'FAILED_SCRAPE', 'FAILED_LLM', 'REVIEW_REQUIRED'))")

    # 4. Revert status values
    op.execute("""
        UPDATE property_reports 
        SET status = CASE 
            WHEN status = 'PROCESSING' THEN 'SCRAPING'
            WHEN status = 'FAILED' THEN 'FAILED_SCRAPE'
            WHEN status = 'QUEUING' THEN 'PENDING'
            ELSE status
        END
    """)

    # 5. Update status CHECK constraint back to original
    op.execute("ALTER TABLE property_reports DROP CONSTRAINT IF EXISTS property_reports_status_check")
    op.execute("ALTER TABLE property_reports ADD CONSTRAINT property_reports_status_check CHECK (status IN ('PENDING', 'SCRAPING', 'PENDING_LLM', 'PROCESSING_LLM', 'READY', 'FAILED_SCRAPE', 'FAILED_LLM', 'REVIEW_REQUIRED'))")

    # 6. Drop requested_by_user_id
    op.execute("ALTER TABLE property_reports DROP COLUMN requested_by_user_id")

