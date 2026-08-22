"""Tests for robots.txt compliance checker."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.utils.robots import is_scraping_allowed


class TestRobotsCompliance:
    """Tests for robots.txt checking."""

    def setup_method(self):
        """Clear the robots cache between tests."""
        from app.utils import robots

        robots._robots_cache.clear()

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
    def test_disallows_when_fetch_fails(self, mock_get: MagicMock):
        # Fail closed: if we can't verify the policy, we must not scrape.
        mock_get.side_effect = Exception("connection failed")

        assert is_scraping_allowed("https://example.com", "/search") is False

    @patch("app.utils.robots.httpx.get")
    def test_disallows_on_server_error(self, mock_get: MagicMock):
        # 5xx means the policy is unknown — fail closed.
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = ""
        mock_get.return_value = mock_resp

        assert is_scraping_allowed("https://example.com", "/search") is False

    def test_allows_empty_base_url(self):
        assert is_scraping_allowed("", "/") is True
