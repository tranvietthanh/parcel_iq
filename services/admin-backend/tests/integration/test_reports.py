import pytest
from uuid import uuid4
from unittest.mock import MagicMock


def test_list_reports(client, auth_headers, mock_db):
    """List reports endpoint should return paginated results."""
    mock_db.fetch.return_value = [
        {
            "id": str(uuid4()),
            "property_id": str(uuid4()),
            "property_address": "123 Test St, Melbourne VIC",
            "status": "READY",
            "overall_confidence": "HIGH",
            "updated_at": "2024-01-01T00:00:00",
            "state": "VIC",
        }
    ]

    response = client.get("/reports", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "READY"



def test_delete_report_pdf_cache_all_modes(client, auth_headers, mock_db, monkeypatch):
    """Delete report PDF cache should remove both full and lite variants by default."""
    report_id = str(uuid4())
    property_id = str(uuid4())
    mock_db.fetchrow.return_value = {
        "report_id": report_id,
        "property_id": property_id,
    }

    mock_delete_pdf = MagicMock()
    monkeypatch.setattr("app.routers.reports.delete_report_pdf", mock_delete_pdf)

    response = client.delete(f"/reports/{report_id}/pdf", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["report_id"] == report_id
    assert data["property_id"] == property_id
    assert data["mode"] == "all"
    assert sorted(data["deleted"]) == ["full", "lite"]
    assert mock_delete_pdf.call_count == 2


def test_delete_report_pdf_cache_not_found(client, auth_headers, mock_db):
    """Delete report PDF cache should return 404 when report does not exist."""
    report_id = str(uuid4())
    mock_db.fetchrow.return_value = None

    response = client.delete(f"/reports/{report_id}/pdf", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Report not found"
