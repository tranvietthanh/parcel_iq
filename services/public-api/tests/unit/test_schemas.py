"""Unit tests for Pydantic schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.search import SearchParams
from app.schemas.payment import PaymentStatusResponse
from app.schemas.user import UserSyncRequest


class TestSearchParams:
    def test_valid_bbox(self):
        p = SearchParams(bbox="144.5,-37.9,144.7,-37.7")
        assert p.bbox == "144.5,-37.9,144.7,-37.7"
        assert p.q is None

    def test_valid_text(self):
        p = SearchParams(q="werribee")
        assert p.q == "werribee"
        assert p.bbox is None

    def test_both_q_and_bbox(self):
        p = SearchParams(q="test", bbox="1,2,3,4")
        assert p.q and p.bbox

    def test_neither_q_nor_bbox_raises(self):
        with pytest.raises(ValidationError, match="Either 'q' or 'bbox' is required"):
            SearchParams()

    def test_limit_default(self):
        p = SearchParams(q="x")
        assert p.limit == 100

    def test_limit_max(self):
        with pytest.raises(ValidationError):
            SearchParams(q="x", limit=501)

    def test_limit_min(self):
        with pytest.raises(ValidationError):
            SearchParams(q="x", limit=0)


class TestPaymentStatusResponse:
    def test_pro_active(self):
        r = PaymentStatusResponse(
            subscription_tier="PRO",
            has_active_subscription=True,
            already_downloaded_today=False,
            quota_used_today=5,
            quota_limit=30,
            can_download=True,
        )
        assert r.subscription_tier == "PRO"
        assert r.has_active_subscription is True
        assert r.quota_limit == 30

    def test_unlimited_no_quota_limit(self):
        r = PaymentStatusResponse(
            subscription_tier="UNLIMITED",
            has_active_subscription=True,
            already_downloaded_today=False,
            quota_used_today=0,
            quota_limit=None,
            can_download=True,
        )
        assert r.quota_limit is None

    def test_free_cannot_download(self):
        r = PaymentStatusResponse(
            subscription_tier="FREE",
            has_active_subscription=False,
            already_downloaded_today=False,
            quota_used_today=0,
            quota_limit=3,
            can_download=False,
        )
        assert r.has_active_subscription is False
        assert r.can_download is False


class TestUserSyncRequest:
    def test_valid(self):
        r = UserSyncRequest(clerk_user_id="user_abc", email="a@example.com")
        assert r.clerk_user_id == "user_abc"

    def test_invalid_email(self):
        with pytest.raises(ValidationError):
            UserSyncRequest(clerk_user_id="user_abc", email="not-email")
