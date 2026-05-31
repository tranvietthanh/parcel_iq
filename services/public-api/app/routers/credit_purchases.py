"""Credit purchase endpoints — Stripe payment integration.

POST /api/credits/checkout              — create Stripe checkout session
POST /api/credits/webhook/stripe        — handle Stripe webhook events
GET  /api/credits/purchases             — user's purchase order history

Architecture notes:
  - Checkout and purchases require Clerk JWT auth (get_current_user).
  - The webhook endpoint is UNAUTHENTICATED — Stripe calls it, not users.
    Security is enforced via Stripe signature verification only.
  - Credit grant on payment success MUST acquire the same per-user advisory
    lock as debit_credit() to prevent races with in-flight downloads.
  - Credits are non-refundable: dispute/chargeback → order FAILED, no clawback.
  - All wallet mutations are idempotent via payment_event_receipts + terminal
    order status guard.

Router is named credit_purchases.py — payments.py is tombstoned.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

import asyncpg
import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, field_validator

from app.config import settings
from app.core.rate_limit import limiter
from app.dependencies import get_current_user, get_db
from app.schemas.user import UserRow

logger = logging.getLogger(__name__)

router = APIRouter(tags=["credit-purchases"])

# ── Constants ─────────────────────────────────────────────────────────────────

UNIT_PRICE_AUD_CENTS = settings.STRIPE_UNIT_PRICE_AUD_CENTS  # 100 = $1.00 AUD
MIN_CREDITS = settings.STRIPE_MIN_CREDITS                     # 5

# Terminal order states — never overwrite these on new events
TERMINAL_STATES = {"PAID", "FAILED"}


# ── Request / Response models ─────────────────────────────────────────────────


class CheckoutRequest(BaseModel):
    credits: int

    @field_validator("credits")
    @classmethod
    def credits_minimum(cls, v: int) -> int:
        if v < MIN_CREDITS:
            raise ValueError(
                f"Minimum purchase is {MIN_CREDITS} credits ({MIN_CREDITS} AUD)."
            )
        return v


class CheckoutResponse(BaseModel):
    checkout_url: str
    order_id: str
    credits: int
    total_aud: float


class PurchaseOrderItem(BaseModel):
    id: str
    credits: int
    unit_price_aud_cents: int
    total_amount_aud_cents: int
    status: str
    provider: str
    provider_checkout_id: str | None
    created_at: str
    paid_at: str | None


class PurchaseHistoryResponse(BaseModel):
    items: list[PurchaseOrderItem]


# ── Checkout ──────────────────────────────────────────────────────────────────


@router.post("/checkout", response_model=CheckoutResponse)
@limiter.limit("10/minute")
async def create_checkout_session(
    request: Request,
    body: CheckoutRequest,
    current_user: UserRow = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> CheckoutResponse:
    """Create a Stripe checkout session for purchasing credits.

    Server validates pricing — the client may NOT specify the price.
    Credits are NOT granted here; they are granted only after the
    verified payment success webhook arrives.
    """
    if not settings.CREDIT_PURCHASE_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Credit purchasing is currently unavailable. This feature is still under development.",
        )

    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail="Payment processing is not yet configured. Please try again later.",
        )

    total_aud_cents = body.credits * UNIT_PRICE_AUD_CENTS

    # Create the purchase order record (PENDING)
    order_id: UUID = await db.fetchval(
        """
        INSERT INTO credit_purchase_orders
            (user_id, credits, unit_price_aud_cents, status, provider)
        VALUES ($1, $2, $3, 'PENDING', 'stripe')
        RETURNING id
        """,
        current_user.id,
        body.credits,
        UNIT_PRICE_AUD_CENTS,
    )

    # Create Stripe checkout session
    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "aud",
                        "unit_amount": UNIT_PRICE_AUD_CENTS,
                        "product_data": {
                            "name": f"OZ Property Report Credits × {body.credits}",
                            "description": (
                                f"{body.credits} download credit"
                                f"{'s' if body.credits != 1 else ''}. "
                                "Each credit unlocks one full property report. Credits never expire."
                            ),
                        },
                    },
                    "quantity": body.credits,
                }
            ],
            metadata={
                "order_id": str(order_id),
                "user_id": str(current_user.id),
                "credits": str(body.credits),
            },
            success_url=f"{settings.FRONTEND_URL}/credits/success?order_id={order_id}",
            cancel_url=f"{settings.FRONTEND_URL}/pricing",
        )
    except stripe.StripeError as e:
        # Roll back the pending order if Stripe session creation fails
        await db.execute(
            "UPDATE credit_purchase_orders SET status = 'FAILED', updated_at = NOW() WHERE id = $1",
            order_id,
        )
        logger.error("Stripe session creation failed: %s", e, extra={"order_id": str(order_id)})
        raise HTTPException(status_code=502, detail="Payment session creation failed. Please try again.")

    # Store Stripe checkout session ID on the order
    await db.execute(
        "UPDATE credit_purchase_orders SET provider_checkout_id = $2, updated_at = NOW() WHERE id = $1",
        order_id,
        session.id,
    )

    return CheckoutResponse(
        checkout_url=session.url,
        order_id=str(order_id),
        credits=body.credits,
        total_aud=total_aud_cents / 100,
    )


# ── Webhook ───────────────────────────────────────────────────────────────────


@router.post("/webhook/stripe", status_code=200)
async def stripe_webhook(
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    stripe_signature: str = Header(alias="Stripe-Signature"),
) -> dict:
    """Handle Stripe webhook events.

    This endpoint is intentionally UNAUTHENTICATED — Stripe calls it,
    not users. Security is solely via Stripe signature verification.

    Handles:
    - checkout.session.completed  → grant credits (PENDING → PAID)
    - payment_intent.payment_failed → mark failed (PENDING → FAILED)
    - charge.dispute.created → record dispute, mark FAILED, NO clawback
    """
    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET not configured — webhook rejected")
        raise HTTPException(status_code=503, detail="Webhook endpoint not configured.")

    payload = await request.body()

    # ── Verify Stripe signature ───────────────────────────────────────────────
    try:
        event = stripe.Webhook.construct_event(
            payload,
            stripe_signature,
            settings.STRIPE_WEBHOOK_SECRET,
        )
    except stripe.SignatureVerificationError:
        logger.warning("Stripe signature verification failed")
        raise HTTPException(status_code=400, detail="Invalid signature.")
    except Exception as exc:
        logger.error("Stripe event construction failed: %s", exc)
        raise HTTPException(status_code=400, detail="Malformed webhook payload.")

    event_id: str = event["id"]
    event_type: str = event["type"]

    # ── Idempotency: skip already-processed events ────────────────────────────
    already_processed = await db.fetchval(
        "SELECT 1 FROM payment_event_receipts WHERE provider_event_id = $1",
        event_id,
    )
    if already_processed:
        logger.info("Duplicate webhook event ignored: %s", event_id)
        return {"status": "already_processed"}

    # ── Route by event type ───────────────────────────────────────────────────
    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(event, event_id, db)

    elif event_type == "payment_intent.payment_failed":
        await _handle_payment_failed(event, event_id, db)

    elif event_type == "charge.dispute.created":
        await _handle_dispute(event, event_id, db)

    else:
        # Unknown event type — record receipt and return 200 for Stripe compatibility
        await db.execute(
            """
            INSERT INTO payment_event_receipts (provider_event_id, provider, order_id)
            VALUES ($1, 'stripe', NULL)
            ON CONFLICT (provider_event_id) DO NOTHING
            """,
            event_id,
        )

    return {"status": "ok"}


async def _handle_checkout_completed(
    event: dict,
    event_id: str,
    db: asyncpg.Connection,
) -> None:
    """Grant credits after verified checkout.session.completed event."""
    session = event["data"]["object"]
    metadata = session.get("metadata", {})
    order_id_str = metadata.get("order_id")

    if not order_id_str:
        logger.error("checkout.session.completed missing order_id in metadata: %s", event_id)
        return

    try:
        order_id = UUID(order_id_str)
    except ValueError:
        logger.error("Invalid order_id in Stripe metadata: %s", order_id_str)
        return

    payment_intent_id = session.get("payment_intent")

    async with db.transaction():
        # ── Advisory lock: same key as debit_credit() ─────────────────────────
        # Look up user_id first so we can acquire the correct lock
        order_row = await db.fetchrow(
            """
            SELECT id, user_id, credits, status
            FROM credit_purchase_orders
            WHERE id = $1
            FOR UPDATE
            """,
            order_id,
        )

        if not order_row:
            logger.error("Order not found for webhook: %s", order_id)
            return

        if order_row["status"] in TERMINAL_STATES:
            logger.info(
                "Order %s already in terminal state %s — skipping grant",
                order_id,
                order_row["status"],
            )
            # Still record the receipt to prevent re-processing
            await db.execute(
                """
                INSERT INTO payment_event_receipts (provider_event_id, provider, order_id)
                VALUES ($1, 'stripe', $2)
                ON CONFLICT (provider_event_id) DO NOTHING
                """,
                event_id,
                order_id,
            )
            return

        user_id: UUID = order_row["user_id"]
        credits: int = order_row["credits"]

        # Per-user advisory lock — same key as debit_credit() in credits.py
        await db.execute(
            "SELECT pg_advisory_xact_lock(hashtext('credit:' || $1::text))",
            str(user_id),
        )

        # Ensure wallet exists
        await db.execute(
            """
            INSERT INTO user_credit_wallet
                (user_id, daily_grant_credits, daily_used_credits, purchased_credits_balance, wallet_day_au)
            VALUES ($1, 0, 0, 0, CURRENT_DATE)
            ON CONFLICT (user_id) DO NOTHING
            """,
            user_id,
        )

        # Increment purchased credits balance + compute balance_after
        updated = await db.fetchrow(
            """
            UPDATE user_credit_wallet
            SET purchased_credits_balance = purchased_credits_balance + $2,
                updated_at = NOW()
            WHERE user_id = $1
            RETURNING
                GREATEST(0, daily_grant_credits - daily_used_credits)
                    + purchased_credits_balance AS balance_after
            """,
            user_id,
            credits,
        )
        balance_after = int(updated["balance_after"])

        # Write PURCHASE_CREDIT ledger entry (idempotent via idempotency_key)
        idempotency_key = f"purchase:{order_id}:{event_id}"
        await db.execute(
            """
            INSERT INTO credit_ledger
                (user_id, entry_type, delta_credits, balance_after,
                 idempotency_key, related_order_id, metadata)
            VALUES
                ($1, 'PURCHASE_CREDIT', $2, $3, $4, $5, $6::jsonb)
            ON CONFLICT (idempotency_key) DO NOTHING
            """,
            user_id,
            credits,
            balance_after,
            idempotency_key,
            order_id,
            json.dumps({"stripe_event_id": event_id, "payment_intent_id": payment_intent_id}),
        )

        # Transition order to PAID
        await db.execute(
            """
            UPDATE credit_purchase_orders
            SET status = 'PAID',
                provider_payment_intent_id = $2,
                provider_event_id_last = $3,
                paid_at = NOW(),
                updated_at = NOW()
            WHERE id = $1
            """,
            order_id,
            payment_intent_id,
            event_id,
        )

        # Record event receipt (dedup guard)
        await db.execute(
            """
            INSERT INTO payment_event_receipts (provider_event_id, provider, order_id)
            VALUES ($1, 'stripe', $2)
            ON CONFLICT (provider_event_id) DO NOTHING
            """,
            event_id,
            order_id,
        )

    logger.info(
        "Granted %d credits to user %s (order=%s, event=%s)",
        credits,
        user_id,
        order_id,
        event_id,
    )


async def _handle_payment_failed(
    event: dict,
    event_id: str,
    db: asyncpg.Connection,
) -> None:
    """Mark order FAILED on payment_intent.payment_failed — no credits granted.

    Lookup strategy:
    1. Try metadata.order_id (Stripe propagates session metadata to payment_intent)
    2. Fall back to matching by provider_payment_intent_id (for orders that
       already received a checkout.session.completed before failing)
    """
    payment_intent = event["data"]["object"]
    payment_intent_id = payment_intent.get("id")
    metadata = payment_intent.get("metadata", {})
    order_id_str = metadata.get("order_id")

    if not payment_intent_id:
        return

    async with db.transaction():
        if order_id_str:
            # Primary path: match by order_id from metadata
            try:
                order_id = UUID(order_id_str)
            except ValueError:
                order_id = None

            if order_id:
                await db.execute(
                    """
                    UPDATE credit_purchase_orders
                    SET status = 'FAILED',
                        provider_payment_intent_id = $2,
                        provider_event_id_last = $3,
                        updated_at = NOW()
                    WHERE id = $1
                      AND status = 'PENDING'
                    """,
                    order_id,
                    payment_intent_id,
                    event_id,
                )
        else:
            # Fallback: match by provider_payment_intent_id (may be NULL on PENDING orders)
            await db.execute(
                """
                UPDATE credit_purchase_orders
                SET status = 'FAILED',
                    provider_event_id_last = $2,
                    updated_at = NOW()
                WHERE provider_payment_intent_id = $1
                  AND status = 'PENDING'
                """,
                payment_intent_id,
                event_id,
            )

        await db.execute(
            """
            INSERT INTO payment_event_receipts (provider_event_id, provider)
            VALUES ($1, 'stripe')
            ON CONFLICT (provider_event_id) DO NOTHING
            """,
            event_id,
        )

    logger.info("Payment failed for payment_intent %s (event=%s)", payment_intent_id, event_id)


async def _handle_dispute(
    event: dict,
    event_id: str,
    db: asyncpg.Connection,
) -> None:
    """Record dispute — mark order FAILED, NO credit clawback.

    Credits are non-refundable consumables. We record the dispute for
    audit and support purposes only. Wallet balance is not touched.
    """
    charge = event["data"]["object"]
    payment_intent_id = charge.get("payment_intent")

    async with db.transaction():
        if payment_intent_id:
            await db.execute(
                """
                UPDATE credit_purchase_orders
                SET status = 'FAILED',
                    provider_event_id_last = $2,
                    updated_at = NOW()
                WHERE provider_payment_intent_id = $1
                  AND status NOT IN ('FAILED')
                """,
                payment_intent_id,
                event_id,
            )

        await db.execute(
            """
            INSERT INTO payment_event_receipts (provider_event_id, provider)
            VALUES ($1, 'stripe')
            ON CONFLICT (provider_event_id) DO NOTHING
            """,
            event_id,
        )

    logger.warning(
        "Dispute received for payment_intent %s (event=%s) — NO clawback applied",
        payment_intent_id,
        event_id,
    )


# ── Purchase history ──────────────────────────────────────────────────────────


@router.get("/purchases", response_model=PurchaseHistoryResponse)
@limiter.limit("60/minute")
async def get_purchase_history(
    request: Request,
    current_user: UserRow = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> PurchaseHistoryResponse:
    """Return the authenticated user's credit purchase order history.

    Returns order status, amounts, and timestamps only — not ledger entries.
    Use GET /api/credits/me for the current balance.
    """
    rows = await db.fetch(
        """
        SELECT
            id, credits, unit_price_aud_cents, total_amount_aud_cents,
            status, provider, provider_checkout_id,
            created_at, paid_at
        FROM credit_purchase_orders
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT 50
        """,
        current_user.id,
    )

    return PurchaseHistoryResponse(
        items=[
            PurchaseOrderItem(
                id=str(r["id"]),
                credits=r["credits"],
                unit_price_aud_cents=r["unit_price_aud_cents"],
                total_amount_aud_cents=r["total_amount_aud_cents"],
                status=r["status"],
                provider=r["provider"],
                provider_checkout_id=r["provider_checkout_id"],
                created_at=r["created_at"].isoformat(),
                paid_at=r["paid_at"].isoformat() if r["paid_at"] else None,
            )
            for r in rows
        ]
    )
