"""Google AI (Gemini) LLM provider implementation."""

from __future__ import annotations

import logging

import requests

from app.services.providers.base import LlmProvider

logger = logging.getLogger(__name__)


class GoogleAIClient(LlmProvider):
    """Google Gemini REST API client using generateContent endpoint."""

    def __init__(
        self,
        api_key: str,
        model: str,
        api_base: str = "https://generativelanguage.googleapis.com/v1beta",
    ):
        self.api_key = api_key or ""
        self.model = model
        self.model_name = model.removeprefix("models/")
        self.api_base = api_base.rstrip("/")
        self.session = requests.Session()

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 8192,
    ) -> str:
        """Call Gemini generateContent API and return assistant content as string.

        Args:
            system_prompt: System-level instructions for the model.
            user_prompt: User prompt containing scraped data and extraction instructions.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in completion response (default 8192).

        Returns:
            The assistant reply as a plain string (expected to be JSON).
        """
        url = f"{self.api_base}/models/{self.model_name}:generateContent"
        # Security critical: API key must only be passed in header, never as URL query parameter
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "response_mime_type": "application/json",
            },
        }

        logger.debug("Google AI request model=%s size=%d", self.model_name, len(user_prompt))
        resp = self.session.post(url, headers=headers, json=payload, timeout=300)
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            logger.error("Google AI API error %s: %s", resp.status_code, resp.text)
            raise

        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            block_reason = (data.get("promptFeedback") or {}).get("blockReason")
            raise RuntimeError(f"PROVIDER_NO_CANDIDATES: google blockReason={block_reason}")

        first_candidate = candidates[0] or {}
        finish_reason = first_candidate.get("finishReason")
        if finish_reason == "MAX_TOKENS":
            raise RuntimeError("PROVIDER_TRUNCATED: google finishReason=MAX_TOKENS")

        content = first_candidate.get("content") or {}
        parts = content.get("parts") or []
        text = "".join(
            p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")
        ) or None
        if not text:
            raise RuntimeError(f"PROVIDER_NO_CONTENT: google finishReason={finish_reason}")

        return text
