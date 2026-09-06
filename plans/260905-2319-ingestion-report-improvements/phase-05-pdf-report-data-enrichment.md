---
phase: 5
title: "PDF Report Data Enrichment"
status: pending
priority: P2
effort: "2.5d"
dependencies: []
---

# Phase 5: PDF Report Data Enrichment

## Overview

The LLM already extracts `infrastructure[]` (required schema field —
transport/health/education/commercial nearby developments), per-risk `.detail`
free text, and zoning `conflict_note`/`epi_type`, but `shared/pdf-renderer`
never renders them. This is not intentional (per user decision) — surface all
three in the full report PDF. No backend/schema changes needed; the data is
already present in `llm_parsed_insights` passed into
`generate_report_pdf_bytes()`.

**Red-team findings (2026-09-05, accepted) that substantially expanded this
phase:**

1. **`build_risk()`/`build_zoning()` are shared with the free lite PDF
   (Critical).** Both functions the original draft extends are called from
   *both* branches of `build_report`'s story assembly — the `full` branch
   (paid, login required) and the `lite` branch (`GET
   /{property_id}/lite-report/pdf`, Turnstile-only, no login) at
   `full_report.py:1329-1341`. Adding `.detail`/`conflict_note` text
   unconditionally would leak analyst commentary into the free demo report.
   Per the confirmed product model — anonymous users get the demo/lite
   report; logged-in users always have full-report access via credits — this
   must be gated on `variant`, not left unconditional. Fixed below.
2. **Untrusted LLM free text goes straight into ReportLab's markup parser,
   unescaped (High).** `Paragraph(f"<b>{label}:</b> {detail}", ...)` feeds
   `RiskEntry.detail`/`conflict_note`/`InfrastructureItem.description` — text
   the LLM summarizes from scraped, third-party council HTML — into
   ReportLab's mini-XML parser with zero escaping anywhere in this file
   (confirmed: no `xml.sax.saxutils.escape` import exists in
   `full_report.py`). A bare `&` or an unbalanced `<tag>` in that text crashes
   PDF generation. Because the MinIO cache is only written on success, that
   property's paid report becomes permanently undeliverable until someone
   manually edits the offending row. Fixed below with a shared escaping
   helper.
3. **The MinIO PDF cache is keyed by `report_id` only — this phase's new
   sections will never appear on an already-cached report (High).**
   `build_report_pdf_object_key(report_id, variant)`
   (`storage.py:27-31`) has no content/renderer-version component, and both
   consumers (`services/public-api/app/routers/properties.py:280-292`,
   `services/admin-backend/app/routers/reports.py`) check-then-serve the
   cached object before ever calling the renderer again. Every property whose
   report was already downloaded once — i.e. the ones people actually paid a
   credit for — would keep serving pre-Phase-5 bytes forever. Fixed below
   with a renderer-version component in the object key.
4. **Adding `pytest`/`pypdf` as pdf-renderer dev dependencies breaks two
   Docker builds (High).** `shared/pdf-renderer` is a locked path dependency
   of `services/public-api` and `services/admin-backend`
   (`services/public-api/uv.lock` records `ozpr-pdf-renderer`'s
   `requires-dist` verbatim), and both services' Dockerfiles run
   `uv sync --frozen --no-dev`. Changing pdf-renderer's `pyproject.toml`
   without regenerating the consuming lockfiles fails those builds with a
   stale-lockfile error. Fixed below with explicit lockfile-regeneration and
   build-verification steps.

## Requirements

- Functional: full report PDF (variant `"full"` only) includes a new "Infrastructure" section listing each `InfrastructureItem` (type, description, distance_km, expected_completion_year, source_url when present), sorted by `distance_km` ascending (nulls last).
- Functional: the existing "Risk Factors" section shows each risk's `.detail` text under its enum value (flood, bushfire, crime_density) **only in the `full` variant** — the `lite` variant must render identically to today (enum values only, no detail text).
- Functional: the existing "Zoning & Planning" section shows `epi_type` (alongside the existing `epi_name` row) **in both variants** (structured field, not analyst commentary — no paywall concern) and `conflict_note` as a callout paragraph **only in the `full` variant**.
- Functional: every LLM-sourced free-text string rendered via `Paragraph()` (risk `.detail`, `conflict_note`, infrastructure `description`, and — while touching the file — the existing `overlay_table()`/narrative/ROI-disclaimer call sites that already interpolate LLM text unescaped) is passed through a shared `_esc()` helper (`xml.sax.saxutils.escape`) before interpolation.
- Functional: `build_report_pdf_object_key()` includes a renderer-version component (e.g. `reports/{report_id}.v2.pdf`) so this phase's changes are visible on reports generated before it shipped, without needing a bulk cache sweep.
- Non-functional: sections that render "—" placeholder rows today for empty data must keep doing so if `infrastructure` is an empty list (no LLM data) — no broken layout on missing data, consistent with existing patterns in the file.
- Non-functional: adding `shared/pdf-renderer` dev dependencies must not break `services/public-api`'s or `services/admin-backend`'s Docker build — both consumers' `uv.lock` files are regenerated and both Docker builds are verified as part of this phase, not left to CI to discover.

**Test infra found missing during validation (2026-09-05):** `shared/pdf-renderer`
has zero test infrastructure today — `pyproject.toml` declares no `pytest`
dev-dependency and no `tests/` directory exists (not even for the current,
long-shipped report sections). Per user decision, this phase bootstraps a
minimal test harness rather than deferring testing to manual checks only.

## Architecture

**Shared escaping helper**, added near the top of `full_report.py`:
```python
from xml.sax.saxutils import escape as _esc
```
Every `Paragraph(...)` call that interpolates LLM-sourced free text wraps that
text in `_esc(...)` before it reaches the f-string. Static labels
("Flood:", "—", etc.) don't need escaping — only text the LLM wrote.

**Variant-aware `build_risk()`/`build_zoning()`** (currently
`full_report.py:375-384` / `:354-372`) — both gain a `variant: str` parameter:
```python
def build_risk(data, styles, variant: str = "full"):
    rf = data.get("risk_factors", {})
    story = section_title("Risk Factors", styles)
    rows = [
        ("Flood Risk", rf.get("flood", {}).get("risk") or "—"),
        ("Bushfire Risk", rf.get("bushfire", {}).get("risk") or "—"),
        ("Crime Density", rf.get("crime_density", {}).get("rating") or "—"),
    ]
    story.append(two_col_table(rows, styles))
    if variant == "full":
        for label, key in [("Flood", "flood"), ("Bushfire", "bushfire"), ("Crime Density", "crime_density")]:
            detail = rf.get(key, {}).get("detail")
            if detail:
                story.append(Paragraph(f"<b>{label}:</b> {_esc(detail)}", styles["body_small"]))
    return story
```
`build_zoning()` gets the same `variant` parameter; `epi_type` renders in both
variants (structured, non-narrative), `conflict_note` only when
`variant == "full"`. Update **every call site** of `build_risk`/`build_zoning`
in both the `full` and `lite` story-assembly branches to pass `variant`
explicitly — do not rely on the default parameter silently doing the right
thing at only one of the two call sites.

**New section function** (full variant only), following the existing pattern
of `build_risk()`/`build_zoning()`:
```python
def build_infrastructure(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    items = data.get("infrastructure") or []
    story = section_title("Infrastructure", styles)
    if not items:
        story.append(Paragraph("No nearby infrastructure data available.", styles["body_small"]))
        return story

    def sort_key(item: dict) -> float:
        d = item.get("distance_km")
        return d if isinstance(d, (int, float)) else float("inf")

    rows = []
    for item in sorted(items, key=sort_key):
        distance = f"{item['distance_km']:.1f} km" if item.get("distance_km") is not None else "—"
        year = item.get("expected_completion_year") or "—"
        rows.append((item.get("type", "OTHER"), _esc(item.get("description", "")), distance, year))
    story.append(infrastructure_table(rows, styles))  # new small table helper, mirrors overlay_table()
    return story
```
Only called from the `full` branch of the story assembly (`infrastructure` is
never part of the lite/raw-data-only report).

Wire `build_infrastructure(data, styles)` into the `full`-variant story
assembly inside `build_report()` — the section list is built starting around
`full_report.py:1296` (`build_report`, not `generate_report_pdf_bytes`, which
is the outer public function at `:1343`); place the new call after
Connectivity and before Education, matching the LLM output's logical grouping.

**MinIO cache-key versioning** (`shared/pdf-renderer/pdf_renderer/storage.py:27-31`):
```python
_RENDERER_VERSION = "v2"  # bump whenever a rendered section changes in a way that should invalidate cached PDFs

def build_report_pdf_object_key(report_id: str, variant: str = "full") -> str:
    safe_variant = variant.lower().strip() if variant else "full"
    if safe_variant == "full":
        return f"reports/{report_id}.{_RENDERER_VERSION}.pdf"
    return f"reports/{report_id}.{safe_variant}.{_RENDERER_VERSION}.pdf"
```
This is a cache-key change, not a migration — old `reports/{report_id}.pdf`
objects are simply never looked up again after this ships; they become
orphaned storage, not a correctness problem. (Optional cleanup: a
`delete_report_pdf` sweep over old-format keys, already exposed by
`storage.py`; not required for correctness, note as a follow-up if storage
cost matters.)

## Related Code Files

- Modify: `shared/pdf-renderer/pdf_renderer/full_report.py` — add the `_esc()` import and apply it at every LLM-text interpolation site (risk `.detail`, `conflict_note`, infrastructure `description`, and the pre-existing `overlay_table()`/narrative/ROI-disclaimer sites while touching the file); add `variant` parameter to `build_risk()`/`build_zoning()` and update both call sites (full and lite branches); add `build_infrastructure()` + `infrastructure_table()` helper (mirror the existing `overlay_table()` helper at `full_report.py:246`); wire the new section into `build_report()`'s full-variant assembly (around `full_report.py:1296`, not the outer `generate_report_pdf_bytes` at `:1343`).
- Modify: `shared/pdf-renderer/pdf_renderer/storage.py:27-31` — add the `_RENDERER_VERSION` component to `build_report_pdf_object_key()`.
- Reference (no change): `shared/py-types/parceliq_types/llm_output.py` — `InfrastructureItem`, `RiskEntry.detail`, `ZoningAndPlanning.conflict_note`/`epi_type` already exist; no schema change needed.
- Modify: `shared/pdf-renderer/pyproject.toml` — add `pytest>=8` and `pypdf>=5` (or an equivalent lightweight text-extraction library — confirm current best-maintained choice at implementation time) as dev dependencies.
- Modify: `shared/pdf-renderer/uv.lock`, `services/public-api/uv.lock`, `services/admin-backend/uv.lock` — regenerate all three (`uv lock`) after the `pyproject.toml` change; the latter two vendor `ozpr-pdf-renderer` as a locked path dependency and will fail `uv sync --frozen` in CI/Docker if left stale.
- Create: `shared/pdf-renderer/tests/__init__.py`, `shared/pdf-renderer/tests/test_full_report.py` — fixture-based test: build a minimal `llm_parsed_insights` dict with populated `infrastructure`/risk `.detail`/`conflict_note`/`epi_type`, call `generate_report_pdf_bytes(data=fixture, address="Test St", variant="full")` **and** `variant="lite"`, extract text from both PDFs via the new text-extraction dependency, assert the full variant contains the new content and the lite variant does **not**; add a fixture with an unescaped `&`/unbalanced-tag string in `detail`/`description` and assert generation succeeds instead of raising.
- Create: `shared/pdf-renderer/tests/conftest.py` (if pytest fixture sharing is needed across future pdf-renderer tests).

## Implementation Steps

1. Add `pytest` + a PDF-text-extraction library to `pyproject.toml`; create the `tests/` directory and confirm `uv run pytest shared/pdf-renderer/tests/` runs (even with zero tests) before writing any assertions.
2. Regenerate `shared/pdf-renderer/uv.lock`, then `services/public-api/uv.lock` and `services/admin-backend/uv.lock`; run both services' Docker builds (or at minimum `uv sync --frozen --no-dev` in each) locally and confirm they still succeed — do this early, before writing the rendering code, so a lockfile problem is caught immediately rather than at the end of the phase.
3. Add the `_esc()` import and helper usage across all LLM-text interpolation sites in `full_report.py`.
4. Add the `variant` parameter to `build_risk()`/`build_zoning()`; update both the full and lite story-assembly call sites explicitly.
5. Add `infrastructure_table()` helper and `build_infrastructure()`; wire it into the full-variant assembly only.
6. Add the `_RENDERER_VERSION` cache-key component in `storage.py`.
7. Write `test_full_report.py`: full-vs-lite content assertions, plus the malformed-input (unescaped `&`/unbalanced tag) fixture asserting generation succeeds.
8. Manually generate one full-report PDF and one lite-report PDF against the same real `READY` property with non-null infrastructure/detail/conflict_note data; visually confirm the full PDF's new content and layout (no truncation/overlap), and confirm the lite PDF shows no detail/conflict_note/infrastructure content.

## Success Criteria

- [ ] A full report PDF for a property whose `llm_parsed_insights.infrastructure` is non-empty shows an "Infrastructure" section listing each item.
- [ ] A property with a non-null `risk_factors.flood.detail` shows that text under the Flood Risk row **in the full PDF only** — the lite PDF for the same property shows no detail text.
- [ ] A property with a non-null `zoning_and_planning.conflict_note` shows it as a callout in the full PDF's Zoning & Planning section; the lite PDF omits it. `epi_type` appears in both.
- [ ] A property whose LLM-authored text contains `&`, `<`, `>`, or an unbalanced tag still generates a valid PDF in both variants (new regression test).
- [ ] A property with empty/null infrastructure still renders a clean "No nearby infrastructure data available." placeholder, not a broken/empty page.
- [ ] A property whose PDF was already cached in MinIO before this phase shipped shows the new sections on its next download (proves the cache-key version bump works), without requiring any manual cache-clear step.
- [ ] `services/public-api` and `services/admin-backend` Docker builds succeed against the regenerated lockfiles.
- [ ] `uv run pytest shared/pdf-renderer/tests/ -v` passes (new test suite — first one this module has ever had).

## Risk Assessment

Raised from the original "Low" after red-team review: this phase touches a
module three services depend on (`public-api`, `admin-backend`, and
`pdf-renderer` itself), interpolates untrusted third-party-derived text into a
markup parser, and changes a cache key that gates whether paid users ever see
new content. Each of those is addressed above (lockfile regen + build
verification, `_esc()` escaping, cache-key version bump). The remaining risk
is visual layout regression (table width overflow, page-break mid-section) —
mitigated by the manual visual check in step 8, done against **both**
variants this time, not just full.
