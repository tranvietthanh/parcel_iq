"""User endpoints — Clerk webhook sync + account deletion.

POST   /api/users/sync                  — Clerk webhook (user.created / user.updated)
DELETE /api/users/sync/{clerk_user_id}  — Clerk webhook (user.deleted)
DELETE /api/users/me                    — self-initiated deletion (Privacy Act 1988)

On user deletion, the FK cascade (ON DELETE CASCADE) on user_credit_wallet and
credit_ledger ensures credit data is removed. saved_properties is deleted
explicitly first to avoid FK constraint issues.
"""

from __future__ import annotations

import asyncpg
import hmac
from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.schemas.user import DeleteResponse, UserRow, UserSyncRequest, UserSyncResponse

router = APIRouter(tags=["users"])


@router.post("/sync", response_model=UserSyncResponse)
async def sync_user(
    body: UserSyncRequest,
    x_webhook_secret: str = Header(alias="X-Webhook-Secret"),
    db: asyncpg.Connection = Depends(get_db),
) -> UserSyncResponse:
    """Sync a Clerk user into the local ``users`` table.

    Called by the Next.js public-web webhook route when Clerk fires
    ``user.created`` or ``user.updated``.

    Also ensures a credit wallet row is created for the user on first sync.
    """
    if not hmac.compare_digest(x_webhook_secret, settings.INTERNAL_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid webhook secret.")

    await db.execute(
        """INSERT INTO users (clerk_user_id, email)
           VALUES ($1, $2)
           ON CONFLICT (clerk_user_id) DO UPDATE SET email = EXCLUDED.email""",
        body.clerk_user_id,
        body.email,
    )

    # Ensure credit wallet exists for new users (idempotent)
    user_id = await db.fetchval(
        "SELECT id FROM users WHERE clerk_user_id = $1",
        body.clerk_user_id,
    )
    if user_id:
        await db.execute(
            """
            INSERT INTO user_credit_wallet
                (user_id, daily_grant_credits, daily_used_credits, purchased_credits_balance, wallet_day_au)
            VALUES ($1, 0, 0, 0, CURRENT_DATE)
            ON CONFLICT (user_id) DO NOTHING
            """,
            user_id,
        )

    return UserSyncResponse()


@router.delete("/sync/{clerk_user_id}", response_model=DeleteResponse)
async def delete_user_by_webhook(
    clerk_user_id: str,
    x_webhook_secret: str = Header(alias="X-Webhook-Secret"),
    db: asyncpg.Connection = Depends(get_db),
) -> DeleteResponse:
    """Delete a user triggered by Clerk's ``user.deleted`` webhook event.

    Removes saved_properties explicitly; user_credit_wallet and credit_ledger
    cascade via FK ON DELETE CASCADE.
    """
    if not hmac.compare_digest(x_webhook_secret, settings.INTERNAL_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid webhook secret.")

    await db.execute(
        "DELETE FROM saved_properties WHERE user_id = (SELECT id FROM users WHERE clerk_user_id = $1)",
        clerk_user_id,
    )
    await db.execute("DELETE FROM users WHERE clerk_user_id = $1", clerk_user_id)
    return DeleteResponse()


@router.delete("/me", response_model=DeleteResponse)
async def delete_account(
    current_user: UserRow = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> DeleteResponse:
    """Delete the authenticated user's account and associated data.

    Required by the **Privacy Act 1988 (Cth)** — right to erasure.

    Cascade: user_credit_wallet and credit_ledger rows are deleted via
    FK ON DELETE CASCADE when the users row is removed.
    """
    # Delete saved properties (no cascade from users)
    await db.execute(
        "DELETE FROM saved_properties WHERE user_id = $1",
        current_user.id,
    )
    # Delete user row — cascades to user_credit_wallet, credit_ledger, property_reports (requested_by_user_id SET NULL)
    await db.execute("DELETE FROM users WHERE id = $1", current_user.id)
    return DeleteResponse()
