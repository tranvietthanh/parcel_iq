"""Tests for the proxy configuration service."""

from __future__ import annotations

from unittest.mock import patch

from app.services.proxy import get_proxy_config


class TestGetProxyConfig:
    """Tests for proxy configuration."""

    @patch("app.services.proxy.settings")
    def test_returns_none_when_no_proxy_url(self, mock_settings):
        mock_settings.PROXY_URL = ""
        assert get_proxy_config() is None

    @patch("app.services.proxy.settings")
    def test_returns_config_when_proxy_set(self, mock_settings):
        mock_settings.PROXY_URL = "http://proxy.example.com:8080"
        mock_settings.PROXY_USERNAME = "user"
        mock_settings.PROXY_PASSWORD = "pass"

        config = get_proxy_config()
        assert config is not None
        assert config["url"] == "http://proxy.example.com:8080"
        assert config["username"] == "user"
        assert config["password"] == "pass"
