"""Anthropic LLM provider implementation."""

from __future__ import annotations

import logging

import requests

from app.services.providers.base import LlmProvider

logger = logging.getLogger(__name__)


class AnthropicClient(LlmProvider):
    """Anthropic Messages API client."""

    def __init__(self, api_key: str, model: str, api_base: str = "https://api.anthropic.com/v1"):
        self.api_key = api_key or ""
        self.model = model
        self.model_name = model
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
        """Call Anthropic Messages API and return assistant content as string.

        Args:
            system_prompt: System-level instructions for the model.
            user_prompt: User prompt containing scraped data and extraction instructions.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in completion response (default 8192).

        Returns:
            The assistant reply as a plain string (expected to be JSON).
        """
        url = f"{self.api_base}/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": temperature,
        }

        logger.debug("Anthropic request model=%s size=%d", self.model_name, len(user_prompt))
        resp = self.session.post(url, headers=headers, json=payload, timeout=300)
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            logger.error("Anthropic API error %s: %s", resp.status_code, resp.text)
            raise

        data = resp.json()
        stop_reason = data.get("stop_reason")
        if stop_reason == "max_tokens":
            raise RuntimeError(
                "PROVIDER_TRUNCATED: anthropic stop_reason=max_tokens "
                "(raise max_tokens or shrink prompt)"
            )

        blocks = data.get("content") or []
        text = "".join(
            b.get("text", "")
            for b in blocks
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text")
        ) or None
        if not text:
            raise RuntimeError(f"PROVIDER_NO_CONTENT: anthropic stop_reason={stop_reason}")

        return text
