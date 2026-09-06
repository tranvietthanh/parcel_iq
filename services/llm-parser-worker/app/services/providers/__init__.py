"""LLM provider registry and factory."""

from __future__ import annotations

from app.config import settings
from app.services.providers.base import LlmProvider
from app.services.providers.openai_provider import OpenAIClient

LLM_PROVIDER_REGISTRY: dict[str, type[LlmProvider]] = {
    "openai": OpenAIClient,
    # "anthropic": AnthropicClient,  # added in Phase 2
    # "google": GoogleAIClient,      # added in Phase 2
}


def get_llm_client() -> LlmProvider:
    """Instantiate and return the configured LLM provider client."""
    provider_name = settings.LLM_PROVIDER.lower() if settings.LLM_PROVIDER else "openai"

    if provider_name == "openai":
        provider_cls = LLM_PROVIDER_REGISTRY.get("openai")
        if provider_cls is None:
            raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")
        return provider_cls(
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_MODEL,
            api_base=settings.OPENAI_BASE_URL,
        )

    if provider_name in ("anthropic", "google"):
        raise NotImplementedError(
            f"LLM_PROVIDER={settings.LLM_PROVIDER} not yet implemented (Phase 2)"
        )

    raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")
