"""005 – Create property_reports table

Revision ID: 005
Revises: 004
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE property_reports (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            property_id         UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            status              VARCHAR(30) NOT NULL DEFAULT 'PENDING'
                                    CHECK (status IN (
                                        'PENDING',
                                        'SCRAPING',
                                        'PENDING_LLM',
                                        'PROCESSING_LLM',
                                        'READY',
                                        'FAILED_SCRAPE',
                                        'FAILED_LLM',
                                        'REVIEW_REQUIRED'
                                    )),
            raw_scraped_data    JSONB,
            llm_parsed_insights JSONB,
            confidence_scores   JSONB,
            overall_confidence  VARCHAR(10)
                                    CHECK (overall_confidence IN ('HIGH', 'MEDIUM', 'LOW')),
            review_flag         BOOLEAN NOT NULL DEFAULT FALSE,
            scraper_version     VARCHAR(20),
            llm_model_version   VARCHAR(60),
            error_message       TEXT,
            retry_count         SMALLINT NOT NULL DEFAULT 0,
            created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX idx_reports_property_id  ON property_reports (property_id);")
    op.execute("CREATE INDEX idx_reports_status       ON property_reports (status);")
    op.execute("""
        CREATE INDEX idx_reports_ready_latest ON property_reports (property_id, created_at DESC)
            WHERE status = 'READY';
    """)
    op.execute("""
        CREATE INDEX idx_reports_review_queue ON property_reports (review_flag, created_at DESC)
            WHERE review_flag = TRUE;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS property_reports CASCADE;")
