"""Credit wallet service.

Handles:
- Wallet reconciliation (AU day reset, no rollover)
- Spendable credit reads
- Post-download atomic debit (daily credits first, then purchased)

Debit model: credit is subtracted ONLY after successful PDF retrieval.
No refund mechanism exists — the debit is final once committed.

Advisory lock key: pg_advisory_xact_lock(hashtext('credit:' || user_id::text))
Lock is held only during the brief wallet update + ledger write, NOT during
PDF generation.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from uuid import UUID

import asyncpg
from zoneinfo import ZoneInfo

SYDNEY_TZ = ZoneInfo("Australia/Sydney")

# Default daily grant — overridden by DAILY_CREDIT_GRANT env var at startup
_DEFAULT_DAILY_GRANT: int = 3


def get_daily_grant_amount() -> int:
    """Return the configured daily free-credit grant amount."""
    import os
    try:
        return int(os.environ.get("DAILY_CREDIT_GRANT", _DEFAULT_DAILY_GRANT))
    except (TypeError, ValueError):
        return _DEFAULT_DAILY_GRANT


def _today_au() -> date:
    return datetime.now(SYDNEY_TZ).date()


def _advisory_lock_key(user_id: UUID) -> int:
    """Stable int key for per-user advisory lock.

    Uses hashtext-equivalent via Python so the value matches
    pg_advisory_xact_lock(hashtext('credit:' || user_id::text)).
    In practice we pass the raw string and let Postgres hash it.
    """
    # We pass the string directly in SQL using hashtext(); this helper
    # is here for documentation purposes only.
    return int(hashlib.md5(f"credit:{user_id}".encode()).hexdigest()[:8], 16)


async def get_wallet(
    user_id: UUID,
    db: asyncpg.Connection,
) -> asyncpg.Record | None:
    """Fetch raw wallet row for a user."""
    return await db.fetchrow(
        "SELECT * FROM user_credit_wallet WHERE user_id = $1",
        user_id,
    )


async def get_spendable_credits(
    user_id: UUID,
    db: asyncpg.Connection,
) -> int:
    """Return total spendable credits (daily remaining + purchased)."""
    row = await db.fetchrow(
        """
        SELECT
            GREATEST(0, daily_grant_credits - daily_used_credits) AS daily_remaining,
            purchased_credits_balance
        FROM user_credit_wallet
        WHERE user_id = $1
        """,
        user_id,
    )
    if not row:
        return 0
    return int(row["daily_remaining"]) + int(row["purchased_credits_balance"])


async def ensure_wallet_exists(
    user_id: UUID,
    db: asyncpg.Connection,
) -> None:
    """Create wallet row if not present (idempotent)."""
    daily_grant = get_daily_grant_amount()
    await db.execute(
        """
        INSERT INTO user_credit_wallet
            (user_id, daily_grant_credits, daily_used_credits, purchased_credits_balance, wallet_day_au)
        VALUES ($1, $2, 0, 0, $3)
        ON CONFLICT (user_id) DO NOTHING
        """,
        user_id,
        daily_grant,
        _today_au(),
    )


async def _reconcile_day(
    user_id: UUID,
    today: date,
    db: asyncpg.Connection,
) -> None:
    """Reset daily credits if the wallet day has rolled over.

    Must be called inside an advisory-locked transaction.
    """
    daily_grant = get_daily_grant_amount()
    await db.execute(
        """
        UPDATE user_credit_wallet
        SET
            wallet_day_au      = $2,
            daily_grant_credits = $3,
            daily_used_credits  = 0,
            updated_at          = NOW()
        WHERE user_id = $1
          AND wallet_day_au < $2
        """,
        user_id,
        today,
        daily_grant,
    )


async def get_wallet_summary(
    user_id: UUID,
    db: asyncpg.Connection,
) -> dict:
    """Return wallet summary for the /credits/me endpoint.

    Reconciles the day inline (non-locking read then update if stale).
    """
    today = _today_au()
    # Ensure wallet exists
    await ensure_wallet_exists(user_id, db)

    # Reconcile day if stale (best-effort, no lock needed for summary reads)
    daily_grant = get_daily_grant_amount()
    await db.execute(
        """
        UPDATE user_credit_wallet
        SET wallet_day_au = $2, daily_grant_credits = $3, daily_used_credits = 0, updated_at = NOW()
        WHERE user_id = $1 AND wallet_day_au < $2
        """,
        user_id,
        today,
        daily_grant,
    )

    row = await db.fetchrow(
        """
        SELECT
            daily_grant_credits,
            daily_used_credits,
            purchased_credits_balance,
            wallet_day_au,
            GREATEST(0, daily_grant_credits - daily_used_credits) AS daily_remaining
        FROM user_credit_wallet
        WHERE user_id = $1
        """,
        user_id,
    )
    if not row:
        return {
            "daily_remaining": 0,
            "daily_grant": daily_grant,
            "purchased_balance": 0,
            "total_spendable": 0,
        }
    daily_remaining = int(row["daily_remaining"])
    purchased = int(row["purchased_credits_balance"])
    return {
        "daily_remaining": daily_remaining,
        "daily_grant": int(row["daily_grant_credits"]),
        "purchased_balance": purchased,
        "total_spendable": daily_remaining + purchased,
    }


async def debit_credit(
    user_id: UUID,
    property_id: UUID,
    report_id: UUID,
    idempotency_key: str,
    db: asyncpg.Connection,
) -> bool:
    """Atomically debit 1 credit after successful PDF retrieval.

    Consumes daily credits first, then purchased credits.
    Returns True on success, False if insufficient credits (race condition).

    Must be called AFTER the PDF has been successfully retrieved/generated.
    The debit is final once committed — no refund mechanism exists.
    """
    today = _today_au()
    daily_grant = get_daily_grant_amount()

    async with db.transaction():
        # Per-user advisory lock — held only during this brief transaction
        await db.execute(
            "SELECT pg_advisory_xact_lock(hashtext('credit:' || $1::text))",
            str(user_id),
        )

        # Reconcile day if rolled over
        await db.execute(
            """
            UPDATE user_credit_wallet
            SET wallet_day_au = $2, daily_grant_credits = $3, daily_used_credits = 0, updated_at = NOW()
            WHERE user_id = $1 AND wallet_day_au < $2
            """,
            user_id,
            today,
            daily_grant,
        )

        # Read current wallet state (inside lock)
        row = await db.fetchrow(
            """
            SELECT
                daily_grant_credits,
                daily_used_credits,
                purchased_credits_balance,
                GREATEST(0, daily_grant_credits - daily_used_credits) AS daily_remaining
            FROM user_credit_wallet
            WHERE user_id = $1
            FOR UPDATE
            """,
            user_id,
        )
        if not row:
            return False

        daily_remaining = int(row["daily_remaining"])
        purchased = int(row["purchased_credits_balance"])
        total_spendable = daily_remaining + purchased

        if total_spendable < 1:
            return False  # Concurrent session drained credits

        # Determine debit source: daily first, then purchased
        if daily_remaining >= 1:
            # Consume from daily
            await db.execute(
                """
                UPDATE user_credit_wallet
                SET daily_used_credits = daily_used_credits + 1, updated_at = NOW()
                WHERE user_id = $1
                """,
                user_id,
            )
            new_purchased = purchased
        else:
            # Consume from purchased
            await db.execute(
                """
                UPDATE user_credit_wallet
                SET purchased_credits_balance = purchased_credits_balance - 1, updated_at = NOW()
                WHERE user_id = $1
                """,
                user_id,
            )
            new_purchased = purchased - 1

        balance_after = (total_spendable - 1)

        # Write immutable ledger entry
        await db.execute(
            """
            INSERT INTO credit_ledger
                (user_id, entry_type, delta_credits, balance_after,
                 idempotency_key, related_property_id, related_report_id, metadata)
            VALUES
                ($1, 'DOWNLOAD_DEBIT', -1, $2, $3, $4, $5, $6)
            ON CONFLICT (idempotency_key) DO NOTHING
            """,
            user_id,
            balance_after,
            idempotency_key,
            property_id,
            report_id,
            "{}",
        )

    return True


async def grant_daily_credits(
    user_id: UUID,
    db: asyncpg.Connection,
) -> None:
    """Ensure daily grant ledger entry exists for today.

    Called during wallet reconciliation to record the grant in the ledger.
    Idempotent via idempotency_key.
    """
    today = _today_au()
    daily_grant = get_daily_grant_amount()
    idempotency_key = f"daily_grant:{user_id}:{today.isoformat()}"

    # Only write the ledger entry if reconciliation actually reset the day
    exists = await db.fetchval(
        "SELECT 1 FROM credit_ledger WHERE idempotency_key = $1",
        idempotency_key,
    )
    if exists:
        return

    # Compute balance after grant
    row = await db.fetchrow(
        """
        SELECT
            GREATEST(0, daily_grant_credits - daily_used_credits) + purchased_credits_balance AS spendable
        FROM user_credit_wallet
        WHERE user_id = $1
        """,
        user_id,
    )
    balance_after = int(row["spendable"]) if row else daily_grant

    await db.execute(
        """
        INSERT INTO credit_ledger
            (user_id, entry_type, delta_credits, balance_after, idempotency_key, metadata)
        VALUES
            ($1, 'DAILY_GRANT', $2, $3, $4, '{}')
        ON CONFLICT (idempotency_key) DO NOTHING
        """,
        user_id,
        daily_grant,
        balance_after,
        idempotency_key,
    )
