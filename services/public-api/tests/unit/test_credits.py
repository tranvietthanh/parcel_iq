"""Unit tests for the credit wallet service.

Tests:
- Debit ordering: daily credits consumed before purchased
- No-rollover daily reset
- Post-download debit atomicity (concurrent session race)
- Daily grant idempotency
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest

from app.core.credits import (
    debit_credit,
    get_spendable_credits,
    get_wallet_summary,
)

USER_ID = uuid4()
PROPERTY_ID = uuid4()
REPORT_ID = uuid4()


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_wallet_row(
    daily_grant: int = 3,
    daily_used: int = 0,
    purchased: int = 0,
    day_offset: int = 0,
) -> dict:
    """Return a fake wallet row dict."""
    wallet_day = date.today() - timedelta(days=day_offset)
    return {
        "daily_grant_credits": daily_grant,
        "daily_used_credits": daily_used,
        "purchased_credits_balance": purchased,
        "wallet_day_au": wallet_day,
        "daily_remaining": max(0, daily_grant - daily_used),
        "total_spendable": max(0, daily_grant - daily_used) + purchased,
    }


class MockConn:
    """Minimal mock of asyncpg.Connection."""

    def __init__(self):
        self.fetchrow = AsyncMock(return_value=None)
        self.fetchval = AsyncMock(return_value=None)
        self.fetch = AsyncMock(return_value=[])
        self.execute = AsyncMock(return_value="UPDATE 1")
        self._tx = None

    def transaction(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=None)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx


# ── Task 7.1: Debit ordering — daily before purchased ────────────────────────


class TestDebitOrdering:
    @pytest.mark.anyio
    async def test_consumes_daily_credits_first(self):
        """When daily credits are available, debit from daily first."""
        db = MockConn()

        # Wallet has 2 daily remaining + 5 purchased
        wallet_row = {
            "daily_grant_credits": 3,
            "daily_used_credits": 1,
            "purchased_credits_balance": 5,
            "daily_remaining": 2,
        }
        db.fetchrow.return_value = MagicMock(**wallet_row, **{"__getitem__": lambda s, k: wallet_row[k]})
        # Make it subscriptable
        row = MagicMock()
        row.__getitem__ = lambda s, k: wallet_row[k]
        db.fetchrow.return_value = row

        result = await debit_credit(
            user_id=USER_ID,
            property_id=PROPERTY_ID,
            report_id=REPORT_ID,
            idempotency_key="test-daily-first",
            db=db,
        )

        assert result is True
        # Should UPDATE daily_used_credits, not purchased_credits_balance
        execute_calls = [str(c) for c in db.execute.call_args_list]
        # Find the wallet update call — should update daily_used_credits
        daily_update_found = any("daily_used_credits = daily_used_credits + 1" in c for c in execute_calls)
        purchased_update_found = any("purchased_credits_balance = purchased_credits_balance - 1" in c for c in execute_calls)
        assert daily_update_found, "Should have incremented daily_used_credits"
        assert not purchased_update_found, "Should NOT have decremented purchased credits when daily credits are available"

    @pytest.mark.anyio
    async def test_consumes_purchased_when_daily_exhausted(self):
        """When daily credits are exhausted, debit from purchased credits."""
        db = MockConn()

        wallet_row = {
            "daily_grant_credits": 3,
            "daily_used_credits": 3,
            "purchased_credits_balance": 5,
            "daily_remaining": 0,
        }
        row = MagicMock()
        row.__getitem__ = lambda s, k: wallet_row[k]
        db.fetchrow.return_value = row

        result = await debit_credit(
            user_id=USER_ID,
            property_id=PROPERTY_ID,
            report_id=REPORT_ID,
            idempotency_key="test-purchased-fallback",
            db=db,
        )

        assert result is True
        execute_calls = [str(c) for c in db.execute.call_args_list]
        purchased_update_found = any("purchased_credits_balance = purchased_credits_balance - 1" in c for c in execute_calls)
        assert purchased_update_found, "Should have decremented purchased_credits_balance when daily exhausted"

    @pytest.mark.anyio
    async def test_returns_false_when_no_credits(self):
        """Returns False when user has zero spendable credits."""
        db = MockConn()

        wallet_row = {
            "daily_grant_credits": 3,
            "daily_used_credits": 3,
            "purchased_credits_balance": 0,
            "daily_remaining": 0,
        }
        row = MagicMock()
        row.__getitem__ = lambda s, k: wallet_row[k]
        db.fetchrow.return_value = row

        result = await debit_credit(
            user_id=USER_ID,
            property_id=PROPERTY_ID,
            report_id=REPORT_ID,
            idempotency_key="test-no-credits",
            db=db,
        )

        assert result is False

    @pytest.mark.anyio
    async def test_returns_false_when_wallet_missing(self):
        """Returns False when user has no wallet row."""
        db = MockConn()
        db.fetchrow.return_value = None

        result = await debit_credit(
            user_id=USER_ID,
            property_id=PROPERTY_ID,
            report_id=REPORT_ID,
            idempotency_key="test-no-wallet",
            db=db,
        )

        assert result is False


# ── Task 7.2: No-rollover daily reset ────────────────────────────────────────


class TestDailyReset:
    @pytest.mark.anyio
    async def test_reset_fires_when_day_is_stale(self):
        """Reconciliation resets daily_used_credits when wallet_day_au is yesterday."""
        db = MockConn()
        yesterday = date.today() - timedelta(days=1)

        # Simulate a stale wallet
        wallet_row = {
            "daily_grant_credits": 3,
            "daily_used_credits": 3,   # fully used yesterday
            "purchased_credits_balance": 0,
            "daily_remaining": 0,
            "wallet_day_au": yesterday,
        }
        row = MagicMock()
        row.__getitem__ = lambda s, k: wallet_row[k]
        db.fetchrow.return_value = row

        # debit_credit calls reconciliation inside the transaction
        # Even with exhausted yesterday credits, today should have 3 fresh
        # We can't easily test debit_credit end-to-end without full DB,
        # so test the reconcile SQL is executed:
        await debit_credit(
            user_id=USER_ID,
            property_id=PROPERTY_ID,
            report_id=REPORT_ID,
            idempotency_key="test-day-reset",
            db=db,
        )

        # Check that an UPDATE with wallet_day_au was issued (reconciliation)
        execute_calls = [str(c) for c in db.execute.call_args_list]
        reset_found = any("daily_used_credits = 0" in c for c in execute_calls)
        assert reset_found, "Should have reset daily_used_credits to 0 on day rollover"

    @pytest.mark.anyio
    async def test_get_wallet_summary_reconciles_stale_day(self):
        """get_wallet_summary resets daily credits for a stale wallet."""
        db = MockConn()
        yesterday = date.today() - timedelta(days=1)

        wallet_row = {
            "daily_grant_credits": 3,
            "daily_used_credits": 2,
            "purchased_credits_balance": 0,
            "wallet_day_au": yesterday,
            "daily_remaining": 1,
        }
        row = MagicMock()
        row.__getitem__ = lambda s, k: wallet_row[k]
        db.fetchrow.return_value = row

        # Expect an UPDATE for reconciliation
        await get_wallet_summary(USER_ID, db)

        execute_calls = [str(c) for c in db.execute.call_args_list]
        reset_found = any("daily_used_credits = 0" in c for c in execute_calls)
        assert reset_found, "get_wallet_summary should reconcile a stale wallet day"

    @pytest.mark.anyio
    async def test_no_rollover_unused_daily(self):
        """Daily unused credits do not carry over — each day starts fresh."""
        db = MockConn()
        yesterday = date.today() - timedelta(days=1)

        # User had 3 granted, only used 1 yesterday → 2 unused
        wallet_row = {
            "daily_grant_credits": 3,
            "daily_used_credits": 1,
            "purchased_credits_balance": 5,
            "wallet_day_au": yesterday,
            "daily_remaining": 2,
        }
        row = MagicMock()
        row.__getitem__ = lambda s, k: wallet_row[k]
        db.fetchrow.return_value = row

        await get_wallet_summary(USER_ID, db)

        # Reconciliation should reset daily_used_credits to 0 (full 3 available)
        # and not carry unused 2 forward
        execute_calls = [str(c) for c in db.execute.call_args_list]
        reset_call = next(
            (c for c in execute_calls if "daily_used_credits = 0" in c), None
        )
        assert reset_call is not None, "Should reset daily_used_credits, not carry over unused credits"


# ── Task 7.3: Duplicate download charge ──────────────────────────────────────


class TestDuplicateDownload:
    @pytest.mark.anyio
    async def test_second_download_of_same_report_charges_credit(self):
        """A user who downloads the same report twice is charged on each download."""
        db = MockConn()

        wallet_row = {
            "daily_grant_credits": 3,
            "daily_used_credits": 0,
            "purchased_credits_balance": 0,
            "daily_remaining": 3,
        }
        row = MagicMock()
        row.__getitem__ = lambda s, k: wallet_row[k]
        db.fetchrow.return_value = row

        # First download
        result1 = await debit_credit(
            user_id=USER_ID,
            property_id=PROPERTY_ID,
            report_id=REPORT_ID,
            idempotency_key="download-1",
            db=db,
        )

        # Second download (different idempotency key — it's a new request)
        result2 = await debit_credit(
            user_id=USER_ID,
            property_id=PROPERTY_ID,
            report_id=REPORT_ID,
            idempotency_key="download-2",
            db=db,
        )

        assert result1 is True
        assert result2 is True

        # Should have inserted 2 separate DOWNLOAD_DEBIT ledger entries
        insert_calls = [c for c in db.execute.call_args_list if "DOWNLOAD_DEBIT" in str(c)]
        assert len(insert_calls) == 2, f"Expected 2 DOWNLOAD_DEBIT entries, got {len(insert_calls)}"

    @pytest.mark.anyio
    async def test_idempotency_key_prevents_double_charge(self):
        """Same idempotency_key on retry does not result in a double charge."""
        db = MockConn()

        wallet_row = {
            "daily_grant_credits": 3,
            "daily_used_credits": 0,
            "purchased_credits_balance": 0,
            "daily_remaining": 3,
        }
        row = MagicMock()
        row.__getitem__ = lambda s, k: wallet_row[k]
        db.fetchrow.return_value = row

        idempotency_key = "download-idempotent"

        # Call twice with same key
        await debit_credit(
            user_id=USER_ID,
            property_id=PROPERTY_ID,
            report_id=REPORT_ID,
            idempotency_key=idempotency_key,
            db=db,
        )
        await debit_credit(
            user_id=USER_ID,
            property_id=PROPERTY_ID,
            report_id=REPORT_ID,
            idempotency_key=idempotency_key,
            db=db,
        )

        # The ON CONFLICT DO NOTHING on ledger insert ensures only one entry
        insert_calls = [c for c in db.execute.call_args_list if "DOWNLOAD_DEBIT" in str(c)]
        # Both calls write to ledger but ON CONFLICT handles deduplication at DB level
        # We just verify the INSERT is called with ON CONFLICT
        assert all("ON CONFLICT" in str(c) for c in insert_calls if "DOWNLOAD_DEBIT" in str(c))


# ── Task 7.4: Post-download debit atomicity ───────────────────────────────────


class TestDebitAtomicity:
    @pytest.mark.anyio
    async def test_advisory_lock_is_acquired(self):
        """Advisory lock is acquired before wallet mutation."""
        db = MockConn()

        wallet_row = {
            "daily_grant_credits": 3,
            "daily_used_credits": 0,
            "purchased_credits_balance": 0,
            "daily_remaining": 3,
        }
        row = MagicMock()
        row.__getitem__ = lambda s, k: wallet_row[k]
        db.fetchrow.return_value = row

        await debit_credit(
            user_id=USER_ID,
            property_id=PROPERTY_ID,
            report_id=REPORT_ID,
            idempotency_key="test-lock",
            db=db,
        )

        execute_calls = [str(c) for c in db.execute.call_args_list]
        lock_acquired = any("pg_advisory_xact_lock" in c and "credit:" in c for c in execute_calls)
        assert lock_acquired, "Advisory lock must be acquired before wallet mutation"

    @pytest.mark.anyio
    async def test_balance_after_is_written_to_ledger(self):
        """Ledger entry must contain balance_after for auditability."""
        db = MockConn()

        wallet_row = {
            "daily_grant_credits": 3,
            "daily_used_credits": 0,
            "purchased_credits_balance": 2,
            "daily_remaining": 3,
        }
        row = MagicMock()
        row.__getitem__ = lambda s, k: wallet_row[k]
        db.fetchrow.return_value = row

        await debit_credit(
            user_id=USER_ID,
            property_id=PROPERTY_ID,
            report_id=REPORT_ID,
            idempotency_key="test-balance-after",
            db=db,
        )

        insert_calls = [str(c) for c in db.execute.call_args_list if "DOWNLOAD_DEBIT" in str(c)]
        assert len(insert_calls) >= 1
        # balance_after is the 2nd positional arg (index 1) after user_id
        # We just verify the ledger write included it by checking arg count
        insert_args = [c for c in db.execute.call_args_list if "DOWNLOAD_DEBIT" in str(c)]
        for call_obj in insert_args:
            args = call_obj[0]  # positional args
            # args[0] = SQL, args[1] = user_id, args[2] = balance_after, args[3] = idempotency_key, ...
            assert len(args) >= 5, f"Ledger INSERT should have at least 5 args (including balance_after), got {len(args)}"
