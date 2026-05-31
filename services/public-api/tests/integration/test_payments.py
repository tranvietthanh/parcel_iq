"""DECOMMISSIONED — test_payments.py

The payments router (/api/payments) has been removed as part of the
credit-based-downloads change. These tests are preserved as tombstones
to document the removed surface area.

Replacement:
  - tests/integration/test_credits.py — wallet summary + precheck endpoints
  - tests/unit/test_credits.py       — debit service unit tests

To verify the endpoint is gone:
"""

from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_payments_status_endpoint_removed(authed_client):
    """Verify /api/payments/status/{id} no longer exists (decommissioned)."""
    from uuid import uuid4
    client, _, _ = authed_client
    prop_id = uuid4()
    resp = await client.get(f"/api/payments/status/{prop_id}")
    assert resp.status_code == 404, (
        f"/api/payments/status was decommissioned. Expected 404, got {resp.status_code}"
    )


@pytest.mark.anyio
async def test_payments_subscribe_endpoint_removed(authed_client):
    """Verify /api/payments/subscribe no longer exists."""
    client, _, _ = authed_client
    resp = await client.post("/api/payments/subscribe", json={"tier": "PRO"})
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_payments_portal_endpoint_removed(authed_client):
    """Verify /api/payments/portal no longer exists."""
    client, _, _ = authed_client
    resp = await client.get("/api/payments/portal")
    assert resp.status_code == 404
