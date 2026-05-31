"""Pydantic schemas for credit endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CreditWalletSummary(BaseModel):
    """Response for GET /api/credits/me."""

    daily_remaining: int
    daily_grant: int
    purchased_balance: int
    total_spendable: int


class DownloadPrecheckResponse(BaseModel):
    """Response for GET /api/properties/{property_id}/full/precheck."""

    is_duplicate_download: bool
    previous_download_at: datetime | None = None
    spendable_credits: int

    # Advisory note — not a transactional guarantee
    note: str = (
        "This precheck is advisory only. Credits are debited after successful "
        "PDF retrieval; a concurrent session may affect your balance between "
        "this check and the download."
    )
