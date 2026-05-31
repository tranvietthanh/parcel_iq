"""Stripe service — helpers for Stripe Checkout integration."""

from __future__ import annotations

import stripe

from app.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

REPORT_PRICE_CENTS = 3900  # $39.00 AUD


def create_checkout_session(
    *, property_id: str, user_id: str, clerk_user_id: str, address: str
) -> stripe.checkout.Session:
    """Create a Stripe Checkout session for a property report purchase."""
    return stripe.checkout.Session.create(
        mode="payment",
        currency="aud",
        line_items=[
            {
                "price_data": {
                    "currency": "aud",
                    "unit_amount": REPORT_PRICE_CENTS,
                    "product_data": {
                        "name": "OZ Property Report Full Report",
                        "description": address,
                    },
                },
                "quantity": 1,
            }
        ],
        success_url=f"https://ozpropertyreport.com/property/{property_id}?unlocked=true",
        cancel_url="https://ozpropertyreport.com/?payment=cancelled",
        metadata={
            "property_id": property_id,
            "user_id": user_id,
            "clerk_user_id": clerk_user_id,
        },
    )
