"""LLM provider registry and factory."""

from __future__ import annotations

from app.config import settings
from app.services.providers.anthropic_provider import AnthropicClient
from app.services.providers.base import LlmProvider
from app.services.providers.google_provider import GoogleAIClient
from app.services.providers.openai_provider import OpenAIClient

LLM_PROVIDER_REGISTRY: dict[str, type[LlmProvider]] = {
    "openai": OpenAIClient,
    "anthropic": AnthropicClient,
    "google": GoogleAIClient,
}


def get_llm_client(provider_name: str | None = None) -> LlmProvider:
    """Instantiate and return the configured LLM provider client."""
    name = (provider_name or settings.LLM_PROVIDER or "openai").lower()
    provider_cls = LLM_PROVIDER_REGISTRY.get(name)

    if provider_cls is None:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider_name or settings.LLM_PROVIDER}")

    if name == "openai":
        return provider_cls(
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_MODEL,
            api_base=settings.OPENAI_BASE_URL,
        )

    if name == "anthropic":
        return provider_cls(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.ANTHROPIC_MODEL,
            api_base=settings.ANTHROPIC_BASE_URL,
        )

    if name == "google":
        return provider_cls(
            api_key=settings.GOOGLE_API_KEY,
            model=settings.GOOGLE_MODEL,
            api_base=settings.GOOGLE_BASE_URL,
        )

    raise ValueError(f"Unknown LLM_PROVIDER: {provider_name or settings.LLM_PROVIDER}")
