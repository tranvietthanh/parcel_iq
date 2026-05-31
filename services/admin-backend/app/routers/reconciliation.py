"""Reconciliation endpoints — payment order vs ledger integrity checks.

GET /reconciliation/payments              — orders in PAID state with no PURCHASE_CREDIT ledger entry
GET /reconciliation/payments/summary      — aggregate counts by status for dashboard

These endpoints are admin-only (X-Service-Token + X-Admin-User-Id required)
and used by support/ops for identifying fulfillment gaps.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import asyncpg
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.service_auth import verify_service_token
from app.dependencies import get_db

router = APIRouter(
    prefix="/reconciliation",
    tags=["reconciliation"],
    dependencies=[Depends(verify_service_token)],
)


# ── Response models ───────────────────────────────────────────────────────────


class MissingGrantRow(BaseModel):
    order_id: str
    user_id: str
    credits: int
    total_amount_aud_cents: int
    status: str
    provider: str
    provider_payment_intent_id: str | None
    paid_at: str
    created_at: str


class ReconciliationReport(BaseModel):
    checked_at: str
    missing_grants: list[MissingGrantRow]
    total_missing: int


class PaymentStatusSummary(BaseModel):
    status: str
    count: int
    total_credits: int
    total_aud_cents: int


class ReconciliationSummaryResponse(BaseModel):
    as_of: str
    window_days: int
    by_status: list[PaymentStatusSummary]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/payments", response_model=ReconciliationReport)
async def find_missing_grants(
    db: asyncpg.Connection = Depends(get_db),
) -> ReconciliationReport:
    """Return purchase orders in PAID state that have no PURCHASE_CREDIT ledger entry.

    These represent fulfillment gaps — the webhook was processed (order PAID)
    but the credit_ledger insert may have failed silently.

    Used by ops to identify orders that need manual investigation or re-grant.
    """
    now_utc = datetime.now(timezone.utc)

    rows = await db.fetch(
        """
        SELECT
            o.id             AS order_id,
            o.user_id,
            o.credits,
            o.total_amount_aud_cents,
            o.status,
            o.provider,
            o.provider_payment_intent_id,
            o.paid_at,
            o.created_at
        FROM credit_purchase_orders o
        WHERE o.status = 'PAID'
          AND NOT EXISTS (
              SELECT 1 FROM credit_ledger l
              WHERE l.related_order_id = o.id
                AND l.entry_type = 'PURCHASE_CREDIT'
          )
        ORDER BY o.paid_at DESC
        LIMIT 200
        """
    )

    missing = [
        MissingGrantRow(
            order_id=str(r["order_id"]),
            user_id=str(r["user_id"]),
            credits=r["credits"],
            total_amount_aud_cents=r["total_amount_aud_cents"],
            status=r["status"],
            provider=r["provider"],
            provider_payment_intent_id=r["provider_payment_intent_id"],
            paid_at=r["paid_at"].isoformat(),
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]

    return ReconciliationReport(
        checked_at=now_utc.isoformat(),
        missing_grants=missing,
        total_missing=len(missing),
    )


@router.get("/payments/summary", response_model=ReconciliationSummaryResponse)
async def get_payment_summary(
    window_days: int = 30,
    db: asyncpg.Connection = Depends(get_db),
) -> ReconciliationSummaryResponse:
    """Return aggregate order counts/totals by status for the given window.

    Default window: 30 days. Used on admin dashboard for payment health overview.
    """
    now_utc = datetime.now(timezone.utc)
    since = datetime.now(ZoneInfo("Australia/Sydney")).date() - timedelta(days=window_days)

    rows = await db.fetch(
        """
        SELECT
            status,
            COUNT(*)              AS count,
            COALESCE(SUM(credits), 0)              AS total_credits,
            COALESCE(SUM(total_amount_aud_cents), 0) AS total_aud_cents
        FROM credit_purchase_orders
        WHERE created_at >= $1
        GROUP BY status
        ORDER BY status
        """,
        since,
    )

    return ReconciliationSummaryResponse(
        as_of=now_utc.isoformat(),
        window_days=window_days,
        by_status=[
            PaymentStatusSummary(
                status=r["status"],
                count=int(r["count"]),
                total_credits=int(r["total_credits"]),
                total_aud_cents=int(r["total_aud_cents"]),
            )
            for r in rows
        ],
    )
