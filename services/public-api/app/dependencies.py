"""FastAPI dependency injection functions.

Central location for ``get_db``, ``get_current_user``, ``require_auth``, and
``verify_clerk_token`` — all referenced by routers via ``Depends()``.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import Depends, HTTPException, Request

from app.core.clerk import require_auth, verify_clerk_token  # noqa: F401 (re-export)
from app.core.credits import get_spendable_credits
from app.schemas.user import UserRow


async def get_db(request: Request) -> asyncpg.Connection:
    """Yield a connection from the asyncpg pool for the request lifetime."""
    async with request.app.state.db_pool.acquire() as conn:
        yield conn


async def get_current_user(
    payload: dict = Depends(require_auth),
    db: asyncpg.Connection = Depends(get_db),
) -> UserRow:
    """Look up (or auto-create) the local users row from the JWT sub claim.

    Clerk webhooks (user.created/user.updated) keep the email in sync, but
    they cannot reach localhost during local development. Auto-upsert on first
    auth ensures the row always exists for any holder of a valid Clerk JWT.
    The email is sourced from the JWT ``email`` claim if present; otherwise a
    placeholder is stored and updated when the webhook fires in production.
    """
    clerk_user_id: str | None = payload.get("sub")
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub.")

    row = await db.fetchrow(
        "SELECT id, clerk_user_id, email, created_at FROM users WHERE clerk_user_id = $1",
        clerk_user_id,
    )
    if row:
        return UserRow(**dict(row))

    # Auto-provision: user authenticated with Clerk but has no local row yet.
    # This happens when the webhook hasn't fired (e.g., local dev) or on first
    # request before the webhook is processed.
    email: str = payload.get("email") or f"{clerk_user_id}@noemail.local"

    row = await db.fetchrow(
        """
        INSERT INTO users (clerk_user_id, email)
        VALUES ($1, $2)
        ON CONFLICT (clerk_user_id) DO UPDATE SET email = EXCLUDED.email
        RETURNING id, clerk_user_id, email, created_at
        """,
        clerk_user_id,
        email,
    )

    # Also ensure the credit wallet exists for new users
    from app.core.credits import ensure_wallet_exists
    await ensure_wallet_exists(row["id"], db)

    return UserRow(**dict(row))



async def get_optional_user(
    payload: dict | None = Depends(verify_clerk_token),
    db: asyncpg.Connection = Depends(get_db),
) -> UserRow | None:
    """Return user if authenticated, None otherwise."""
    if not payload:
        return None
    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        return None
    row = await db.fetchrow(
        "SELECT id, clerk_user_id, email, created_at FROM users WHERE clerk_user_id = $1",
        clerk_user_id,
    )
    if not row:
        return None
    return UserRow(**dict(row))


async def require_credits_available(
    current_user: UserRow = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> UserRow:
    """Ensure user has at least 1 spendable credit.

    This is a fast, non-locking pre-flight check. The atomic debit happens
    after successful PDF retrieval in the download endpoint itself.
    """
    spendable = await get_spendable_credits(current_user.id, db)
    if spendable < 1:
        raise HTTPException(
            status_code=403,
            detail=(
                "Insufficient credits. You have 0 spendable credits. "
                "Daily credits reset each day (Australia/Sydney time)."
            ),
        )
    return current_user
