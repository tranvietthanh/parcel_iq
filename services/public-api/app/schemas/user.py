"""Pydantic schemas for user endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserSyncRequest(BaseModel):
    """Payload sent by the Clerk webhook (user.created / user.updated)."""

    clerk_user_id: str
    email: EmailStr


class UserSyncResponse(BaseModel):
    synced: bool = True


class UserRow(BaseModel):
    """Internal representation of a local ``users`` table row."""

    id: UUID
    clerk_user_id: str
    email: str
    created_at: datetime


class DeleteResponse(BaseModel):
    deleted: bool = True
