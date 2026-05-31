"""X-Service-Token authentication for the Admin Backend API.

This is the ONLY auth on this service. Clerk verification happens upstream in
the Next.js Server Action before this service is ever reached.

The Admin Backend API is physically unreachable from the internet (ClusterIP only,
NetworkPolicy restricted to admin-web pod).
"""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.config import settings


async def verify_service_token(
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
    x_admin_user_id: str | None = Header(default=None, alias="X-Admin-User-Id"),
) -> str:
    """
    Verifies the shared service token on every request.
    
    Returns the admin user ID (forwarded from Server Action for audit logging).
    If X-Admin-User-Id is missing, returns "unknown".
    """
    if not x_service_token or x_service_token != settings.ADMIN_SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid service token.")
    return x_admin_user_id or "unknown"

