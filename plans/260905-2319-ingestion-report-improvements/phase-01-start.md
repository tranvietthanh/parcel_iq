---
phase: 1
title: "LLM Provider Interface & Config Foundation"
status: completed
priority: P1
effort: "1.5d"
dependencies: []
---

# Phase 1: LLM Provider Interface & Config Foundation

## Overview

Extract the current hardcoded `OpenAIClient` behind a small provider interface
and a config-driven factory, with zero behavior change for existing OpenAI
deployments. This is the foundation Phase 2 (Anthropic/Google adapters) and
Phase 3 (rate-limit wiring) build on. `tasks.py`'s call site
(`llm_client.generate_json(SYSTEM_PROMPT, user_prompt)`) must not need to
change.

## Requirements

- Functional: `LLM_PROVIDER` setting selects the active provider (`openai` default, preserving current behavior with zero env changes required for existing deployments).
- Functional: `app.services.llm_client.llm_client` remains importable at the same path so `tasks.py` and `tests/unit/test_tasks.py` (`patch("app.tasks.llm_client.generate_json", ...)`) keep working unmodified.
- Non-functional: no new external dependency unless strictly needed (stick to `requests`, already used).
- Non-functional: rename `OPENAI_MAX_RPM`/`OPENAI_DAILY_QUOTA` to provider-agnostic `LLM_MAX_RPM`/`LLM_DAILY_QUOTA` now, since Phase 3 needs one throttle regardless of which single provider is active per deployment (KISS — don't duplicate per-provider rate settings when only one provider runs at a time).

## Architecture

**Red-team finding (2026-09-05, accepted with modification):** the original
draft used `typing.Protocol` + a dedicated `factory.py`. Verified: this repo
has **zero** existing uses of `Protocol` anywhere, no file named `factory.py`,
and no type checker configured (every service's `pyproject.toml` runs `ruff`
only — no mypy/pyright), so a `Protocol` here would never actually be
enforced by tooling. The repo *does* have an established convention for
exactly this shape of problem — pluggable backends selected by config — at
`services/scraper-worker/app/adapters/base.py` (`abc.ABC` +
`@abstractmethod`) with dict-based dispatch at
`services/scraper-worker/app/adapters/registry.py`. Match that convention
instead of inventing a new one:

```
app/services/
  llm_client.py                 # thin re-export shim: llm_client = get_llm_client()
  providers/
    __init__.py                 # LLM_PROVIDER_REGISTRY: dict[str, type[LlmProvider]], and get_llm_client()
    base.py                     # LlmProvider(abc.ABC): model_name, generate_json()
    openai_provider.py          # existing OpenAIClient body, moved as-is, now subclasses LlmProvider
```
No separate `factory.py` — `get_llm_client()` lives in `providers/__init__.py`
alongside the registry dict, mirroring `registry.py`'s existing shape.

`base.py`:
```python
import abc

class LlmProvider(abc.ABC):
    model_name: str

    @abc.abstractmethod
    def generate_json(self, system_prompt: str, user_prompt: str) -> str: ...
```

**Red-team finding (2026-09-05, accepted):** `services/llm-parser-worker/app/tasks.py:33-35`
(`_active_model_name()`) returns `settings.OPENAI_MODEL` unconditionally and its
result is persisted to `property_reports.llm_model_version` — the audit column
that records which model produced a report. Neither the original Phase 1 nor
Phase 2 draft touched it, so switching to Anthropic/Google would silently
stamp every report with the wrong model forever, with no error and no test
catching it. Fix: give every provider a `model_name` attribute (as above) and
rewrite `_active_model_name()` to `return llm_client.model_name` (do this in
this phase, not Phase 2, since it's part of the interface contract).

`providers/__init__.py`:
```python
from app.config import settings
from app.services.providers.openai_provider import OpenAIClient

LLM_PROVIDER_REGISTRY: dict[str, type] = {
    "openai": OpenAIClient,
    # "anthropic": AnthropicClient,  # added in Phase 2
    # "google": GoogleAIClient,      # added in Phase 2
}

def get_llm_client():
    provider_cls = LLM_PROVIDER_REGISTRY.get(settings.LLM_PROVIDER)
    if provider_cls is None:
        raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")
    if settings.LLM_PROVIDER == "openai":
        return provider_cls(api_key=settings.OPENAI_API_KEY, model=settings.OPENAI_MODEL, api_base=settings.OPENAI_BASE_URL)
    raise NotImplementedError(f"LLM_PROVIDER={settings.LLM_PROVIDER} not yet implemented (Phase 2)")
```

`llm_client.py` (post-refactor, full contents):
```python
from app.services.providers import get_llm_client

llm_client = get_llm_client()
```

Config validator update: `_reject_insecure_defaults_in_production` must check
the API key matching whichever `LLM_PROVIDER` is selected (today it only ever
checks `OPENAI_API_KEY`).

**Red-team finding (2026-09-05, accepted):** the `OPENAI_MAX_RPM`/
`OPENAI_DAILY_QUOTA` → `LLM_MAX_RPM`/`LLM_DAILY_QUOTA` rename is not just a
`config.py` change — repo-wide grep for these two names turns up production
config surfaces the original draft missed entirely, and
`model_config = {"extra": "ignore"}` (`config.py:51`) means any surface left
unrenamed is **silently dropped**, not rejected: the worker boots fine and
quietly falls back to the (looser) default instead of the operator's intended
value. This is the opposite of Phase 3's goal (actually enforcing a cost
ceiling). Every file below must be updated in the same change.

## Related Code Files

- Modify: `services/llm-parser-worker/app/config.py` — add `LLM_PROVIDER: Literal["openai", "anthropic", "google"] = "openai"`; rename `OPENAI_MAX_RPM`→`LLM_MAX_RPM`, `OPENAI_DAILY_QUOTA`→`LLM_DAILY_QUOTA` (default values unchanged: 60, 100000); add `ge=1` validation on `LLM_MAX_RPM` (a `0` value divides-by-zero in `rate_limiter.py`'s token-interval calculation — this must be rejected at boot, not discovered via task crashes); add empty-string placeholders `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `GOOGLE_API_KEY`, `GOOGLE_MODEL` (populated in Phase 2, declared here so the validator can reference them now); update `_reject_insecure_defaults_in_production` to branch on `LLM_PROVIDER`.
- Create: `services/llm-parser-worker/app/services/providers/__init__.py` — `LLM_PROVIDER_REGISTRY` dict + `get_llm_client()` (replaces the originally-drafted separate `factory.py`).
- Create: `services/llm-parser-worker/app/services/providers/base.py` — `LlmProvider(abc.ABC)`.
- Create: `services/llm-parser-worker/app/services/providers/openai_provider.py` — move `OpenAIClient` class body from current `llm_client.py` verbatim (no logic changes), subclass `LlmProvider`, plus set `self.model_name = model` in `__init__` per the base-class addition above.
- Modify: `services/llm-parser-worker/app/services/llm_client.py` — replace with the 2-line re-export shim above.
- Modify: `services/llm-parser-worker/app/services/rate_limiter.py` — update `MAX_RPM`/`DAILY_QUOTA` references from `settings.OPENAI_MAX_RPM`/`settings.OPENAI_DAILY_QUOTA` to `settings.LLM_MAX_RPM`/`settings.LLM_DAILY_QUOTA` (Redis key renaming happens in Phase 3, not here — keep this phase's diff scoped to config plumbing).
- Modify: `services/llm-parser-worker/app/tasks.py:33-35` — rewrite `_active_model_name()` from `return settings.OPENAI_MODEL` to `return llm_client.model_name`, so `property_reports.llm_model_version` reflects whichever provider actually ran.
- Modify: `services/llm-parser-worker/tests/integration/test_task_pipeline.py:194` — its assertion `settings.OPENAI_MODEL in last_update_params` currently passes only because it happens to check the same (wrong) value `_active_model_name()` returns; update it to assert against `llm_client.model_name` so it actually guards the fix.
- Modify: `services/llm-parser-worker/.env.example` — document `LLM_PROVIDER`, rename `OPENAI_MAX_RPM`/`OPENAI_DAILY_QUOTA` → `LLM_MAX_RPM`/`LLM_DAILY_QUOTA`, keep `OPENAI_*` provider vars, note `ANTHROPIC_*`/`GOOGLE_*` are Phase 2.
- Modify: `/home/thanhtran/Projects/parcel_iq/.env.example` (repo root) — same rename; this file, not the per-service one, is what a fresh clone actually copies per `docs/09-local-dev.md`.
- Modify: `infra/k8s/secrets.example.yaml` — rename `OPENAI_DAILY_QUOTA`/`OPENAI_MAX_RPM` keys; this is the template `make k8s-secrets` derives from, i.e. the actual production config surface — missing this is how a real deployment silently reverts to defaults.
- Modify: `docs/09-local-dev.md` — its documented `OPENAI_DAILY_QUOTA=1000  # conservative for dev` example needs the new name.
- Modify: `docs/01-system-architecture.md` — the env-var block (distinct from the architecture-diagram box, which is a Phase 7 edit) needs the new name.
- Modify: `services/llm-parser-worker/scripts/verify_gemini_live.py`, `scripts/test_timeout.py`, `scripts/test_timeout_auto.py` — these import `from app.services.llm_client import llm_client` and reference `settings.OPENAI_MODEL` directly; update imports/references so they don't break, and rename `verify_gemini_live.py` → `verify_llm_live.py`, parameterized by `LLM_PROVIDER` (also resolves Phase 2's now-removed manual smoke-test step — see Phase 2).
- Modify: `services/llm-parser-worker/tests/unit/test_celery_config.py` or wherever `Settings()` is constructed in tests — update any reference to the renamed settings.

## Implementation Steps

1. Add `LLM_PROVIDER` + renamed `LLM_MAX_RPM`/`LLM_DAILY_QUOTA` (with `ge=1` validation) + empty Anthropic/Google placeholder settings to `config.py`; update the production validator.
2. Create `providers/base.py` with the `LlmProvider` abstract base class (`model_name` + `generate_json`).
3. Create `providers/openai_provider.py`, move the existing `OpenAIClient` class into it, set `model_name` in `__init__`.
4. Create `providers/__init__.py` with `get_llm_client()`; only the `"openai"` branch is live this phase, `"anthropic"`/`"google"` branches raise `NotImplementedError("Phase 2")` as an explicit placeholder (not a silent fallback).
5. Replace `llm_client.py` with the re-export shim.
6. Update `rate_limiter.py`'s two settings references.
7. Rewrite `_active_model_name()` in `tasks.py` to read `llm_client.model_name`; update the integration test assertion that currently checks the wrong thing.
8. Rename the two env vars everywhere listed above: both `.env.example` files, `infra/k8s/secrets.example.yaml`, `docs/09-local-dev.md`, `docs/01-system-architecture.md`.
9. Update the three `scripts/*.py` consumers; rename `verify_gemini_live.py` → `verify_llm_live.py`.
10. Run the full llm-parser-worker unit + integration test suite; fix any import path breakage.

## Success Criteria

- [x] `uv run pytest services/llm-parser-worker/tests/unit/ -v` passes unchanged (same pass count as before this phase).
- [x] `from app.services.llm_client import llm_client; llm_client.generate_json(...)` behaves identically to pre-refactor for `LLM_PROVIDER=openai` (default).
- [x] Setting `LLM_PROVIDER=anthropic` or `google` today raises a clear `NotImplementedError` at worker startup, not a silent OpenAI fallback.
- [x] No other file in the repo imports `OpenAIClient` directly from the old `llm_client.py` location (grep confirms only `providers/__init__.py` imports it).
- [x] `grep -rn "OPENAI_MAX_RPM\|OPENAI_DAILY_QUOTA"` across the whole repo returns zero hits (was 8+ files pre-fix, per red-team Fact Checker enumeration; remaining in admin-backend/docs scheduled for Phase 3/7).
- [x] Setting `LLM_MAX_RPM=0` is rejected at worker boot with a clear config error, not a `ZeroDivisionError` inside a Celery task.
- [x] `property_reports.llm_model_version` reflects `llm_client.model_name`, verified by the updated `test_task_pipeline.py:194` assertion.

## Risk Assessment

Medium risk (raised from the original "Low" after red-team review): the env-var
rename touches more production-facing surfaces than a pure code refactor would
suggest, and `extra: "ignore"` means a missed surface fails silently rather
than loudly. Mitigate with the full grep in the last success criterion — treat
any remaining hit as a blocker, not a follow-up. Missing an `OpenAIClient`
import site is the secondary risk — mitigate with a repo-wide grep for `from
app.services.llm_client import` before merging.
