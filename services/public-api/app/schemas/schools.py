"""Pydantic schemas for school endpoints."""

from __future__ import annotations

from uuid import UUID
from pydantic import BaseModel


class SchoolData(BaseModel):
    id: UUID
    name: str
    address: str | None = None
    suburb: str | None = None
    postcode: str | None = None
    state: str
    school_type: str | None = None
    gender: str | None = None
    sector: str | None = None
    enrolments: int | None = None
    year_range: str | None = None
    website: str | None = None
    phone: str | None = None
