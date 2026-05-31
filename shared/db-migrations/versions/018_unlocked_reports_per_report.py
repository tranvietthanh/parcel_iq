"""018 – Make unlocked reports per-report

Revision ID: 018
Revises: 017
Create Date: 2026-03-01

Adds ``report_id`` to unlocked_reports so purchases are tied to a specific
property_report. Existing rows are backfilled to the best matching report.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE unlocked_reports
        ADD COLUMN IF NOT EXISTS report_id UUID;
        """
    )

    op.execute(
        """
        UPDATE unlocked_reports ur
                SET report_id = (
                        SELECT pr.id
                        FROM property_reports pr
                        WHERE pr.property_id = ur.property_id
                            AND pr.status = 'READY'
                            AND pr.created_at <= ur.unlocked_at
                        ORDER BY pr.created_at DESC
                        LIMIT 1
                )
        WHERE ur.report_id IS NULL;
        """
    )

    op.execute(
        """
        UPDATE unlocked_reports ur
                SET report_id = (
                        SELECT pr.id
                        FROM property_reports pr
                        WHERE pr.property_id = ur.property_id
                            AND pr.status = 'READY'
                        ORDER BY pr.created_at DESC
                        LIMIT 1
                )
        WHERE ur.report_id IS NULL;
        """
    )

    op.execute(
        """
        UPDATE unlocked_reports ur
        SET report_id = (
            SELECT pr.id
            FROM property_reports pr
            WHERE pr.property_id = ur.property_id
            ORDER BY pr.created_at DESC
            LIMIT 1
        )
        WHERE ur.report_id IS NULL;
        """
    )

    op.execute(
        """
        ALTER TABLE unlocked_reports
        ALTER COLUMN user_id DROP NOT NULL,
        ALTER COLUMN report_id SET NOT NULL;
        """
    )

    op.execute(
        """
        ALTER TABLE unlocked_reports
        ADD CONSTRAINT unlocked_reports_report_id_fkey
        FOREIGN KEY (report_id) REFERENCES property_reports(id);
        """
    )

    op.execute(
        """
        ALTER TABLE unlocked_reports
        DROP CONSTRAINT IF EXISTS unlocked_reports_user_id_property_id_key;
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_unlocked_user_report
        ON unlocked_reports (user_id, report_id)
        WHERE user_id IS NOT NULL;
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_unlocked_report
        ON unlocked_reports (report_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_unlocked_report;")
    op.execute("DROP INDEX IF EXISTS ux_unlocked_user_report;")

    op.execute(
        """
        ALTER TABLE unlocked_reports
        DROP CONSTRAINT IF EXISTS unlocked_reports_report_id_fkey;
        """
    )

    op.execute(
        """
        ALTER TABLE unlocked_reports
        ALTER COLUMN user_id SET NOT NULL,
        ALTER COLUMN report_id DROP NOT NULL;
        """
    )

    op.execute(
        """
        ALTER TABLE unlocked_reports
        DROP COLUMN IF EXISTS report_id;
        """
    )

    op.execute(
        """
        ALTER TABLE unlocked_reports
        ADD CONSTRAINT unlocked_reports_user_id_property_id_key
        UNIQUE (user_id, property_id);
        """
    )
