"""Tests for base adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.adapters.base import BaseAdapter


class ConcreteAdapter(BaseAdapter):
    """Concrete implementation for testing."""

    def scrape(self, job: dict) -> dict:
        return {"test": True}


class TestBaseAdapter:
    """Tests for the BaseAdapter abstract class."""

    def test_concrete_adapter_scrape(self, sample_job: dict):
        adapter = ConcreteAdapter()
        result = adapter.scrape(sample_job)
        assert result == {"test": True}

    def test_adapter_stores_base_url_and_config(self):
        adapter = ConcreteAdapter(
            base_url="https://example.com",
            config={"key": "value"},
        )
        assert adapter.base_url == "https://example.com"
        assert adapter.config == {"key": "value"}

    def test_adapter_defaults(self):
        adapter = ConcreteAdapter()
        assert adapter.base_url == ""
        assert adapter.config == {}

    @patch("app.adapters.base.httpx.request")
    def test_fetch_json_success(self, mock_request: MagicMock):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": "test"}
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        adapter = ConcreteAdapter()
        result = adapter.fetch_json("https://api.example.com/data")
        assert result == {"data": "test"}
        
        # Verify it was called with default GET method
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["method"] == "GET"
        assert call_kwargs["url"] == "https://api.example.com/data"

    @patch("app.adapters.base.httpx.request")
    def test_fetch_json_retries_on_failure(self, mock_request: MagicMock):
        mock_request.side_effect = [
            Exception("timeout"),
            Exception("timeout"),
            MagicMock(
                json=MagicMock(return_value={"ok": True}),
                raise_for_status=MagicMock(),
            ),
        ]

        adapter = ConcreteAdapter()
        result = adapter.fetch_json("https://api.example.com/data")
        assert result == {"ok": True}
        assert mock_request.call_count == 3
