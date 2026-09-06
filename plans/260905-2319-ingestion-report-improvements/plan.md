---
title: "ingestion-report-improvements"
description: "Pluggable LLM provider factory, fix dead rate limiter + ABS growth-rate bug, surface unused LLM report data in PDF/web, sync docs to reality"
status: pending
priority: P1
effort: "11-13d"
tags: [llm-parser-worker, scraper-worker, pdf-renderer, public-api, public-web, docs]
created: 2026-09-05
---

# ingestion-report-improvements

## Overview

Follow-up to a full review of the data ingestion flow (`services/scraper-worker`,
`services/llm-parser-worker`) and report generation flow (`shared/pdf-renderer`,
`services/public-api`, `apps/public-web`). Review found: (1) `AGENTS.md` and
several docstrings claim a Gemini/NVIDIA provider factory that was never built —
the LLM worker is hardcoded to OpenAI; (2) the LLM worker's Redis rate
limiter/daily-quota guard exist but are never called (dead code) — no proactive
throttle on OpenAI spend; (3) `_add_growth_rates()` in the ABS census adapter is
an empty no-op due to a copy-paste error, silently dropping YoY growth metrics;
(4) the LLM already extracts `infrastructure[]`, risk `.detail` text, zoning
`conflict_note`/`epi_type`, `narrative`, `demographic_trend_analysis`, and
`roi_scenarios` but the PDF and/or web UI never render several of them; (5)
`AGENTS.md` and related docs are stale relative to the real implementation.

User decisions resolving prior open questions:
- Build a real pluggable LLM provider factory: OpenAI-compatible (as today),
  Anthropic, Google AI (Gemini).
- Unrendered `infrastructure[]` was not intentional — add it to the report.
- `crime_density` and `properties.estimated_value`/`estimated_rent` are pure
  data-gaps (no adapter/source exists) — **out of scope for this plan**, no
  code changes attempted for them.
- The removed manual-review gate (`review_flag`, migration `023`) stays
  removed for now; a legal-compliance follow-up is a separate future decision,
  not implemented here — this plan only documents that status.
- `AGENTS.md` (and related docs/docstrings) must be synced to the final
  implementation once the above lands.

**Confirmed product model (2026-09-05, resolved a red-team-raised paywall
concern):** anonymous users get a demo/lite report; logged-in users always
have full-report access, paying with credits (auto-topped-up daily up to 3,
purchasable beyond that) specifically at PDF-**download** time. Viewing the
detail page is an authentication-gated action, not a credit-gated one. This
shapes Phase 5 (lite vs. full PDF content) and Phase 6 (auth-gated, not
credit-gated, API fields).

## Goals

| # | Goal | Priority |
|---|------|----------|
| 1 | Real pluggable LLM provider factory (OpenAI-compatible / Anthropic / Google AI) behind one config switch | P1 |
| 2 | Wire the existing dead rate-limiter/daily-quota code into the actual LLM call path | P1 |
| 3 | Fix the ABS `_add_growth_rates()` no-op bug | P1 |
| 4 | Render already-extracted LLM data (`infrastructure`, risk detail, zoning conflict/epi_type) in the PDF | P2 |
| 5 | Bring the public-web property detail page to parity with the PDF (narrative, trend analysis, ROI, infrastructure) | P2 |
| 6 | Sync `AGENTS.md` + related docs/docstrings to the real implementation | P2 |

## Non-Goals

- No crime-data source, no property valuation/rent-estimate source (explicit user decision: data gap, not a bug — out of scope).
- No reinstatement of the manual-review gate (`review_flag`) — stays removed; only documented as an intentional, revisitable-later decision.
- No change to scraper adapter set (ABS/NBN/VicPlan/council adapters) beyond the one bugfix in Phase 4.
- No change to credit/payment/auth flows themselves — Phase 6 adds an authentication *check* (`get_optional_user`) to existing endpoints, but does not touch credit debiting, Stripe, or the ledger, which stay exactly as reviewed and confirmed sound.
- No SDK dependency for Anthropic/Google (plain `requests`, matching the existing OpenAI client's style).
- No bulk MinIO cache-sweep or ABS cache backfill job — both Phase 4 and Phase 5's cache-invalidation fixes are lazy/self-healing (next access re-fetches), not proactive bulk jobs, per YAGNI.
- No pagination/rate-limit rework of `GET /api/saved` — a payload-size follow-up noted in Phase 6, not part of this plan.

## Phases

| # | Phase | Status | Depends on |
|---|-------|--------|------------|
| 1 | [Phase 1: LLM Provider Interface & Config Foundation](./phase-01-start.md) | Completed | — |
| 2 | [Phase 2: Anthropic & Google AI Provider Adapters](./phase-02-llm-provider-abstraction.md) | Completed | 1 |
| 3 | [Phase 3: Wire Rate Limiter & Daily Quota Into the Call Path](./phase-03-llm-rate-limit-wiring.md) | Completed | 1 |
| 4 | [Phase 4: Fix ABS `_add_growth_rates()` No-Op Bug](./phase-04-abs-growth-rate-bugfix.md) | Completed | — |
| 5 | [Phase 5: PDF Report Data Enrichment](./phase-05-pdf-report-data-enrichment.md) | Completed | — |
| 6 | [Phase 6: Web UI Report Parity](./phase-06-web-ui-report-parity.md) | Completed | — |
| 7 | [Phase 7: Sync Docs to Implementation](./phase-07-docs-sync.md) | Completed | 2, 3, 4, 5, 6 |

Phases 1-3 (LLM worker) and 4 (ABS bugfix) and 5-6 (report data) touch disjoint
files/services and can be executed in parallel by separate workstreams once
Phase 1 lands (Phase 2 and 3 both depend only on Phase 1; Phases 4, 5, 6 have
no dependencies and can start immediately). Phase 7 is a wrap-up pass and must
run last.

## Success Criteria

- [x] `LLM_PROVIDER` env var selects between `openai` / `anthropic` / `google`; each produces valid `LlmOutput` JSON against the existing Pydantic schema with no changes to `tasks.py`'s call site, and `llm_model_version` correctly reflects whichever provider ran.
- [x] A non-mutating quota check and a bounded token wait run before every LLM API request; a forced quota-exceeded/rate-limit condition demonstrably delays/retries instead of bursting through, and never leaves a report silently stuck in `PROCESSING`.
- [x] A property with 2+ *consecutive* years of cached ABS time-series data shows non-null `*_growth_pct_yoy` fields — including properties whose LGA was already cached before this plan shipped.
- [x] Full-report PDF renders an "Infrastructure" section and shows risk `.detail` text + zoning `conflict_note`/`epi_type` when present in `llm_parsed_insights`; the free lite PDF shows none of that analyst-commentary text; malformed LLM text does not crash generation; a previously-cached PDF picks up the new content on next download.
- [x] `apps/public-web` property detail page renders Narrative, Demographic Trend Analysis, ROI Scenarios, and Infrastructure sections **only for authenticated users** — anonymous viewers see today's five sections, unchanged.
- [x] `AGENTS.md`, `docs/06-llm-parser-worker.md`, `docs/current_data_flow.md`, and all other stale-reference files found during review and red-team (README.md, TESTING.md, prompt docstrings, `docs/01-system-architecture.md`, `docs/10-testing-strategy.md`) no longer mention Gemini/NVIDIA as the sole or default provider, and no longer claim rate limiting works when it didn't (until Phase 3 lands).
- [x] All existing unit and integration tests pass; new tests added for provider registry selection, rate-limiter call-site wiring (including the quota-exhaustion-then-FAILED path), auth-gated `/detail` responses, and PDF variant-gating.
- [x] `services/admin-backend`'s quota dashboard widget keeps working during a rolling deploy against either an old or new pod (dual-emit), and no `GeminiQuotaStats`/`gemini_quota` naming survives past the compatibility window.
- [x] No provider API key ever appears in a log line or a `property_reports.error_message` value.
- [x] `services/public-api` and `services/admin-backend` Docker builds succeed against `shared/pdf-renderer`'s updated lockfile.

## Validation Log

### Session 1 — 2026-09-05
**Trigger:** `/ak:plan validate` after initial plan creation
**Questions asked:** 2

#### Questions & Answers

1. **[Contract Verifier / Architecture]** Verification found admin-backend independently duplicates the OpenAI-quota coupling: `services/admin-backend/app/config.py:43` has its own `OPENAI_DAILY_QUOTA` setting, and `app/routers/stats.py:24-54` reads Redis key `openai:daily_count:{today}` directly, returning it as `GeminiQuotaStats.gemini_quota` (consumed by `apps/admin-web/types/index.ts` + `app/page.tsx`). If Phase 1/3 rename the setting and Redis key without touching admin-backend, the admin dashboard's quota widget silently breaks. How should the plan handle this?
   - Options: Fix functional + cosmetic (Recommended) | Fix functional only
   - **Answer:** Fix functional + cosmetic (Recommended)
   - **Rationale:** Prevents a silent cross-service regression and eliminates the last Gemini-specific naming in the API contract, consistent with the overall goal of removing stale provider assumptions from the codebase.

2. **[Scope/Risk]** Verification found `shared/pdf-renderer` has zero test infrastructure today (no pytest dependency, no `tests/` directory). Phase 5 assumed tests could be added/extended. How should Phase 5 handle this?
   - Options: Bootstrap minimal test infra (Recommended) | Manual verification only
   - **Answer:** Bootstrap minimal test infra (Recommended)
   - **Rationale:** Gives the module its first regression test rather than compounding the existing test-coverage gap; small, contained addition (pytest + one text-extraction dependency).

#### Confirmed Decisions
- Admin-backend + admin-web get the same Redis-key/setting rename as llm-parser-worker, plus a `GeminiQuotaStats`→`LlmQuotaStats`/`gemini_quota`→`llm_quota` rename, folded into Phase 3.
- Phase 5 bootstraps `pytest` + a PDF-text-extraction dependency for `shared/pdf-renderer` rather than deferring to manual-only verification.

#### Action Items
- [x] Phase 3: added admin-backend/admin-web related files, implementation steps, success criteria, and an updated risk note (both services must ship together).
- [x] Phase 3: corrected the risk note about Celery task time limits — verified `celery_app.py` sets none today, so the real risk is an unbounded wait during a Redis outage, not a task being killed.
- [x] Phase 5: added test-infra bootstrap steps, dev dependencies, and test file creation; effort updated 1d → 1.5d.
- [x] Phase 7: added `docs/01-system-architecture.md:108`, `docs/10-testing-strategy.md:355`, and `AGENTS.md:219` — found via a broader grep during validation, not caught in the original review's grep.
- [x] Phase 3: effort updated 0.5d → 1d to reflect the added cross-service scope.

#### Impact on Phases
- Phase 3: significantly expanded scope (admin-backend + admin-web now in scope); dependency unchanged (`[1]`).
- Phase 5: expanded scope (test infra bootstrap); dependency unchanged (`[]`).
- Phase 7: two additional doc files added to the grep/fix list; dependency unchanged (`[2, 3, 4, 5, 6]`).

### Verification Results
- **Tier:** Full (7 phases)
- **Claims checked:** ~28 (targeted at claims not already directly verified during the original review's code reads)
- **Verified:** 26 | **Failed:** 2 | **Unverified:** 0

#### Failures (both resolved via user decisions above)
1. [Contract Verifier] Phase 3's Redis-key/setting rename — plan didn't account for `services/admin-backend/app/routers/stats.py:24-54` and `app/config.py:43` also consuming `OPENAI_DAILY_QUOTA`/`openai:daily_count:*`. Resolved: folded into Phase 3.
2. [Fact Checker] Phase 5 assumed `shared/pdf-renderer` had testable infra to extend — `pyproject.toml` declares no `pytest` dependency, no `tests/` directory exists. Resolved: Phase 5 now bootstraps it.

#### Notable verifications (no plan change needed)
- `overlay_table()` exists at `shared/pdf-renderer/pdf_renderer/full_report.py:246` (Phase 5 reference accurate).
- `services/public-api/tests/integration/test_properties.py` and `apps/public-web/vitest.config.ts` exist (Phase 6 references accurate).
- `services/scraper-worker/tests/unit/test_abs_adapter_caching.py` exists but does not reference `_add_growth_rates`/`growth_pct_yoy` — no existing test locks in the Phase 4 bug, safe to fix without touching existing assertions.
- All target doc files (`AGENTS.md`, `docs/06-llm-parser-worker.md`, `docs/04-database.md`, `docs/07-legal-compliance.md`, `docs/current_data_flow.md`) are under the project's 800-LOC guideline; no split needed.
- `services/llm-parser-worker/app/celery_app.py` sets no `time_limit`/`soft_time_limit` — Phase 3's risk note corrected accordingly (see Action Items).

### Whole-Plan Consistency Sweep
- Files reread: `plan.md`, `phase-01-start.md`, `phase-02-llm-provider-abstraction.md`, `phase-03-llm-rate-limit-wiring.md`, `phase-04-abs-growth-rate-bugfix.md`, `phase-05-pdf-report-data-enrichment.md`, `phase-06-web-ui-report-parity.md`, `phase-07-docs-sync.md`
- Decision deltas checked: 2 (admin-backend/admin-web scope added to Phase 3; test-infra bootstrap added to Phase 5)
- Reconciled stale references: `plan.md` Success Criteria (added admin-backend criterion), Phase 3 frontmatter effort (0.5d→1d), Phase 5 frontmatter effort (1d→1.5d), Phase 7 related-files list (2 additional doc files)
- Unresolved contradictions: 0

## Red Team Review

### Session — 2026-09-05
**Reviewers:** 4 (Security Adversary, Failure Mode Analyst, Assumption Destroyer, Scope & Complexity Critic — full tier, 7 phases)
**Findings:** 39 raw findings collected, deduplicated to 16 (all passed the evidence filter — every finding cites file:line)
**Severity breakdown:** 6 Critical, 8 High, 2 Medium
**Disposition:** 16 Accepted (2 with modification following user input), 0 Rejected

**Product decision required and resolved before adjudication:** findings 1-2
below (Phase 6 and Phase 5 paywall leaks) were surfaced to the user as a
product question, not a pure bug-fix choice. User clarified the actual model:
anonymous users get a demo/lite report; logged-in users always have full
access, paying with auto-topped-up daily credits specifically at
**download** time. This resolved both findings as an **authentication gate**
(not a credit/entitlement check) — see Phase 5 and Phase 6 for the applied
fix.

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| 1 | `/detail` endpoints serve paid narrative/trend/ROI content to unauthenticated callers | Critical | Accept (modified: auth-gate via `get_optional_user`, per confirmed product model — not a credit check) | Phase 6 |
| 2 | `build_risk()`/`build_zoning()` extensions leak analyst commentary into the free lite PDF | Critical | Accept (variant-gated) | Phase 5 |
| 3 | `check_daily_quota()` is INCR-then-compare (counts attempts, not successes); exhausted-quota retry path never reaches the FAILED-marking code, stranding reports in `PROCESSING` | Critical | Accept | Phase 3 |
| 4 | Env-var rename (`OPENAI_MAX_RPM`/`OPENAI_DAILY_QUOTA`) misses `infra/k8s/secrets.example.yaml`, root `.env.example`, 2 docs; `extra: "ignore"` makes a missed surface fail silently | Critical | Accept | Phase 1 |
| 5 | `_active_model_name()` hardcoded to `settings.OPENAI_MODEL`, never touched by the provider abstraction — wrong `llm_model_version` audit trail under Anthropic/Google | Critical | Accept | Phase 1 |
| 6 | ABS growth-rate fix unreachable for every already-cached LGA (cache-hit path bypasses the fixed function); own success criterion was false as written | Critical | Accept | Phase 4 |
| 7 | `saved.py` is a third, missed `PropertyDetail` construction site — would 500 without explicit `None` defaults | High | Accept | Phase 6 |
| 8 | Google adapter draft put `GOOGLE_API_KEY` in the URL query string — leaks into logs/DB on any error | High | Accept | Phase 2 |
| 9 | Unescaped LLM free text fed into ReportLab's markup parser — malformed input permanently blocks that property's PDF | High | Accept | Phase 5 |
| 10 | MinIO PDF cache keyed by `report_id` only — new sections would never appear on already-cached (i.e. already-paid-for) reports | High | Accept | Phase 5 |
| 11 | "Ship llm-parser-worker and admin-backend together" isn't achievable with this repo's deploy tooling (no rollout-status waits, sequential apply) | High | Accept (redesigned as dual-emit compatibility window instead of an atomicity assumption) | Phase 3 |
| 12 | Adding `pytest`/`pypdf` as pdf-renderer dev deps breaks `public-api`/`admin-backend` Docker builds (`uv sync --frozen`) | High | Accept | Phase 5 |
| 13 | 8-test integration suite (`test_task_pipeline.py`) not in the file list — will hit real Redis once the throttle is wired in | High | Accept | Phase 3 |
| 14 | Neither new provider adapter handles a 200-with-no-usable-content response; raw model output containing "429" (e.g. a price) can false-positive the retry classifier | Medium | Accept | Phase 2 |
| 15 | Phase 7's stale-reference file list missed ~8 files (README, TESTING.md's phantom `GEMINI_API_KEY`, prompt docstrings, verify scripts) | Medium | Accept | Phase 7 |
| 16 | `Protocol` + dedicated `factory.py` is a novel, type-checker-unenforced pattern; repo already has an `ABC`+registry convention for pluggable backends | Medium | Accept (simplified to match existing convention) | Phase 1 |

### Whole-Plan Consistency Sweep
- Files reread: `plan.md`, `phase-01-start.md`, `phase-02-llm-provider-abstraction.md`, `phase-03-llm-rate-limit-wiring.md`, `phase-04-abs-growth-rate-bugfix.md`, `phase-05-pdf-report-data-enrichment.md`, `phase-06-web-ui-report-parity.md`, `phase-07-docs-sync.md`
- Decision deltas checked: 16 (every accepted finding above)
- Reconciled stale references: all `factory.py` mentions across Phase 1/2 updated to the `providers/__init__.py` registry shape; Phase 1/2's `Protocol` → `abc.ABC` terminology fixed everywhere it appeared; Phase 3's risk note about Redis blocking behavior corrected (was factually backwards); Phase 3's "ship together" requirement replaced with dual-emit design in both Requirements and Architecture; effort estimates recalculated in every phase frontmatter and rolled up into `plan.md`'s `7-9d` → `11-13d`; Success Criteria in `plan.md` rewritten to match the redesigned quota/auth/variant/cache behavior in Phases 1-6, not the original (partially incorrect) drafts.
- Unresolved contradictions: 0

<!-- slug: ingestion-report-improvements -->
