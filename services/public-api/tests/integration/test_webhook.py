"""Integration tests for Stripe webhook processing.

Tests:
- 5.2 Successful payment grant: advisory lock + ledger entry + wallet increment
- 5.3 Webhook replay/idempotency: duplicate event_id ignored
- 5.4 Invalid signature rejection: 400, no mutation
- 5.5 FAILED order on payment failure: no credit grant
- 5.6 Dispute event: order → FAILED, no ledger clawback, wallet unchanged

These tests mock Stripe signature verification and DB calls to run without
a real Stripe account or Postgres instance.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.dependencies import get_db

USER_ID = uuid4()
ORDER_ID = uuid4()


# ── Mock DB ───────────────────────────────────────────────────────────────────


class MockConn:
    def __init__(self):
        self.fetchrow = AsyncMock(return_value=None)
        self.fetchval = AsyncMock(return_value=None)
        self.fetch = AsyncMock(return_value=[])
        self.execute = AsyncMock(return_value="UPDATE 1")

    def transaction(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=None)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_checkout_completed_event(order_id=None, payment_intent_id="pi_test_123", credits=10):
    oid = str(order_id or ORDER_ID)
    return {
        "id": f"evt_test_{oid[:8]}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_abc",
                "payment_intent": payment_intent_id,
                "metadata": {
                    "order_id": oid,
                    "user_id": str(USER_ID),
                    "credits": str(credits),
                },
            }
        },
    }


def make_payment_failed_event(payment_intent_id="pi_test_fail"):
    return {
        "id": "evt_fail_001",
        "type": "payment_intent.payment_failed",
        "data": {"object": {"id": payment_intent_id}},
    }


def make_dispute_event(payment_intent_id="pi_test_dispute"):
    return {
        "id": "evt_dispute_001",
        "type": "charge.dispute.created",
        "data": {"object": {"payment_intent": payment_intent_id}},
    }


def make_order_row(status="PENDING", credits=10):
    row = MagicMock()
    row.__getitem__ = lambda s, k: {
        "id": ORDER_ID,
        "user_id": USER_ID,
        "credits": credits,
        "status": status,
    }[k]
    return row


def make_wallet_row(purchased=5):
    row = MagicMock()
    row.__getitem__ = lambda s, k: {"balance_after": purchased}[k]
    return row


# ── Client fixture ────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    return MockConn()


@pytest.fixture
def webhook_client(mock_db):
    """AsyncClient with real route table but mocked DB and Stripe config."""
    from app.config import settings

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db

    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")

    yield client, mock_db

    app.dependency_overrides.clear()


# ── Task 5.2: Successful payment grant ───────────────────────────────────────


class TestSuccessfulPaymentGrant:
    @pytest.mark.anyio
    async def test_successful_grant_calls_advisory_lock(self, webhook_client):
        """Successful webhook acquires per-user advisory lock before wallet update."""
        client, mock_db = webhook_client

        event = make_checkout_completed_event()
        # No prior receipt → event not yet processed
        mock_db.fetchval.return_value = None
        # fetchrow calls: 1) order FOR UPDATE, 2) wallet UPDATE RETURNING
        mock_db.fetchrow.side_effect = [make_order_row(), make_wallet_row()]

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test"),
            patch("app.config.settings.STRIPE_SECRET_KEY", "sk_test"),
        ):
            resp = await client.post(
                "/api/credits/webhook/stripe",
                content=b"{}",
                headers={"Stripe-Signature": "t=1,v1=fake"},
            )

        assert resp.status_code == 200
        # Advisory lock must be among the execute calls
        execute_calls = [str(c) for c in mock_db.execute.call_args_list]
        lock_acquired = any("pg_advisory_xact_lock" in c and "credit:" in c for c in execute_calls)
        assert lock_acquired, "Advisory lock must be acquired before wallet update"

    @pytest.mark.anyio
    async def test_successful_grant_writes_purchase_credit_ledger(self, webhook_client):
        """Successful webhook writes PURCHASE_CREDIT ledger entry."""
        client, mock_db = webhook_client

        event = make_checkout_completed_event()
        mock_db.fetchval.return_value = None
        mock_db.fetchrow.side_effect = [make_order_row(), make_wallet_row()]

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test"),
            patch("app.config.settings.STRIPE_SECRET_KEY", "sk_test"),
        ):
            resp = await client.post(
                "/api/credits/webhook/stripe",
                content=b"{}",
                headers={"Stripe-Signature": "t=1,v1=fake"},
            )

        assert resp.status_code == 200
        execute_calls = [str(c) for c in mock_db.execute.call_args_list]
        ledger_written = any("PURCHASE_CREDIT" in c for c in execute_calls)
        assert ledger_written, "PURCHASE_CREDIT ledger entry must be written"

    @pytest.mark.anyio
    async def test_successful_grant_updates_purchased_balance(self, webhook_client):
        """Successful webhook increments purchased_credits_balance."""
        client, mock_db = webhook_client

        event = make_checkout_completed_event(credits=10)
        mock_db.fetchval.return_value = None
        mock_db.fetchrow.side_effect = [make_order_row(credits=10), make_wallet_row()]

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test"),
            patch("app.config.settings.STRIPE_SECRET_KEY", "sk_test"),
        ):
            resp = await client.post(
                "/api/credits/webhook/stripe",
                content=b"{}",
                headers={"Stripe-Signature": "t=1,v1=fake"},
            )

        assert resp.status_code == 200
        execute_calls = [str(c) for c in mock_db.execute.call_args_list]
        balance_updated = any(
            "purchased_credits_balance = purchased_credits_balance + " in c for c in execute_calls
        )
        assert balance_updated, "purchased_credits_balance must be incremented"


# ── Task 5.3: Replay / idempotency ───────────────────────────────────────────


class TestWebhookIdempotency:
    @pytest.mark.anyio
    async def test_duplicate_event_id_is_ignored(self, webhook_client):
        """Already-processed event_id returns 200 without granting credits."""
        client, mock_db = webhook_client

        event = make_checkout_completed_event()
        # Simulate: event already in payment_event_receipts
        mock_db.fetchval.return_value = 1

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test"),
            patch("app.config.settings.STRIPE_SECRET_KEY", "sk_test"),
        ):
            resp = await client.post(
                "/api/credits/webhook/stripe",
                content=b"{}",
                headers={"Stripe-Signature": "t=1,v1=fake"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "already_processed"
        # No credit grant should have been issued
        execute_calls = [str(c) for c in mock_db.execute.call_args_list]
        assert not any("PURCHASE_CREDIT" in c for c in execute_calls), (
            "Duplicate event must NOT write a ledger entry"
        )

    @pytest.mark.anyio
    async def test_terminal_order_not_regranted(self, webhook_client):
        """Order in PAID state is not granted credits again."""
        client, mock_db = webhook_client

        event = make_checkout_completed_event()
        mock_db.fetchval.return_value = None  # event not in receipts yet
        # Order already PAID (terminal)
        mock_db.fetchrow.return_value = make_order_row(status="PAID")

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test"),
            patch("app.config.settings.STRIPE_SECRET_KEY", "sk_test"),
        ):
            resp = await client.post(
                "/api/credits/webhook/stripe",
                content=b"{}",
                headers={"Stripe-Signature": "t=1,v1=fake"},
            )

        assert resp.status_code == 200
        execute_calls = [str(c) for c in mock_db.execute.call_args_list]
        assert not any("purchased_credits_balance = purchased_credits_balance +" in c for c in execute_calls), (
            "Terminal order must not receive another credit grant"
        )


# ── Task 5.4: Invalid signature ───────────────────────────────────────────────


class TestInvalidSignature:
    @pytest.mark.anyio
    async def test_invalid_signature_returns_400(self, webhook_client):
        """Stripe signature verification failure returns 400."""
        import stripe
        client, mock_db = webhook_client

        with (
            patch(
                "stripe.Webhook.construct_event",
                side_effect=stripe.SignatureVerificationError("bad sig", "sig_header"),
            ),
            patch("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test"),
            patch("app.config.settings.STRIPE_SECRET_KEY", "sk_test"),
        ):
            resp = await client.post(
                "/api/credits/webhook/stripe",
                content=b"{}",
                headers={"Stripe-Signature": "t=1,v1=tampered"},
            )

        assert resp.status_code == 400
        assert "Invalid signature" in resp.json().get("detail", "")

    @pytest.mark.anyio
    async def test_invalid_signature_no_db_mutation(self, webhook_client):
        """Signature failure must not mutate order or wallet."""
        import stripe
        client, mock_db = webhook_client

        with (
            patch(
                "stripe.Webhook.construct_event",
                side_effect=stripe.SignatureVerificationError("bad sig", "sig_header"),
            ),
            patch("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test"),
            patch("app.config.settings.STRIPE_SECRET_KEY", "sk_test"),
        ):
            await client.post(
                "/api/credits/webhook/stripe",
                content=b"{}",
                headers={"Stripe-Signature": "t=1,v1=tampered"},
            )

        # No DB writes should have occurred
        mock_db.execute.assert_not_called()
        mock_db.fetchrow.assert_not_called()


# ── Task 5.5: Payment failure ─────────────────────────────────────────────────


class TestPaymentFailure:
    @pytest.mark.anyio
    async def test_payment_failed_event_transitions_to_failed(self, webhook_client):
        """payment_intent.payment_failed event marks order FAILED, no credit grant."""
        client, mock_db = webhook_client

        event = make_payment_failed_event()
        mock_db.fetchval.return_value = None  # not yet in receipts

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test"),
            patch("app.config.settings.STRIPE_SECRET_KEY", "sk_test"),
        ):
            resp = await client.post(
                "/api/credits/webhook/stripe",
                content=b"{}",
                headers={"Stripe-Signature": "t=1,v1=fake"},
            )

        assert resp.status_code == 200
        execute_calls = [str(c) for c in mock_db.execute.call_args_list]
        # Must update order to FAILED
        failed_update = any("FAILED" in c and "credit_purchase_orders" in c for c in execute_calls)
        assert failed_update, "Order must be marked FAILED on payment failure"
        # Must NOT grant credits
        no_credit_grant = not any("PURCHASE_CREDIT" in c for c in execute_calls)
        assert no_credit_grant, "No PURCHASE_CREDIT entry on payment failure"


# ── Task 5.6: Dispute / chargeback ───────────────────────────────────────────


class TestDisputeHandling:
    @pytest.mark.anyio
    async def test_dispute_marks_order_failed(self, webhook_client):
        """charge.dispute.created marks order FAILED for audit."""
        client, mock_db = webhook_client

        event = make_dispute_event()
        mock_db.fetchval.return_value = None

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test"),
            patch("app.config.settings.STRIPE_SECRET_KEY", "sk_test"),
        ):
            resp = await client.post(
                "/api/credits/webhook/stripe",
                content=b"{}",
                headers={"Stripe-Signature": "t=1,v1=fake"},
            )

        assert resp.status_code == 200
        execute_calls = [str(c) for c in mock_db.execute.call_args_list]
        failed_update = any("FAILED" in c and "credit_purchase_orders" in c for c in execute_calls)
        assert failed_update, "Order must be marked FAILED on dispute"

    @pytest.mark.anyio
    async def test_dispute_no_clawback(self, webhook_client):
        """charge.dispute.created must NOT write a negative ledger entry."""
        client, mock_db = webhook_client

        event = make_dispute_event()
        mock_db.fetchval.return_value = None

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test"),
            patch("app.config.settings.STRIPE_SECRET_KEY", "sk_test"),
        ):
            await client.post(
                "/api/credits/webhook/stripe",
                content=b"{}",
                headers={"Stripe-Signature": "t=1,v1=fake"},
            )

        execute_calls = [str(c) for c in mock_db.execute.call_args_list]
        # No wallet mutation (purchased_credits_balance should not be decremented)
        no_wallet_debit = not any(
            "purchased_credits_balance = purchased_credits_balance -" in c for c in execute_calls
        )
        assert no_wallet_debit, "Dispute must NOT debit purchased_credits_balance (no clawback)"
        # No DOWNLOAD_DEBIT or compensating ledger entry
        no_ledger_clawback = not any(
            "DOWNLOAD_DEBIT" in c or "delta_credits" in c for c in execute_calls
        )
        assert no_ledger_clawback, "Dispute must NOT write any ledger entry"

    @pytest.mark.anyio
    async def test_dispute_records_receipt(self, webhook_client):
        """Dispute event is recorded in payment_event_receipts for dedup."""
        client, mock_db = webhook_client

        event = make_dispute_event()
        mock_db.fetchval.return_value = None

        with (
            patch("stripe.Webhook.construct_event", return_value=event),
            patch("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test"),
            patch("app.config.settings.STRIPE_SECRET_KEY", "sk_test"),
        ):
            await client.post(
                "/api/credits/webhook/stripe",
                content=b"{}",
                headers={"Stripe-Signature": "t=1,v1=fake"},
            )

        execute_calls = [str(c) for c in mock_db.execute.call_args_list]
        receipt_written = any("payment_event_receipts" in c for c in execute_calls)
        assert receipt_written, "Dispute event must be recorded in payment_event_receipts"
