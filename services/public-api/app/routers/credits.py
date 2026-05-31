"""Credit endpoints.

GET /api/credits/me                               — wallet summary for current user

The precheck endpoint is mounted separately:
GET /api/properties/{property_id}/full/precheck   — duplicate download advisory check
(see precheck_router below, mounted at /api/properties in main.py)
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.credits import get_wallet_summary, get_spendable_credits
from app.core.rate_limit import limiter
from app.dependencies import get_current_user, get_db
from app.schemas.credit import CreditWalletSummary, DownloadPrecheckResponse
from app.schemas.user import UserRow

router = APIRouter(tags=["credits"])
precheck_router = APIRouter(tags=["credits"])


@router.get("/me", response_model=CreditWalletSummary)
@limiter.limit("120/minute")
async def get_my_credits(
    request: Request,
    current_user: UserRow = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> CreditWalletSummary:
    """Return the authenticated user's credit wallet summary.

    Reconciles the wallet day inline if the AU day has rolled over.
    """
    summary = await get_wallet_summary(current_user.id, db)
    return CreditWalletSummary(**summary)


@precheck_router.get("/{property_id}/full/precheck", response_model=DownloadPrecheckResponse)
@limiter.limit("120/minute")
async def download_precheck(
    request: Request,
    property_id: UUID,
    current_user: UserRow = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> DownloadPrecheckResponse:
    """Advisory precheck before a full report download.

    Returns whether the user has previously downloaded this report and how many
    credits they currently have. This is a best-effort hint — the actual credit
    debit happens atomically after PDF retrieval and may differ if a concurrent
    session changes the balance.
    """
    # Check for prior DOWNLOAD_DEBIT ledger entry for this property
    prior = await db.fetchrow(
        """
        SELECT created_at
        FROM credit_ledger
        WHERE user_id = $1
          AND related_property_id = $2
          AND entry_type = 'DOWNLOAD_DEBIT'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        current_user.id,
        property_id,
    )

    spendable = await get_spendable_credits(current_user.id, db)

    return DownloadPrecheckResponse(
        is_duplicate_download=prior is not None,
        previous_download_at=prior["created_at"] if prior else None,
        spendable_credits=spendable,
    )
