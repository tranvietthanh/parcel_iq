"""Unit tests for Anthropic provider adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.services.providers.anthropic_provider import AnthropicClient
from app.services.providers.base import LlmProvider


class TestAnthropicProvider:
    def test_implements_llm_provider(self) -> None:
        """AnthropicClient must inherit from LlmProvider and expose model_name."""
        client = AnthropicClient(
            api_key="test-key",
            model="claude-3-5-sonnet-20241022",
            api_base="https://api.anthropic.com/v1",
        )
        assert isinstance(client, LlmProvider)
        assert client.model_name == "claude-3-5-sonnet-20241022"

    @patch("requests.Session.post")
    def test_request_payload_and_header_auth(self, mock_post: MagicMock) -> None:
        """API key must be sent via x-api-key header and system prompt as top-level field."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": '{"result": "success"}'}],
        }
        mock_post.return_value = mock_resp

        client = AnthropicClient(
            api_key="sk-ant-test-key-12345",
            model="claude-3-5-sonnet-20241022",
        )
        result = client.generate_json(
            system_prompt="You are a property analyst.",
            user_prompt="Analyze 123 Fake St.",
            max_tokens=4096,
        )

        assert result == '{"result": "success"}'
        mock_post.assert_called_once()
        call_args, call_kwargs = mock_post.call_args

        # URL should not contain any query parameters
        url = call_args[0]
        assert url == "https://api.anthropic.com/v1/messages"
        assert "?" not in url

        # Header check: key must be present in header
        headers = call_kwargs["headers"]
        assert headers["x-api-key"] == "sk-ant-test-key-12345"
        assert headers["anthropic-version"] == "2023-06-01"
        assert headers["content-type"] == "application/json"

        # Body check: system prompt must be top-level
        payload = call_kwargs["json"]
        assert payload["model"] == "claude-3-5-sonnet-20241022"
        assert payload["system"] == "You are a property analyst."
        assert payload["messages"] == [{"role": "user", "content": "Analyze 123 Fake St."}]
        assert payload["max_tokens"] == 4096

    @patch("requests.Session.post")
    def test_truncation_raises_provider_truncated(self, mock_post: MagicMock) -> None:
        """stop_reason=max_tokens must raise PROVIDER_TRUNCATED error."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "stop_reason": "max_tokens",
            "content": [{"type": "text", "text": '{"incomplete": "js'}]
        }
        mock_post.return_value = mock_resp

        client = AnthropicClient(api_key="test-key", model="claude-model")
        with pytest.raises(
            RuntimeError, match="PROVIDER_TRUNCATED: anthropic stop_reason=max_tokens"
        ):
            client.generate_json("system", "user")

    @patch("requests.Session.post")
    def test_missing_content_raises_provider_no_content(self, mock_post: MagicMock) -> None:
        """Missing or empty text content blocks must raise PROVIDER_NO_CONTENT."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "stop_reason": "end_turn",
            "content": [],
        }
        mock_post.return_value = mock_resp

        client = AnthropicClient(api_key="test-key", model="claude-model")
        with pytest.raises(
            RuntimeError, match="PROVIDER_NO_CONTENT: anthropic stop_reason=end_turn"
        ):
            client.generate_json("system", "user")

    @patch("requests.Session.post")
    def test_http_error_does_not_leak_api_key(self, mock_post: MagicMock) -> None:
        """HTTP error exceptions must not embed the secret API key."""
        secret_key = "sk-ant-secret1234567890abcdef"
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Rate limit exceeded"
        mock_resp.raise_for_status.side_effect = requests.HTTPError(
            "429 Client Error: Rate limit exceeded for url: https://api.anthropic.com/v1/messages"
        )
        mock_post.return_value = mock_resp

        client = AnthropicClient(api_key=secret_key, model="claude-model")
        with pytest.raises(requests.HTTPError) as exc_info:
            client.generate_json("system", "user")

        assert secret_key not in str(exc_info.value)

    @patch("requests.Session.post")
    def test_concatenates_multiple_text_blocks(self, mock_post: MagicMock) -> None:
        """Multiple text content blocks should be concatenated into a single string."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "stop_reason": "end_turn",
            "content": [
                {"type": "text", "text": '{"chunk1": true, '},
                {"type": "text", "text": '"chunk2": true}'},
            ],
        }
        mock_post.return_value = mock_resp

        client = AnthropicClient(api_key="test-key", model="claude-3-5-sonnet-20241022")
        result = client.generate_json("system", "user")
        assert result == '{"chunk1": true, "chunk2": true}'

