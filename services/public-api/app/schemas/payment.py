"""Pydantic schemas for payment endpoints.

Subscription management is handled by Clerk Billing — no Stripe schemas needed here.
"""

from __future__ import annotations

from pydantic import BaseModel


class PaymentStatusResponse(BaseModel):
    """Response with subscription and download status for a property."""

    subscription_tier: str  # FREE, PRO, UNLIMITED — derived from Clerk Billing JWT
    has_active_subscription: bool
    already_downloaded_today: bool
    quota_used_today: int
    quota_limit: int | None  # None for UNLIMITED
    can_download: bool
