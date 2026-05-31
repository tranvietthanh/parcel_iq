import pytest


def test_health_endpoint_no_auth(client):
    """Health endpoint should work without auth."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_stats_endpoint_no_auth(client):
    """Stats endpoint should require auth."""
    response = client.get("/stats")
    assert response.status_code == 401  # Missing service token



def test_stats_endpoint_with_auth(client, auth_headers, mock_db):
    """Stats endpoint should return data with valid auth."""
    # Mock database response
    mock_db.fetchrow.return_value = {
        "total_properties": 1000,
        "reports_ready": 800,
        "awaiting_review": 50,
        "failed_7d": 10,
        "lga_coverage": 25,
        "sales_mtd": 100,
        "revenue_mtd": 5000.0,
    }

    response = client.get("/stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_properties"] == 1000
    assert data["reports_ready"] == 800
