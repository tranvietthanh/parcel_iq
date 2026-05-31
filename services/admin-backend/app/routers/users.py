"""Admin users router — list, detail, and top-up credit mutation.

GET  /users           — paginated user list with credit summary
GET  /users/{user_id} — user profile + wallet + recent ledger
POST /users/{user_id}/credits/top-up — manual credit top-up

All endpoints require X-Service-Token (enforced in verify_service_token).
Top-up actor identity is sourced from the X-Admin-User-Id header (Clerk admin user ID).
"""

from __future__ import annotations

from uuid import UUID

from asyncpg import Connection
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, field_validator

from app.core.service_auth import verify_service_token
from app.dependencies import get_db

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(verify_service_token)],
)

# ── Max top-up guard ──────────────────────────────────────────────────────────
MAX_TOPUP_CREDITS = 10_000


# ── Request / Response models ─────────────────────────────────────────────────

class TopUpRequest(BaseModel):
    credits: int
    reason: str

    @field_validator("credits")
    @classmethod
    def credits_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("credits must be a positive integer")
        if v > MAX_TOPUP_CREDITS:
            raise ValueError(f"credits cannot exceed {MAX_TOPUP_CREDITS} per top-up operation")
        return v

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("reason must not be empty")
        return v


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_users(
    db: Connection = Depends(get_db),
    page: int = 1,
    page_size: int = 25,
    search: str | None = None,
) -> dict:
    """Paginated user list with credit summary fields.

    Supports search/filter by email or clerk_user_id prefix.
    """
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 25
    offset = (page - 1) * page_size

    search_clause = ""
    params: list = [page_size, offset]
    if search:
        params.append(f"%{search}%")
        idx = len(params)
        search_clause = f"WHERE u.email ILIKE ${idx} OR u.clerk_user_id ILIKE ${idx}"

    rows = await db.fetch(
        f"""
        SELECT
            u.id,
            u.clerk_user_id,
            u.email,
            u.created_at,
            COALESCE(w.daily_grant_credits - w.daily_used_credits, 0) AS daily_remaining,
            COALESCE(w.purchased_credits_balance, 0)                  AS purchased_balance,
            COALESCE(
                GREATEST(0, w.daily_grant_credits - w.daily_used_credits)
                + w.purchased_credits_balance, 0
            )                                                          AS total_spendable
        FROM users u
        LEFT JOIN user_credit_wallet w ON w.user_id = u.id
        {search_clause}
        ORDER BY u.created_at DESC
        LIMIT $1 OFFSET $2
        """,
        *params,
    )

    count_params: list = []
    count_clause = ""
    if search:
        count_params.append(f"%{search}%")
        count_clause = "WHERE email ILIKE $1 OR clerk_user_id ILIKE $1"

    total_count = await db.fetchval(
        f"SELECT COUNT(*) FROM users {count_clause}",
        *count_params,
    )

    return {
        "items": [
            {
                "id": str(r["id"]),
                "clerk_user_id": r["clerk_user_id"],
                "email": r["email"],
                "created_at": r["created_at"].isoformat(),
                "daily_remaining": max(0, int(r["daily_remaining"])),
                "purchased_balance": int(r["purchased_balance"]),
                "total_spendable": max(0, int(r["total_spendable"])),
            }
            for r in rows
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total_count or 0,
            "total_pages": max(1, ((total_count or 0) + page_size - 1) // page_size),
        },
    }


@router.get("/{user_id}")
async def get_user_detail(
    user_id: UUID,
    db: Connection = Depends(get_db),
) -> dict:
    """User profile + wallet summary + 50 most recent credit ledger entries."""
    user_row = await db.fetchrow(
        """
        SELECT u.id, u.clerk_user_id, u.email, u.created_at,
               w.daily_grant_credits,
               w.daily_used_credits,
               GREATEST(0, w.daily_grant_credits - w.daily_used_credits) AS daily_remaining,
               w.purchased_credits_balance,
               GREATEST(0, w.daily_grant_credits - w.daily_used_credits)
                   + w.purchased_credits_balance AS total_spendable,
               w.wallet_day_au,
               w.updated_at AS wallet_updated_at
        FROM users u
        LEFT JOIN user_credit_wallet w ON w.user_id = u.id
        WHERE u.id = $1
        """,
        user_id,
    )
    if not user_row:
        raise HTTPException(status_code=404, detail="User not found.")

    ledger_rows = await db.fetch(
        """
        SELECT id, entry_type, delta_credits, balance_after,
               related_property_id, metadata, created_at
        FROM credit_ledger
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT 50
        """,
        user_id,
    )

    return {
        "id": str(user_row["id"]),
        "clerk_user_id": user_row["clerk_user_id"],
        "email": user_row["email"],
        "created_at": user_row["created_at"].isoformat(),
        "wallet": {
            "daily_grant": int(user_row["daily_grant_credits"] or 0),
            "daily_used": int(user_row["daily_used_credits"] or 0),
            "daily_remaining": max(0, int(user_row["daily_remaining"] or 0)),
            "purchased_balance": int(user_row["purchased_credits_balance"] or 0),
            "total_spendable": max(0, int(user_row["total_spendable"] or 0)),
            "wallet_day_au": user_row["wallet_day_au"].isoformat() if user_row["wallet_day_au"] else None,
            "wallet_updated_at": user_row["wallet_updated_at"].isoformat() if user_row["wallet_updated_at"] else None,
        },
        "recent_ledger": [
            {
                "id": str(r["id"]),
                "entry_type": r["entry_type"],
                "delta_credits": r["delta_credits"],
                "balance_after": r["balance_after"],
                "related_property_id": str(r["related_property_id"]) if r["related_property_id"] else None,
                "metadata": r["metadata"] if r["metadata"] else {},

                "created_at": r["created_at"].isoformat(),
            }
            for r in ledger_rows
        ],
    }


@router.post("/{user_id}/credits/top-up")
async def top_up_user_credits(
    user_id: UUID,
    body: TopUpRequest,
    db: Connection = Depends(get_db),
    x_admin_user_id: str = Header(..., alias="X-Admin-User-Id", description="Clerk admin user ID of the operator"),
) -> dict:
    """Manually top up purchased credits for a user.

    Writes an immutable ADMIN_TOPUP ledger entry with actor ID, reason, and
    timestamp. Updates the wallet's purchased_credits_balance atomically.
    """
    # Verify user exists
    user_row = await db.fetchrow("SELECT id FROM users WHERE id = $1", user_id)
    if not user_row:
        raise HTTPException(status_code=404, detail="User not found.")

    async with db.transaction():
        # Advisory lock on user credits
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

        # Update purchased balance and compute balance_after
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
            body.credits,
        )

        balance_after = int(updated["balance_after"])

        # Write immutable ledger entry
        await db.execute(
            """
            INSERT INTO credit_ledger
                (user_id, entry_type, delta_credits, balance_after, metadata)
            VALUES
                ($1, 'ADMIN_TOPUP', $2, $3, $4::jsonb)
            """,
            user_id,
            body.credits,
            balance_after,
            {
                "reason": body.reason,
                "actor_admin_id": x_admin_user_id,
            },
        )

    return {
        "success": True,
        "credits_added": body.credits,
        "new_balance_after": balance_after,
        "reason": body.reason,
        "actor_admin_id": x_admin_user_id,
    }
