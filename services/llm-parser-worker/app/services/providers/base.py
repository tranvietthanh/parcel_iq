"""Base class for LLM providers."""

from __future__ import annotations

import abc


class LlmProvider(abc.ABC):
    """Abstract base class that all LLM providers must implement."""

    model_name: str

    @abc.abstractmethod
    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 3000,
    ) -> str:
        """Call LLM provider and return assistant content as string.

        Args:
            system_prompt: System-level instructions for the model.
            user_prompt: User prompt containing scraped data and extraction instructions.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in completion response.

        Returns:
            The assistant reply as a plain string (expected to be JSON).
        """
        ...
