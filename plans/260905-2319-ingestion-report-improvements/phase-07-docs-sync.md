---
phase: 7
title: "Sync Docs to Implementation"
status: pending
priority: P2
effort: "1d"
dependencies: [2, 3, 4, 5, 6]
---

# Phase 7: Sync Docs to Implementation

## Overview

Runs last, after Phases 2-6 land, so it documents the final real state rather
than an intermediate one. The review surfaced multiple stale/incorrect claims
scattered across docs *and* code docstrings (not just `docs/`): three separate
places assert a Gemini/NVIDIA provider that never existed until this plan's
Phase 1/2, and `docs/06-llm-parser-worker.md` currently claims rate limiting
"strictly" enforces limits when (pre-Phase-3) it didn't. Per user decision,
this phase also documents — but does not implement — that the manual-review
gate stays removed for now (follow-up is a future, separate decision), and
that `crime_density`/`estimated_value`/`estimated_rent` are known data gaps,
not bugs, so nobody re-attempts a "fix" expecting a data source that doesn't
exist.

**Red-team finding (2026-09-05, accepted):** the original file list below was
materially incomplete — a broader repo-wide grep during red-team review found
~8 more files referencing Gemini/NVIDIA or a phantom env var, including two
LLM prompt module docstrings (not just documentation) and a testing guide that
documents a `GEMINI_API_KEY` setting that has never existed in any config
class. All are now listed explicitly below instead of relying solely on the
step-1 grep to surface them mid-phase.

## Requirements

- Functional: every doc/docstring claim about the LLM provider matches the real, now-pluggable implementation (openai/anthropic/google via `LLM_PROVIDER`).
- Functional: `docs/06-llm-parser-worker.md`'s rate-limiting claim matches reality post-Phase-3 (true again once wired up).
- Functional: `AGENTS.md`'s "Common Mistakes to Avoid" table entry about `review_flag` is updated to state plainly: removal is a standing decision, not a bug to fix; a legal-compliance follow-up is a separate, not-yet-scheduled decision.
- Functional: a new note (in `AGENTS.md` and/or `docs/04-database.md`, wherever `estimated_value`/`estimated_rent` and `risk_factors.crime_density` are documented) states these are known data gaps with no adapter/source — not partially-broken features.
- Non-functional: no doc file exceeds the project's `docs.maxLoc: 800` guideline after edits — check line count post-edit, split only if genuinely necessary (unlikely for these targeted edits).

## Related Code Files

- Modify: `AGENTS.md` — "Where Things Live" table entry for `services/llm-parser-worker/` (currently: "Celery workers + LLM (Gemini or NVIDIA via factory pattern)") → describe the real factory (openai/anthropic/google via `LLM_PROVIDER`, see Phase 1/2). Update the "Common Mistakes to Avoid" table's `review_flag` row per the decision above. Add a short data-gap note for `crime_density`/`estimated_value`/`estimated_rent`.
- Modify: `docs/06-llm-parser-worker.md` — replace the OpenAI-only spec (§1, §5) with the real multi-provider factory design from Phase 1/2; correct env var names (`OPENAI_MAX_RPM`/`OPENAI_DAILY_QUOTA` → `LLM_MAX_RPM`/`LLM_DAILY_QUOTA`, per Phase 1); confirm the rate-limiting claim in §1/§4 is accurate post-Phase-3.
- Modify: `docs/current_data_flow.md` — the "LLM Parser (OpenAI)" label in the pipeline diagram/table → provider-neutral wording.
- Modify: `docs/01-system-architecture.md:108` — architecture diagram box "Celery + Gemini API" → "Celery + configured LLM provider" (or similar provider-neutral phrasing consistent with the diagram's style).
- Modify: `docs/10-testing-strategy.md:355` — "Playwright and Gemini API mocked" → "Playwright and the LLM provider API mocked".
- Modify: `AGENTS.md:219` — docs table description "`06-llm-parser-worker.md` — LLM provider config (Gemini/NVIDIA), confidence scoring" → describe the real openai/anthropic/google factory.
- Verify (no edit expected): `services/admin-backend` and `apps/admin-web` — Phase 3 already renamed `GeminiQuotaStats`/`gemini_quota` to provider-neutral naming; this phase's grep pass (step 1) should confirm zero remaining references rather than re-doing that work.
- Modify: `shared/py-types/parceliq_types/llm_output.py` — docstring lines 1-7 ("Schema source: docs/06-llm-parser-worker.md §7", implies OpenAI) and line 186 ("enforcing the exact structure expected from Gemini") → provider-neutral wording (the schema doesn't change, only the comment describing its origin).
- Modify: `services/llm-parser-worker/app/tasks.py` — module docstring line 4 ("sends it to Gemini for structured extraction") → "sends it to the configured LLM provider".
- Modify: `services/llm-parser-worker/app/services/rate_limiter.py` — already corrected in Phase 3 (docstring fix bundled there since it's a one-line change alongside the key rename); verify it during this phase's review pass rather than re-doing it.
- Check: `docs/04-database.md` (or wherever `properties.estimated_value`/`estimated_rent` columns are documented) — add the data-gap note.
- Check: `docs/07-legal-compliance.md` — if it references the review gate as currently active/required, add a pointer to the standing "removed for now, follow-up TBD" decision (do not re-litigate the legal analysis itself — that's out of scope, a future legal/product decision).
- Modify: `README.md:116` — "Provider-configurable worker (Gemini / NVIDIA / OpenAI-compatible)" describes a factory that (pre-Phase-1/2) didn't exist; correct to describe the real openai/anthropic/google factory now that it does.
- Modify: `TESTING.md:128,134` — documents `# Run with live Gemini verification (if GEMINI_API_KEY set)`; `GEMINI_API_KEY` is not, and never was, a real setting in any config class (grep confirms). Correct to reference `scripts/verify_llm_live.py --provider <name>` (Phase 1/2) and the actual per-provider env vars.
- Modify: `services/llm-parser-worker/app/prompts/system_prompt.py:1` — docstring "System prompt for the Gemini structured extraction model" → provider-neutral wording.
- Modify: `services/llm-parser-worker/app/prompts/user_prompt.py:1,457` — same class of stale Gemini-specific wording.
- Check: `services/llm-parser-worker/tests/integration/test_task_pipeline.py:3,45,101,126` — comments/docstrings referencing Gemini; correct wording (this file's actual mock-patching changes for the rate-limiter wiring are Phase 3's job, not this phase's — here only the stale text matters).
- Verify (already handled elsewhere, confirm only): `services/llm-parser-worker/scripts/verify_gemini_live.py` → `verify_llm_live.py` and `scripts/test_timeout.py`/`test_timeout_auto.py` were already renamed/updated in Phase 1 — this phase's grep pass should find zero remaining references, not redo that work.
- Verify (already handled in Phase 1, confirm only): `docs/01-system-architecture.md:397-400` (the env-var block) was already renamed by Phase 1 — this phase only touches the separate architecture-diagram box at line 108.

## Implementation Steps

1. Grep the whole repo (`grep -rn "Gemini\|NVIDIA" --include="*.py" --include="*.md"`) to find every remaining stale reference — treat this as a completeness check against the explicit list above, not as the sole discovery mechanism (the list above already reflects a broader grep done during red-team review; do not rely on step 1 alone to find everything, since the original draft of this phase did and still missed ~8 files).
2. Update `AGENTS.md` (3 edits: provider line, review_flag row, new data-gap note) and `README.md:116`.
3. Rewrite the relevant sections of `docs/06-llm-parser-worker.md`.
4. Fix `docs/current_data_flow.md`'s provider label, `docs/01-system-architecture.md:108`'s diagram box, and `docs/10-testing-strategy.md:355`.
5. Fix `TESTING.md`'s phantom `GEMINI_API_KEY` reference.
6. Fix the stale docstrings: `llm_output.py`, `tasks.py`, `prompts/system_prompt.py`, `prompts/user_prompt.py`.
7. Check and correct comments in `test_task_pipeline.py`; verify (don't redo) the Phase-1-renamed scripts and the Phase-1-renamed `docs/01-system-architecture.md:397-400` env block.
8. Check and update `docs/04-database.md` and `docs/07-legal-compliance.md` per the notes above.
9. Re-run the grep from step 1 — zero remaining stale Gemini/NVIDIA-as-only-provider references should exist outside of this plan's own files (which correctly reference history) and any CHANGELOG-style historical record.
10. Whole-plan consistency check: re-read `plan.md` and all 7 phase files together, confirm no contradictions remain between what Phases 1-6 actually built and what Phase 7 now documents (e.g. if Phase 2's Anthropic/Google implementation details changed during actual implementation, this phase's docs must reflect the real shipped behavior, not this plan's original sketch).

## Success Criteria

- [ ] `grep -rn "Gemini\|NVIDIA"` across the repo returns no hits implying either is the sole/default provider (historical mentions in this plan's own files are fine).
- [ ] `AGENTS.md`'s LLM worker description matches the real factory pattern.
- [ ] `AGENTS.md`'s `review_flag` row reads as a standing decision, not an open bug.
- [ ] A data-gap note for `crime_density`/`estimated_value`/`estimated_rent` exists somewhere discoverable (AGENTS.md and/or docs/04-database.md).
- [ ] `docs/06-llm-parser-worker.md` accurately describes rate limiting as actually enforced (true post-Phase-3).
- [ ] No doc file exceeds 800 LOC.

## Risk Assessment

Very low technical risk (docs-only). The real risk is doing this phase before
Phases 1-6 are actually merged/stable — if it runs early, it documents an
intended design rather than the shipped one, reintroducing the exact
doc-drift problem this plan exists to fix. Keep the `dependencies: [2, 3, 4,
5, 6]` gate enforced; do not start this phase until those are done.
