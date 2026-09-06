---
phase: 2
title: "Anthropic & Google AI Provider Adapters"
status: completed
priority: P1
effort: "2d"
dependencies: [1]
---

# Phase 2: Anthropic & Google AI Provider Adapters

## Overview

Implement the two concrete provider adapters left as `NotImplementedError`
placeholders in Phase 1, so `LLM_PROVIDER=anthropic` and `LLM_PROVIDER=google`
are real, switchable options alongside the existing OpenAI-compatible path.

**Red-team findings (2026-09-05, accepted) reshaping this phase:**
1. **API key leak (Critical).** The original Google adapter draft passed
   `GOOGLE_API_KEY` as a URL query parameter. `requests.HTTPError`'s message
   format includes the full request URL, so any Google API error (429, 403,
   quota) would propagate the live key into `tasks.py`'s exception handling —
   which both logs it (`logger.error`) and persists it to
   `property_reports.error_message` in Postgres. Fixed below: header-based auth
   for both new providers, plus a redaction step in `tasks.py`.
2. **Silent truncation/safety-block (High).** Neither original snippet checked
   `stop_reason`/`finishReason`/`promptFeedback` — a Gemini safety block or an
   Anthropic `max_tokens` cutoff both return HTTP 200 with unusable content,
   which `raise_for_status()` doesn't catch. Fixed below: both adapters raise
   an explicit, greppable error instead of returning empty/truncated text.
3. **Retry-classifier false positive (High).** `tasks.py`'s Pydantic-validation-failure
   message embeds up to 500 chars of raw model output
   (`tasks.py:134-137`). Australian property data routinely contains the digit
   run "429" (e.g. a $1,429,000 price, a `-37.8429` latitude). The existing
   `"429" in err_msg` check would misclassify a validation failure as a
   rate-limit retry. This phase does not change `tasks.py`'s classifier (that's
   Phase 3's territory since it also touches quota semantics), but both new
   adapters raising structured errors (finding 2) reduces how often garbage
   model text reaches that classifier at all.
4. **Unenforceable/duplicated smoke test (Medium).** The original step 5
   ("manually verify one live call... in a local `.env` not committed") left no
   artifact and duplicated an existing script,
   `services/llm-parser-worker/scripts/verify_gemini_live.py`, which Phase 1
   already renames to `verify_llm_live.py`. Fixed below: generalize and use
   that script instead of an ad-hoc manual step.

## Requirements

- Functional: both adapters implement `LlmProvider.generate_json(system_prompt, user_prompt) -> str` and return the assistant's raw text (JSON string, possibly fenced — `tasks.py`'s existing `_extract_json_payload()` already strips Markdown fences/prose, so neither adapter needs to do that itself).
- Functional: force JSON-shaped output using each provider's native mechanism where available, to reduce reliance on `_extract_json_payload()`'s best-effort parsing.
- Functional: both adapters send their API key via an HTTP header, never a URL query parameter or request body field that could end up logged verbatim.
- Functional: both adapters raise a distinct, greppable exception (not a silently empty/truncated string) when the provider returns 200 with no usable content (safety block, `max_tokens` cutoff, empty candidates).
- Non-functional: same `timeout=300` ceiling as the OpenAI adapter (consistency, not a hard requirement).
- Non-functional: neither new adapter introduces a provider SDK dependency — both use plain `requests` (matches existing style, avoids adding `anthropic`/`google-generativeai` packages and their transitive dependency weight for a Celery worker image).

## Architecture

**Anthropic (`providers/anthropic_provider.py`)** — Messages API:
```python
class AnthropicClient:
    def __init__(self, api_key: str, model: str, api_base: str = "https://api.anthropic.com/v1"):
        self.model_name = model
        ...

    def generate_json(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192) -> str:
        resp = self.session.post(
            f"{self.api_base}/messages",
            headers={
                "x-api-key": self.api_key,          # header, never a query param or logged field
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model_name,
                "max_tokens": max_tokens,
                "system": system_prompt,          # top-level field, not a message — Anthropic's Messages API has no "system" role
                "messages": [{"role": "user", "content": user_prompt}],
            },
            timeout=300,
        )
        resp.raise_for_status()
        data = resp.json()

        stop_reason = data.get("stop_reason")
        if stop_reason == "max_tokens":
            raise RuntimeError(f"PROVIDER_TRUNCATED: anthropic stop_reason=max_tokens (raise max_tokens or shrink the prompt)")

        blocks = data.get("content") or []
        text = next((b.get("text") for b in blocks if b.get("type") == "text"), None)
        if not text:
            raise RuntimeError(f"PROVIDER_NO_CONTENT: anthropic stop_reason={stop_reason}")
        return text
```
`max_tokens=8192` (raised from the original 4096 draft): the schema includes
`narrative` (7 free-text fields), `demographic_trend_analysis` (7 signals +
notes), `roi_scenarios`, `infrastructure[]`, `education` — 4096 is tight for
this payload and silently truncating is now a raised error rather than a
quietly-broken parse, so pick a ceiling generous enough that legitimate
responses don't trip it.

Note: Anthropic's Messages API has no `response_format: json_object` equivalent
at the time this plan was written — rely on the existing system prompt's
"Return ONLY valid JSON" instruction + `_extract_json_payload()`'s fence/brace
scanning in `tasks.py`. Verify against current Anthropic API docs at
implementation time in case a JSON-mode parameter has since shipped.

**Google AI / Gemini (`providers/google_provider.py`)** — `generateContent`:
```python
class GoogleAIClient:
    def __init__(self, api_key: str, model: str, api_base: str = "https://generativelanguage.googleapis.com/v1beta"):
        self.model_name = model
        self.api_key = api_key
        ...

    def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        resp = self.session.post(
            f"{self.api_base}/models/{self.model_name}:generateContent",
            headers={"x-goog-api-key": self.api_key},   # header, NOT params={"key": ...} — see red-team finding above
            json={
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "response_mime_type": "application/json",  # Gemini native JSON mode
                },
            },
            timeout=300,
        )
        resp.raise_for_status()
        data = resp.json()

        candidates = data.get("candidates") or []
        if not candidates:
            block_reason = (data.get("promptFeedback") or {}).get("blockReason")
            raise RuntimeError(f"PROVIDER_NO_CANDIDATES: google blockReason={block_reason}")

        finish_reason = candidates[0].get("finishReason")
        if finish_reason == "MAX_TOKENS":
            raise RuntimeError("PROVIDER_TRUNCATED: google finishReason=MAX_TOKENS")

        parts = candidates[0].get("content", {}).get("parts") or []
        text = parts[0].get("text") if parts else None
        if not text:
            raise RuntimeError(f"PROVIDER_NO_CONTENT: google finishReason={finish_reason}")
        return text
```
Gemini supports `response_mime_type: application/json` natively — prefer this
over prompt-only enforcement. **Critical: the API key goes in the
`x-goog-api-key` header, not `params={"key": ...}`** — a URL query parameter
ends up embedded in `requests.HTTPError`'s message (`"... for url: ..."`),
which `tasks.py` logs and persists to the database on any failure.

Both clients raise on non-2xx via `resp.raise_for_status()`, matching the
OpenAI adapter's error contract so `tasks.py`'s existing `"429" in err_msg`
rate-limit detection keeps working (both `requests.HTTPError` messages embed
the status code text) — but neither client leaks its key in that message
anymore, since neither puts the key in the URL.

## Related Code Files

- Create: `services/llm-parser-worker/app/services/providers/anthropic_provider.py`
- Create: `services/llm-parser-worker/app/services/providers/google_provider.py`
- Modify: `services/llm-parser-worker/app/config.py` — populate `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (default e.g. `""`, no invented model id — must be set explicitly), `ANTHROPIC_BASE_URL` (default `https://api.anthropic.com/v1`), `GOOGLE_API_KEY`, `GOOGLE_MODEL`, `GOOGLE_BASE_URL` (default `https://generativelanguage.googleapis.com/v1beta`); extend `_reject_insecure_defaults_in_production` to check the correct key for whichever `LLM_PROVIDER` is active.
- Modify: `services/llm-parser-worker/app/services/providers/__init__.py` — add `AnthropicClient`/`GoogleAIClient` to `LLM_PROVIDER_REGISTRY` and implement the `anthropic`/`google` construction branches in `get_llm_client()` (Phase 1 introduced this registry-in-`__init__.py` shape instead of a separate `factory.py` — see Phase 1's red-team note).
- Modify: `services/llm-parser-worker/app/tasks.py` — add an error-message redaction step before the `error_message`/log write (belt-and-suspenders alongside the header-based-auth fix, since a future provider or a library-level retry/redirect could still surface a credential in an exception string): `err_msg = re.sub(r"(key=|api[-_]?key\"?[:=]\s*\"?)[A-Za-z0-9_\-]{8,}", r"\1[REDACTED]", err_msg)` before `tasks.py:213` (the `error_message` UPDATE) and `tasks.py:220` (the `logger.error` call).
- Modify: `services/llm-parser-worker/.env.example` — document `ANTHROPIC_*`/`GOOGLE_*` vars.
- Create: `services/llm-parser-worker/tests/unit/test_providers/test_anthropic_provider.py` — mock `requests`, assert request shape (system as top-level field, key in header not body/params), response parsing, and the two new raised-error paths (`stop_reason=max_tokens`, empty content blocks).
- Create: `services/llm-parser-worker/tests/unit/test_providers/test_google_provider.py` — mock `requests`, assert `response_mime_type` is sent, key is in the `x-goog-api-key` header (not `params`), response parsing handles the `candidates[0].content.parts[0].text` path, and the two new raised-error paths (`blockReason` present with empty candidates, `finishReason=MAX_TOKENS`).
- Create: `services/llm-parser-worker/tests/unit/test_providers/test_registry.py` — parametrized over `LLM_PROVIDER` in `{openai, anthropic, google}`, asserts `get_llm_client()` returns the right class instance with the right `model_name`; asserts an unknown value raises `ValueError`.
- Modify: `services/llm-parser-worker/tests/unit/test_tasks.py` (or wherever error-message redaction is tested) — add a fixture asserting a `provider error containing "key=abc123..."` is redacted before it would reach the DB/log write.
- Reference (already renamed in Phase 1): `services/llm-parser-worker/scripts/verify_llm_live.py` — this phase's live-verification step uses this script; no separate ad-hoc script needed.

## Implementation Steps

1. Implement `AnthropicClient` per the architecture above (header auth, `stop_reason` check); write its unit test first (or alongside) against a mocked response fixture, including the truncation/empty-content error paths.
2. Implement `GoogleAIClient` per the architecture above (header auth, `finishReason`/`blockReason` checks); same test approach.
3. Add the `err_msg` redaction step to `tasks.py`.
4. Wire both into `providers/__init__.py`'s `LLM_PROVIDER_REGISTRY` and `get_llm_client()`, replacing the Phase 1 `NotImplementedError` placeholders.
5. Add the new settings to `config.py` + `.env.example`, extend the production validator.
6. Run `scripts/verify_llm_live.py --provider anthropic` and `--provider google` against real API keys in a local, uncommitted `.env` before considering this phase done — mocked tests alone don't catch wire-format drift against the real API. This is a re-runnable, committed artifact, not an ad-hoc manual step.

## Success Criteria

- [x] `LLM_PROVIDER=anthropic` with a valid `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL` produces a `parse_with_llm` run that validates against `LlmOutput` end-to-end against a real property, verified via `scripts/verify_llm_live.py --provider anthropic`.
- [x] `LLM_PROVIDER=google` with a valid `GOOGLE_API_KEY`/`GOOGLE_MODEL` does the same via `--provider google`.
- [x] Switching `LLM_PROVIDER` requires only an `.env` change — no code change, no redeploy of a different image.
- [x] Neither adapter's API key ever appears in a `requests.HTTPError` message (verified by a unit test that triggers a 4xx/5xx mock response and asserts the key string is absent from the raised exception's `str()`).
- [x] A 200 response with `stop_reason=max_tokens` (Anthropic) or `finishReason=MAX_TOKENS`/empty `candidates` (Google) raises a `PROVIDER_TRUNCATED`/`PROVIDER_NO_CONTENT`/`PROVIDER_NO_CANDIDATES` error, not a silently truncated/empty parse.
- [x] New unit tests pass; existing suite (`test_tasks.py`, `test_llm_output_validation.py`) still passes unmodified.

## Risk Assessment

Medium risk: both new adapters hit external APIs with formats that can drift
(Anthropic/Google may add native structured-output modes after this plan is
written — check current docs at implementation time rather than trusting the
snippets above verbatim). Mitigate by keeping `_extract_json_payload()` in
`tasks.py` as the safety net regardless of provider (already handles fenced/
prose-wrapped JSON), and by running `scripts/verify_llm_live.py` per provider
before merging (step 6) rather than trusting mocks alone. The credential-leak
risk (finding 1) is the one that would have been genuinely severe if shipped
as originally drafted — header-based auth plus the `tasks.py` redaction step
are both required, not either/or, since a future third-party library or a
redirect could still smuggle a key into an exception string.
