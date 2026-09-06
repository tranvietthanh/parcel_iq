"""Backward-compatible re-export shim for LLM client."""

from __future__ import annotations

from app.services.providers import get_llm_client

llm_client = get_llm_client()
