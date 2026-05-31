import pytest
from uuid import uuid4


def test_list_data_sources(client, auth_headers, mock_db):
    """List data sources should return all configs."""
    mock_db.fetch.return_value = [
        {
            "id": str(uuid4()),
            "state": "VIC",
            "lga_name": "Melbourne",
            "adapter_name": "VictoriaPlanningAdapter",
            "base_url": "https://example.com",
            "adapter_config": {},
            "enabled": True,
            "test_status": None,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        }
    ]

    response = client.get("/data-sources", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["state"] == "VIC"


def test_create_data_source(client, auth_headers, mock_db):
    """Create data source should validate LGA exists."""
    # Mock LGA exists check
    mock_db.fetchval.side_effect = [True, None]  # LGA exists, no duplicate
    mock_db.fetchrow.return_value = {
        "id": str(uuid4()),
        "state": "VIC",
        "lga_name": "Melbourne",
        "adapter_name": "VictoriaPlanningAdapter",
        "base_url": "https://example.com",
        "adapter_config": {},
        "enabled": True,
        "test_status": None,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    }

    response = client.post(
        "/data-sources",
        headers=auth_headers,
        json={
            "state": "VIC",
            "lga_name": "Melbourne",
            "adapter_name": "VictoriaPlanningAdapter",
            "base_url": "https://example.com",
            "enabled": True,
        },
    )
    assert response.status_code == 201


def test_update_data_source(client, auth_headers, mock_db):
    """Update data source should accept partial updates."""
    config_id = str(uuid4())
    mock_db.execute.return_value = "UPDATE 1"
    mock_db.fetchrow.return_value = {
        "id": config_id,
        "state": "VIC",
        "lga_name": "Melbourne",
        "adapter_name": "VictoriaPlanningAdapter",
        "base_url": "https://new-url.com",
        "adapter_config": {},
        "enabled": False,
        "test_status": None,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-02T00:00:00",
    }

    response = client.patch(
        f"/data-sources/{config_id}",
        headers=auth_headers,
        json={"enabled": False, "base_url": "https://new-url.com"},
    )
    assert response.status_code == 200


def test_delete_data_source(client, auth_headers, mock_db):
    """Delete data source should succeed."""
    config_id = str(uuid4())
    mock_db.execute.return_value = "DELETE 1"

    response = client.delete(f"/data-sources/{config_id}", headers=auth_headers)
    assert response.status_code == 204
