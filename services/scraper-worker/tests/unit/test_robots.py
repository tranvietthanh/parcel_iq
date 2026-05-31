"""Tests for robots.txt compliance checker."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.utils.robots import is_scraping_allowed


class TestRobotsCompliance:
    """Tests for robots.txt checking."""

    def setup_method(self):
        """Clear the LRU cache between tests."""
        from app.utils.robots import _fetch_robots

        _fetch_robots.cache_clear()

    @patch("app.utils.robots.httpx.get")
    def test_allows_when_no_restriction(self, mock_get: MagicMock):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "User-agent: *\nAllow: /"
        mock_get.return_value = mock_resp

        assert is_scraping_allowed("https://example.com", "/search") is True

    @patch("app.utils.robots.httpx.get")
    def test_disallows_when_blocked(self, mock_get: MagicMock):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "User-agent: *\nDisallow: /"
        mock_get.return_value = mock_resp

        assert is_scraping_allowed("https://example.com", "/search") is False

    @patch("app.utils.robots.httpx.get")
    def test_allows_when_robots_not_found(self, mock_get: MagicMock):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = ""
        mock_get.return_value = mock_resp

        assert is_scraping_allowed("https://example.com", "/search") is True

    @patch("app.utils.robots.httpx.get")
    def test_allows_when_fetch_fails(self, mock_get: MagicMock):
        mock_get.side_effect = Exception("connection failed")

        assert is_scraping_allowed("https://example.com", "/search") is True

    def test_allows_empty_base_url(self):
        assert is_scraping_allowed("", "/") is True
