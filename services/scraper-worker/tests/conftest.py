"""Shared test fixtures and helpers."""

from __future__ import annotations

import pytest


@pytest.fixture()
def sample_job() -> dict:
    """A standard job dict for adapter tests."""
    return {
        "property_id": "550e8400-e29b-41d4-a716-446655440000",
        "gnaf_pid": "GAVIC411711364",
        "address_string": "1 Smith Street, Melbourne VIC 3000",
        "latitude": -37.8136,
        "longitude": 144.9631,
        "lga_name": "Melbourne",
        "state": "VIC",
    }
