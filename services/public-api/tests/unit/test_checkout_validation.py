"""Unit tests for checkout validation and pricing rules.

Tests:
- credits < 5 rejected (min 5)
- credits == 5 accepted
- credits > 5 accepted
- pricing formula: total = credits × 100 AUD cents
- checkout request schema rejects non-integer credits
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.routers.credit_purchases import CheckoutRequest, UNIT_PRICE_AUD_CENTS, MIN_CREDITS


class TestCheckoutValidation:
    def test_min_credits_boundary_accepted(self):
        """Exactly MIN_CREDITS (5) is valid."""
        req = CheckoutRequest(credits=MIN_CREDITS)
        assert req.credits == MIN_CREDITS

    def test_above_min_accepted(self):
        """Any value above minimum is accepted."""
        req = CheckoutRequest(credits=100)
        assert req.credits == 100

    def test_below_min_rejected(self):
        """credits < 5 raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            CheckoutRequest(credits=4)
        errors = exc_info.value.errors()
        assert any("Minimum purchase" in (e.get("msg") or "") for e in errors)

    def test_zero_credits_rejected(self):
        """0 credits raises ValidationError."""
        with pytest.raises(ValidationError):
            CheckoutRequest(credits=0)

    def test_negative_credits_rejected(self):
        """Negative credits raise ValidationError."""
        with pytest.raises(ValidationError):
            CheckoutRequest(credits=-10)

    def test_missing_credits_rejected(self):
        """Missing credits field raises ValidationError."""
        with pytest.raises(ValidationError):
            CheckoutRequest()

    def test_string_credits_rejected(self):
        """Non-numeric credits raise ValidationError."""
        with pytest.raises(ValidationError):
            CheckoutRequest(credits="many")  # type: ignore[arg-type]


class TestPricingFormula:
    def test_unit_price_is_100_cents(self):
        """Unit price is 100 AUD cents ($1.00 AUD)."""
        assert UNIT_PRICE_AUD_CENTS == 100

    def test_total_for_5_credits(self):
        """5 credits = 500 AUD cents = $5.00."""
        assert 5 * UNIT_PRICE_AUD_CENTS == 500

    def test_total_for_10_credits(self):
        """10 credits = 1000 AUD cents = $10.00."""
        assert 10 * UNIT_PRICE_AUD_CENTS == 1000

    def test_total_for_50_credits(self):
        """50 credits = 5000 AUD cents = $50.00."""
        assert 50 * UNIT_PRICE_AUD_CENTS == 5000

    def test_min_credits_constant(self):
        """MIN_CREDITS is 5."""
        assert MIN_CREDITS == 5
