"""Unit tests for Google AI (Gemini) provider adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.services.providers.base import LlmProvider
from app.services.providers.google_provider import GoogleAIClient


class TestGoogleAIProvider:
    def test_implements_llm_provider(self) -> None:
        """GoogleAIClient must inherit from LlmProvider and expose model_name."""
        client = GoogleAIClient(
            api_key="test-key",
            model="gemini-1.5-pro",
            api_base="https://generativelanguage.googleapis.com/v1beta",
        )
        assert isinstance(client, LlmProvider)
        assert client.model_name == "gemini-1.5-pro"

    @patch("requests.Session.post")
    def test_request_payload_and_header_auth(self, mock_post: MagicMock) -> None:
        """API key must be sent via x-goog-api-key header and NOT as URL query param."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": '{"zoning": "GRZ1"}'}],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }
            ]
        }
        mock_post.return_value = mock_resp

        secret_key = "AIzaSyD-secret-key-12345"
        client = GoogleAIClient(
            api_key=secret_key,
            model="gemini-1.5-pro",
        )
        result = client.generate_json(
            system_prompt="Extract property insights.",
            user_prompt="Address: 123 Sample Rd",
        )

        assert result == '{"zoning": "GRZ1"}'
        mock_post.assert_called_once()
        call_args, call_kwargs = mock_post.call_args

        # Security check: URL must NOT contain the API key as query parameter
        url = call_args[0]
        assert url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent"
        assert "?" not in url
        assert "key=" not in url
        assert secret_key not in url

        # Header check: key must be present in header
        headers = call_kwargs["headers"]
        assert headers["x-goog-api-key"] == secret_key
        assert headers["Content-Type"] == "application/json"

        # Payload check: native JSON mode and system instruction
        payload = call_kwargs["json"]
        assert payload["system_instruction"] == {"parts": [{"text": "Extract property insights."}]}
        assert payload["contents"] == [
            {"role": "user", "parts": [{"text": "Address: 123 Sample Rd"}]}
        ]
        assert payload["generationConfig"]["response_mime_type"] == "application/json"

    @patch("requests.Session.post")
    def test_safety_block_raises_provider_no_candidates(self, mock_post: MagicMock) -> None:
        """Blocked response with empty candidates raises PROVIDER_NO_CANDIDATES."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [],
            "promptFeedback": {"blockReason": "SAFETY"},
        }
        mock_post.return_value = mock_resp

        client = GoogleAIClient(api_key="test-key", model="gemini-model")
        with pytest.raises(
            RuntimeError, match="PROVIDER_NO_CANDIDATES: google blockReason=SAFETY"
        ):
            client.generate_json("system", "user")

    @patch("requests.Session.post")
    def test_truncation_raises_provider_truncated(self, mock_post: MagicMock) -> None:
        """finishReason=MAX_TOKENS must raise PROVIDER_TRUNCATED."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {"parts": [{"text": '{"broken": '}]},
                    "finishReason": "MAX_TOKENS",
                }
            ]
        }
        mock_post.return_value = mock_resp

        client = GoogleAIClient(api_key="test-key", model="gemini-model")
        with pytest.raises(
            RuntimeError, match="PROVIDER_TRUNCATED: google finishReason=MAX_TOKENS"
        ):
            client.generate_json("system", "user")

    @patch("requests.Session.post")
    def test_missing_parts_raises_provider_no_content(self, mock_post: MagicMock) -> None:
        """Candidate missing text parts must raise PROVIDER_NO_CONTENT."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {"parts": []},
                    "finishReason": "STOP",
                }
            ]
        }
        mock_post.return_value = mock_resp

        client = GoogleAIClient(api_key="test-key", model="gemini-model")
        with pytest.raises(RuntimeError, match="PROVIDER_NO_CONTENT: google finishReason=STOP"):
            client.generate_json("system", "user")

    @patch("requests.Session.post")
    def test_http_error_does_not_leak_api_key(self, mock_post: MagicMock) -> None:
        """HTTP error exceptions must not embed the secret API key."""
        secret_key = "AIzaSyD-very-secret-google-key"
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Permission denied"
        mock_resp.raise_for_status.side_effect = requests.HTTPError(
            "403 Client Error: Permission denied for url: "
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent"
        )
        mock_post.return_value = mock_resp

        client = GoogleAIClient(api_key=secret_key, model="gemini-1.5-pro")
        with pytest.raises(requests.HTTPError) as exc_info:
            client.generate_json("system", "user")

        assert secret_key not in str(exc_info.value)

    @patch("requests.Session.post")
    def test_strips_models_prefix(self, mock_post: MagicMock) -> None:
        """models/ prefix in model name must be stripped to prevent /models/models/ URLs."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {"parts": [{"text": "{}"}]},
                    "finishReason": "STOP",
                }
            ]
        }
        mock_post.return_value = mock_resp

        client = GoogleAIClient(api_key="test-key", model="models/gemini-1.5-flash")
        assert client.model_name == "gemini-1.5-flash"
        client.generate_json("system", "user")

        call_args, _ = mock_post.call_args
        url = call_args[0]
        assert "/models/models/" not in url
        assert url.endswith("/models/gemini-1.5-flash:generateContent")

    @patch("requests.Session.post")
    def test_concatenates_multiple_parts(self, mock_post: MagicMock) -> None:
        """Multiple content parts should be concatenated into a single string."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": '{"chunk1": true, '},
                            {"text": '"chunk2": true}'},
                        ]
                    },
                    "finishReason": "STOP",
                }
            ]
        }
        mock_post.return_value = mock_resp

        client = GoogleAIClient(api_key="test-key", model="gemini-1.5-pro")
        result = client.generate_json("system", "user")
        assert result == '{"chunk1": true, "chunk2": true}'

