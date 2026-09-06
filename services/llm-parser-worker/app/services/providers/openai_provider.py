"""OpenAI LLM provider implementation."""

from __future__ import annotations

import logging

import requests

from app.services.providers.base import LlmProvider

logger = logging.getLogger(__name__)


class OpenAIClient(LlmProvider):
    """Lightweight OpenAI client using the Chat Completions endpoint.

    The client intentionally keeps the interface small: a single
    `generate_json` method returning the assistant response text.
    """

    def __init__(self, api_key: str, model: str, api_base: str = "https://api.openai.com/v1"):
        self.api_key = api_key or ""
        self.model = model
        self.model_name = model
        self.api_base = api_base.rstrip("/")
        self.session = requests.Session()
        # Set headers when API key is present; requests will still work
        # without an API key (the request will simply fail with 401).
        if self.api_key:
            self.session.headers.update(
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
            )

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 3000,
    ) -> str:
        """Call OpenAI Chat Completions and return assistant content as string.

        Args:
            system_prompt: System-level instructions for the model.
            user_prompt: User prompt containing the scraped data and instructions.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in completion response.

        Returns:
            The assistant reply as a plain string (expected to be JSON).
        """
        url = f"{self.api_base}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "n": 1,
        }

        logger.debug("OpenAI request model=%s size=%d", self.model, len(user_prompt))
        resp = self.session.post(url, json=payload, timeout=300)
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            logger.error("OpenAI API error %s: %s", resp.status_code, resp.text)
            raise

        data = resp.json()
        choice = (data.get("choices") or [None])[0]
        if not choice:
            raise RuntimeError("No choices returned from OpenAI API")

        # Chat Completions: assistant text is under `choice['message']['content']`.
        message = choice.get("message") or {}
        content = message.get("content")
        if content is None:
            # Fall back to older `text` field for compatibility
            content = choice.get("text", "")
        return content
