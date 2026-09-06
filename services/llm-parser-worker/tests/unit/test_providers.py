"""Unit tests for LLM provider abstraction, registry, and configuration."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services.providers import LLM_PROVIDER_REGISTRY, get_llm_client
from app.services.providers.base import LlmProvider
from app.services.providers.openai_provider import OpenAIClient


class TestLlmProviders:
    def test_registry_contains_openai(self) -> None:
        """OpenAIClient should be registered in LLM_PROVIDER_REGISTRY."""
        assert "openai" in LLM_PROVIDER_REGISTRY
        assert issubclass(LLM_PROVIDER_REGISTRY["openai"], LlmProvider)

    def test_get_llm_client_default_openai(self) -> None:
        """Default provider should return an OpenAIClient with model_name set."""
        with patch("app.services.providers.settings.LLM_PROVIDER", "openai"), \
             patch("app.services.providers.settings.OPENAI_MODEL", "test-model-42"):
            client = get_llm_client()
            assert isinstance(client, OpenAIClient)
            assert isinstance(client, LlmProvider)
            assert client.model_name == "test-model-42"

    def test_get_llm_client_anthropic_placeholder_raises(self) -> None:
        """Setting LLM_PROVIDER=anthropic should raise NotImplementedError in Phase 1."""
        with patch("app.services.providers.settings.LLM_PROVIDER", "anthropic"):
            with pytest.raises(NotImplementedError, match="Phase 2"):
                get_llm_client()

    def test_get_llm_client_google_placeholder_raises(self) -> None:
        """Setting LLM_PROVIDER=google should raise NotImplementedError in Phase 1."""
        with patch("app.services.providers.settings.LLM_PROVIDER", "google"):
            with pytest.raises(NotImplementedError, match="Phase 2"):
                get_llm_client()

    def test_get_llm_client_unknown_provider_raises(self) -> None:
        """Setting an unknown LLM_PROVIDER should raise ValueError."""
        with patch("app.services.providers.settings.LLM_PROVIDER", "unsupported_provider"):
            with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
                get_llm_client()

    def test_llm_client_reexport_shim(self) -> None:
        """app.services.llm_client should re-export llm_client as an LlmProvider."""
        from app.services.llm_client import llm_client

        assert isinstance(llm_client, LlmProvider)
        assert hasattr(llm_client, "model_name")
        assert callable(getattr(llm_client, "generate_json"))


class TestProviderConfig:
    def test_llm_max_rpm_validation(self) -> None:
        """LLM_MAX_RPM must be >= 1 to prevent division by zero in rate limiter."""
        with pytest.raises(ValidationError):
            Settings(LLM_MAX_RPM=0)

        with pytest.raises(ValidationError):
            Settings(LLM_MAX_RPM=-5)

        s = Settings(LLM_MAX_RPM=1)
        assert s.LLM_MAX_RPM == 1

    def test_production_validator_branches_on_provider(self) -> None:
        """Production validation checks the key matching the configured LLM_PROVIDER."""
        # Development environment skips key checks
        dev = Settings(
            ENVIRONMENT="development",
            LLM_PROVIDER="openai",
            OPENAI_API_KEY="",
        )
        assert dev.ENVIRONMENT == "development"

        # Production with openai requires OPENAI_API_KEY
        with pytest.raises(ValueError, match="OPENAI_API_KEY is not set"):
            Settings(
                ENVIRONMENT="production",
                DATABASE_URL="postgresql+psycopg2://user:secret@localhost:5432/db",
                LLM_PROVIDER="openai",
                OPENAI_API_KEY="",
            )

        # Production with anthropic requires ANTHROPIC_API_KEY
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY is not set"):
            Settings(
                ENVIRONMENT="production",
                DATABASE_URL="postgresql+psycopg2://user:secret@localhost:5432/db",
                LLM_PROVIDER="anthropic",
                ANTHROPIC_API_KEY="",
            )

        # Production with google requires GOOGLE_API_KEY
        with pytest.raises(ValueError, match="GOOGLE_API_KEY is not set"):
            Settings(
                ENVIRONMENT="production",
                DATABASE_URL="postgresql+psycopg2://user:secret@localhost:5432/db",
                LLM_PROVIDER="google",
                GOOGLE_API_KEY="",
            )
