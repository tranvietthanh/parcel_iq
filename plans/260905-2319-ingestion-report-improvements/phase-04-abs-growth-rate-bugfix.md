---
phase: 4
title: "Fix ABS _add_growth_rates() No-Op Bug"
status: completed
priority: P1
effort: "0.75d"
dependencies: []
---

# Phase 4: Fix ABS `_add_growth_rates()` No-Op Bug

## Overview

`services/scraper-worker/app/adapters/national/abs_census.py` has a
copy-paste error: `_add_growth_rates()` (lines 497-507) is only a docstring —
its body is empty. The actual growth-rate computation loop is instead
appended, unreachable, after the `return` statement of the unrelated
`_has_usable_cached_demographics()` function (lines 518-527), referencing
`sorted_years`/`time_series` which aren't even parameters of that function.
Net effect: `population_growth_pct_yoy`, `house_price_growth_pct_yoy`,
`business_count_growth_pct_yoy`, `dwelling_approvals_growth_pct_yoy` are never
populated in the ABS time series despite `_add_growth_rates(time_series_final,
filtered_years)` being called at line 476 and despite `DemographicTrendAnalysis`
downstream expecting real growth signals to reason about.

**Red-team findings (2026-09-05, accepted) that expanded this phase beyond the
original one-line-move fix:**

1. **The fix is unreachable for every already-cached LGA (Critical).**
   `_add_growth_rates()` is only invoked on a fresh-fetch (cache-miss) path
   (`abs_census.py:476`, inside the block starting at `:201`). On a cache hit,
   `abs_census.py:174-196` returns the stored `enriched_demographics` blob
   verbatim, and `_has_usable_cached_demographics()` only checks that `latest`
   and `time_series` are non-empty dicts — it says nothing about growth keys.
   Every row cached before this fix ships was written by the no-op version, so
   it has no growth keys, is still judged "usable," and short-circuits forever.
   The plan's own original success criterion ("a property with cached
   multi-year ABS data shows non-null growth values on its next scrape") was
   therefore false as written for the majority of production data — every LGA
   the product has ever served. Fixed below by tightening
   `_has_usable_cached_demographics()` to treat a multi-year cached blob
   lacking any growth key as stale, so it self-heals on the next scrape
   instead of needing a manual backfill.
2. **The loop mislabels multi-year gaps as "YoY" (High).** ABS Data-by-Region
   coverage is patchy; `filtered_years` (the loop's `sorted_years` argument)
   can skip years entirely (e.g. `["2016", "2021", "2022"]`). The original
   loop pairs `sorted_years[i]` with `sorted_years[i-1]` regardless of the
   actual year gap, so a 5-year change (2016→2021) would be computed and
   labeled `house_price_growth_pct_yoy` — a materially wrong number, not just
   a missing one, flowing into the LLM prompt, the PDF's literal "House Price
   Growth (YoY)" label (`full_report.py:1081`), and the web UI
   (`PropertyDetail.tsx:697-701`). Fixed below by skipping non-consecutive
   year pairs.

## Requirements

- Functional: `_add_growth_rates()` actually mutates `time_series` in place, adding each measure's growth % only for calendar-consecutive year pairs (skip a pair whose years are not exactly 1 apart — do not label a multi-year change as "YoY").
- Functional: `_has_usable_cached_demographics()` returns immediately after its existing `return` statement (the unreachable code after it is deleted, not preserved elsewhere), **and** treats a cached blob with 2+ years of `time_series` data but zero growth-rate keys anywhere in it as unusable — so it self-heals via the normal cache-miss/refresh path on the next scrape, rather than requiring a manual backfill job.
- Non-functional: no change to the public shape of `abs_census.py`'s adapter output beyond newly-populated (previously always-`None`) growth fields — purely additive within existing dict keys already declared in `_GROWTH_RATE_MEASURES`.
- Non-functional: do not build a one-off backfill script or bulk cache-invalidation job — the self-healing cache check above is sufficient and matches YAGNI; a property only pays the "one extra live fetch" cost the next time it's scraped, which is the existing normal cache-miss cost.

## Architecture

Move the orphaned loop into `_add_growth_rates()`'s body, skip non-consecutive
year pairs, and tighten the cache-usability check:

```python
def _add_growth_rates(
    time_series: dict[str, dict[str, float | int]],
    sorted_years: list[str],
) -> None:
    """Mutates time_series in-place to add year-on-year growth rates.

    Only computes a growth rate for calendar-consecutive year pairs (e.g.
    2021 -> 2022). A gap in coverage (e.g. 2016 -> 2021) is skipped rather
    than mislabeled as a one-year change.
    """
    for i, year in enumerate(sorted_years):
        if i == 0:
            continue
        prev_year = sorted_years[i - 1]
        if int(year) - int(prev_year) != 1:
            continue  # coverage gap -- not a real YoY comparison
        for measure_label, growth_label in _GROWTH_RATE_MEASURES:
            curr = time_series[year].get(measure_label)
            prev = time_series[prev_year].get(measure_label)
            if curr is not None and prev and prev != 0:
                growth = round((curr - prev) / prev * 100, 2)
                time_series[year][growth_label] = growth


def _has_usable_cached_demographics(enriched: dict) -> bool:
    """Return True only when cached demographics include parsed ABS content
    with growth rates already computed where expected.

    A multi-year blob with zero growth-rate keys anywhere in it was written
    by the pre-fix no-op _add_growth_rates() -- treat it as stale so it
    refreshes via the normal cache-miss path instead of needing a backfill.
    """
    if not isinstance(enriched, dict) or not enriched:
        return False

    latest = enriched.get("latest")
    time_series = enriched.get("time_series")
    if not (isinstance(latest, dict) and isinstance(time_series, dict) and time_series):
        return False

    if len(time_series) >= 2:
        growth_labels = {label for _, label in _GROWTH_RATE_MEASURES}
        has_any_growth_key = any(
            isinstance(year_data, dict) and growth_labels & year_data.keys()
            for year_data in time_series.values()
        )
        if not has_any_growth_key:
            return False

    return True
```

## Related Code Files

- Modify: `services/scraper-worker/app/adapters/national/abs_census.py` (lines 497-527) — move the loop into `_add_growth_rates()` with the consecutive-year-pair guard; tighten `_has_usable_cached_demographics()` per the Architecture section.
- Check: `services/scraper-worker/tests/unit/test_abs_adapter_caching.py` — this file exists and covers ABS caching but (verified) does not reference `_add_growth_rates`/`_has_usable_cached_demographics`/`growth_pct_yoy` today, so no existing assertion needs to change — only new tests are added.

## Implementation Steps

1. Move the loop into `_add_growth_rates()` with the consecutive-year-pair guard; delete it from after `_has_usable_cached_demographics()`'s `return`.
2. Tighten `_has_usable_cached_demographics()` per the Architecture section.
3. Add a unit test: feed a 2+ *consecutive*-year cached time series through `_add_growth_rates()` directly, assert each `*_growth_pct_yoy` key is present and numerically correct for the second year onward, and absent for the first year (no prior to compare against).
4. Add a unit test for the coverage-gap case: feed `["2016", "2021", "2022"]` and assert **no** growth key is emitted for 2021 (gap), but one **is** emitted for 2022 (consecutive with 2021).
5. Add unit tests for `_has_usable_cached_demographics()`: (a) a fresh-format blob with growth keys present → usable; (b) a pre-fix blob with 2+ years and zero growth keys → unusable (triggers refresh); (c) a legitimate single-year blob with no growth keys expected → still usable (guards against over-tightening).
6. Run `uv run pytest services/scraper-worker/tests/unit/ -v`.
7. Spot-check one real property whose LGA is **already cached** in `abs_census_data` from before this fix — confirm its *next* scrape treats the cache as stale, re-fetches, and populates real growth figures (this is the scenario the original phase draft's success criterion incorrectly assumed already worked).

## Success Criteria

- [x] `_add_growth_rates()` has a real, non-empty body with the consecutive-year-pair guard; `_has_usable_cached_demographics()` has no unreachable code after its `return`.
- [x] New unit tests prove: growth fields populate correctly for consecutive years, are skipped for coverage gaps, and a pre-fix cached blob is correctly judged unusable so it self-heals.
- [x] A real property whose LGA was cached **before this fix shipped** shows non-null, calendar-consecutive `population_growth_pct_yoy` (etc.) after its next scrape — not just a property that happens to hit a fresh, never-cached LGA.
- [x] `uv run pytest services/scraper-worker/tests/unit/ -v` passes.

## Risk Assessment

Raised from the original "Very low" after red-team review: the fix now
touches cache-usability logic that determines whether the adapter re-fetches
from the ABS API, not just a pure-function bugfix. The self-healing check
means every already-cached LGA takes one extra live ABS API round-trip on its
next scrape rather than serving from cache — acceptable (ABS Data-by-Region is
a low-volume, non-user-facing-latency-critical background fetch), but confirm
this doesn't meaningfully spike ABS API call volume if a very large number of
LGAs get invalidated simultaneously (unlikely — invalidation is per-LGA and
lazy, triggered only when that LGA's cache is next consulted, not a bulk
sweep). The consecutive-year-pair guard is a pure, isolated, low-risk
correctness fix with no side effects beyond the dict it's given.
