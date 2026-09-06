---
phase: 6
title: "Web UI Report Parity"
status: completed
priority: P2
effort: "2d"
dependencies: []
---

# Phase 6: Web UI Report Parity

## Overview

`apps/public-web`'s property detail page (`PropertyDetail.tsx`) renders only
Education/Connectivity/Risk/Zoning/Demographics. `narrative`,
`demographic_trend_analysis`, `roi_scenarios`, and `infrastructure` exist in
`property_reports.llm_parsed_insights` and render in the PDF, but the
`/api/properties/{id}/detail` endpoint's `PropertyDetail` schema doesn't
expose them at all — this needs a backend change before a frontend change is
possible.

**Confirmed product model (2026-09-05, resolves the red-team's paywall
concern):** anonymous users see a demo/lite report; logged-in users always
have full-report access, paid for with credits (auto-topped-up daily, up to
3/day, purchasable beyond that) specifically at **download** time — viewing
the detail page itself is not a credit-gated action. The fix below is
therefore a simple **authentication** gate (logged in vs not), not a
credit/entitlement check — `/detail` continues to have no credit logic at
all, matching the existing `/full/pdf` vs `/lite-report/pdf` split.

**Red-team findings (2026-09-05, accepted) that reshaped this phase:**

1. **Unauthenticated leak (Critical, now resolved by the auth-gate design
   below).** `GET /{property_id}/detail` and `GET /slug/{slug}/detail` have
   **no auth dependency at all** today (`properties.py:186-213` — only
   `Depends(get_db)`), used identically by anonymous and logged-in callers.
   Adding the four new fields unconditionally would serve full-report content
   to anonymous users, contradicting the confirmed model above. Fixed by
   adding `Depends(get_optional_user)` and conditioning the four new fields on
   `current_user is not None`.
2. **A third `PropertyDetail` construction site was missed (Critical).**
   `services/public-api/app/routers/saved.py:16,105,108-118` also imports
   `_build_detail_sections`/`_normalize_insights` and constructs
   `PropertyDetail(...)` directly, with an explicit kwarg list that does not
   include the four new fields. Without adding them there too — and without
   explicit `= None` defaults on the schema — `GET /api/saved` breaks with a
   Pydantic `ValidationError` (500) the moment this phase ships. Verified:
   `saved.py:88` already requires `Depends(get_current_user)` (hard auth), so
   it's safe to populate the four fields there unconditionally once added —
   no additional gating needed on this endpoint.
3. **The "existing component-per-section style" justification was
   inaccurate.** `apps/public-web/components/property/` has 5 files today;
   none is a section component, and `PropertyDetail.tsx` renders its five
   existing sections **inline** as raw JSX blocks
   (`PropertyDetail.tsx:584,619,639,659,684`). This phase introduces a new
   one-component-per-section pattern — that's a fine, deliberate choice given
   4 new sizeable sections, just not a continuation of an existing one.
4. **No test currently covers `PropertyDetail.tsx`** (verified: the 9-file
   `apps/public-web` test inventory has no test for it). Unlike Phase 5's
   pdf-renderer situation, Vitest infra already exists here
   (`vitest.config.ts` is present and used by other component tests) — this
   is "write a new test using existing infra," not a from-scratch bootstrap,
   so it's scoped as a normal implementation step below, not a separate user
   decision.
5. **Minor, non-blocking:** `saved.py`'s list endpoint (`GET /api/saved`)
   accepts `limit` up to 200 and has no rate-limit decorator (unlike
   `/detail`'s `@limiter.limit("200/hour")`), so populating four
   LLM-prose-heavy fields there increases response size for a user with many
   saved properties. Since the endpoint already requires login (finding 2),
   this is a payload-size/cost concern, not a security one — noted as a
   follow-up, not a blocker for this phase.

## Requirements

- Functional: `GET /{property_id}/detail` and `GET /slug/{slug}/detail` gain `Depends(get_optional_user)`; responses include `narrative`, `demographic_trend_analysis`, `roi_scenarios`, and `infrastructure` **only when the caller is authenticated** (`current_user is not None`). Anonymous callers get exactly today's five sections, unchanged.
- Functional: `GET /api/saved` (`saved.py`) also passes the four new fields through — safe unconditionally since that endpoint already requires login.
- Functional: `apps/public-web` renders each of the four as a new section on the property detail page, following existing component patterns (e.g. `RiskTeaser.tsx`, `MetricCard.tsx`).
- Non-functional: sections render nothing (not an empty box) when the corresponding data is null/absent (either because the LLM hasn't produced it yet, or because the caller is anonymous) — matches existing `PropertyDetail.tsx` pattern of conditionally omitting sections. The frontend does not need to distinguish "anonymous" from "no data yet" — both cases are simply `null`/absent fields.
- Non-functional: `DETAIL_QUERY` (`services/public-api/app/routers/properties.py:76-92`) currently does not select `pr.overall_confidence` at all (unlike `FULL_REPORT_QUERY`) — add it if confidence display is in scope for this phase (see Non-Goals below; confirm with user before adding UI for it, since AGENTS.md still frames `overall_confidence` display as an open, undecided item beyond the "keep review gate removed" decision already made).

## Non-Goals

- This phase does NOT add a manual-review gate or restore `review_flag` — out of scope per standing decision (Phase 7 documents this).
- Whether to surface `overall_confidence` as a user-facing trust signal is a separate product decision not resolved by this plan's clarifying answers — implement the four data sections listed above; leave confidence display out unless/until a follow-up decision is made. Do not infer a design for it.
- No credit/entitlement check on `/detail` or `/saved` — per the confirmed product model, viewing is an authentication-gated action, not a credit-gated one. Do not add `require_credits_available` or any credit-ledger check to these endpoints.
- No pagination/payload-size rework of `GET /api/saved` — the finding above is noted as a follow-up, not part of this phase's scope.

## Architecture

**Backend** (`services/public-api/app/routers/properties.py`):
```python
def _build_detail_sections(
    insights: dict,
    raw_scraped: dict,
    *,
    include_full_sections: bool,
) -> dict[str, dict | list | None]:
    education = _extract_detail_education(insights, raw_scraped)
    connectivity = _extract_detail_connectivity(insights, raw_scraped)
    risk_factors = _extract_detail_risk_factors(insights, raw_scraped)
    zoning_and_planning = _extract_detail_zoning(insights, raw_scraped)
    demographic_snapshot = _extract_detail_demographics(insights, raw_scraped)

    result: dict[str, dict | list | None] = {
        "education": education,
        "connectivity": connectivity,
        "risk_factors": risk_factors,
        "zoning_and_planning": zoning_and_planning,
        "demographic_snapshot": demographic_snapshot,
        "narrative": None,
        "demographic_trend_analysis": None,
        "roi_scenarios": None,
        "infrastructure": None,
    }
    if include_full_sections:
        result["narrative"] = insights.get("narrative") or None
        result["demographic_trend_analysis"] = insights.get("demographic_trend_analysis") or None
        result["roi_scenarios"] = insights.get("roi_scenarios") or None
        result["infrastructure"] = insights.get("infrastructure") or None
    return result
```
`_get_property_detail()` (`properties.py:159-183`) gains a
`current_user: UserRow | None = Depends(get_optional_user)` parameter (already
imported at `properties.py:33`, already used elsewhere at `properties.py:330`
for `/request-scrape`) and passes `include_full_sections=current_user is not None`
into `_build_detail_sections()`. Both route handlers
(`property_detail_by_slug`, `property_detail`) gain the same dependency and
forward it through to `_get_property_detail()`.

`PropertyDetail` schema (`services/public-api/app/schemas/property.py`) gains
four matching optional fields, **all with explicit `= None` defaults**
(required to avoid breaking `saved.py`'s existing 10-kwarg construction call,
which won't pass these four):
```python
narrative: dict | None = None
demographic_trend_analysis: dict | None = None
roi_scenarios: dict | None = None
infrastructure: list | None = None
```

`services/public-api/app/routers/saved.py:108-118` — add the four fields to
its `PropertyDetail(...)` construction, calling
`_build_detail_sections(insights, raw_scraped, include_full_sections=True)`
(safe unconditionally: this endpoint already requires `Depends(get_current_user)`
at line 88).

**Frontend** (`apps/public-web/components/property/`): add sections to
`PropertyDetail.tsx` (816 lines — insert alongside the existing
Education/Connectivity/Risk/Zoning/Demographics blocks, which today are
rendered inline, not via sub-components — this phase introduces new
components for these four specifically, a deliberate choice given their
size). New files:
- `InfrastructureList.tsx` — list/table of nearby infrastructure items.
- `NarrativeSection.tsx` — renders the 7 narrative fields as labeled paragraphs (mirror the PDF's `build_narrative()` ordering: executive_summary, zoning_summary, demographic_story, market_momentum, rental_case, risk_summary, investor_context).
- `TrendAnalysisSection.tsx` — the 7 trend signals + notes (population_momentum, migration_trend, housing_supply_pressure, price_growth_trend, business_health_trend, rental_demand_outlook, overall_investment_signal).
- `RoiScenariosSection.tsx` — 3 scenarios (Conservative/Base/Optimistic) with assumptions + yields, always rendering the `disclaimer` field prominently (matches the Pydantic validator that enforces its presence).

`apps/public-web/types/index.ts` — the `PropertyDetail` TypeScript type
(currently ~12 fields) gains the four new optional fields to match the
backend schema; without this, `tsc` fails once the new components consume
`property.narrative` etc.

## Related Code Files

- Modify: `services/public-api/app/schemas/property.py` — add 4 optional fields to `PropertyDetail`, all with explicit `= None` defaults.
- Modify: `services/public-api/app/routers/properties.py` — add `include_full_sections` parameter to `_build_detail_sections()` (line 536); add `Depends(get_optional_user)` to both `/detail` routes and thread `current_user is not None` through `_get_property_detail()` (line 159-183) into that parameter.
- Modify: `services/public-api/app/routers/saved.py` — pass `include_full_sections=True` when calling `_build_detail_sections()` (line 105) and add the four fields to the `PropertyDetail(...)` construction (lines 108-118).
- Modify: `apps/public-web/components/property/PropertyDetail.tsx` — render the 4 new sections conditionally.
- Modify: `apps/public-web/types/index.ts` — add the four new optional fields to the `PropertyDetail` type.
- Create: `apps/public-web/components/property/InfrastructureList.tsx`
- Create: `apps/public-web/components/property/NarrativeSection.tsx`
- Create: `apps/public-web/components/property/TrendAnalysisSection.tsx`
- Create: `apps/public-web/components/property/RoiScenariosSection.tsx`
- Modify: `services/public-api/tests/integration/test_properties.py` — extend fixtures/assertions to cover the 4 new fields, **including a test asserting an anonymous request to `/detail` does NOT include them even when the underlying report has the data**, and a test asserting an authenticated request does.
- Modify: `services/public-api/tests/` for `saved.py` (find or create the relevant test file) — assert `GET /api/saved` includes the 4 new fields for its already-authenticated caller.
- Create: `apps/public-web/__tests__/components/PropertyDetail.test.tsx` (or wherever the existing 9 component tests live, e.g. alongside `__tests__/components/MetricCard.test.tsx`) — no existing test covers this component; add one covering the 4 new sections' conditional rendering.

## Implementation Steps

1. Extend `PropertyDetail` schema (with explicit `None` defaults) + `_build_detail_sections()` (`include_full_sections` param) + `_get_property_detail()` (auth dependency + threading) on the backend.
2. Update `saved.py`'s call site to pass the four new fields through.
3. Add/extend backend tests: anonymous `/detail` omits the four fields, authenticated `/detail` includes them, `/saved` includes them.
4. Manually hit `GET /api/properties/{id}/detail` once unauthenticated and once authenticated for the same property with populated `narrative`/`demographic_trend_analysis`/`roi_scenarios`/`infrastructure`, and confirm the anonymous response omits all four while the authenticated one includes them.
5. Build the 4 new frontend components, each accepting its typed slice of the API response; add the 4 fields to `types/index.ts`.
6. Wire them into `PropertyDetail.tsx`, matching existing conditional-render-on-null patterns.
7. Add the new `PropertyDetail.test.tsx` covering conditional rendering of the 4 sections.
8. `pnpm --filter public-web test --run`; fix any failures.
9. Manually load the property detail page in a browser: (a) logged out, confirm the 4 new sections do not appear; (b) logged in with a property that has full LLM data, confirm all 4 sections render correctly; (c) logged in with a property still `PROCESSING` (`llm_parsed_insights = null`), confirm none of them render broken/empty boxes.

## Success Criteria

- [x] An unauthenticated `GET /api/properties/{id}/detail` or `/slug/{slug}/detail` never includes `narrative`, `demographic_trend_analysis`, `roi_scenarios`, or `infrastructure`, even when the underlying report has that data.
- [x] An authenticated request to the same endpoints includes all four when present in `llm_parsed_insights`.
- [x] `GET /api/saved` includes all four fields for its (already-authenticated) caller.
- [x] Property detail page on `apps/public-web` visibly renders all 4 new sections for a logged-in user viewing a property with full LLM data, and none of them for a logged-out user viewing the same property.
- [x] Property detail page renders unchanged (no broken sections) for a property still `PROCESSING`/`FAILED`.
- [x] `pnpm --filter public-web test` (including the new `PropertyDetail.test.tsx`) and the relevant `public-api` pytest suites (`test_properties.py` and the `saved.py` test) both pass.

## Risk Assessment

Raised from the original "Low-medium" after red-team review: the auth-gating
requirement is the load-bearing change in this phase — get it wrong (e.g. a
default parameter that silently includes the fields, or a missed call site)
and the confirmed product model (full content behind login) is violated.
Mitigate with the explicit anonymous-vs-authenticated test pair in step 3/4,
and by grepping for every `PropertyDetail(` construction site before
considering this phase done (two are known — `properties.py` and
`saved.py` — confirm no third exists). Main remaining risk is scope creep into
confidence-score UI, which this plan explicitly defers (see Non-Goals) — stay
disciplined to the 4 named sections only.
