---
phase: 3
title: "Wire Rate Limiter & Daily Quota Into the Call Path"
status: completed
priority: P1
effort: "2d"
dependencies: [1]
---

# Phase 3: Wire Rate Limiter & Daily Quota Into the Call Path

## Overview

`services/llm-parser-worker/app/services/rate_limiter.py` defines
`wait_for_token()` and `check_daily_quota()` — a Redis token bucket + daily
counter — but grep across the entire worker shows zero call sites. The LLM
worker currently has no proactive throttle: `parse_with_llm` calls
`llm_client.generate_json(...)` directly (`tasks.py:127`), relying only on
reactive retry-after-429. This phase wires the existing functions in, and
generalizes the (currently OpenAI-hardcoded) Redis key names now that the
active provider is configurable (Phase 1/2).

**Cross-service coupling found during the first validation pass (2026-09-05):**
`services/admin-backend` independently duplicates this quota concept:
`app/config.py:43` has its own `OPENAI_DAILY_QUOTA` setting, and
`app/routers/stats.py:24-54` (`get_gemini_quota_stats()`) reads the Redis key
`openai:daily_count:{today}` directly and returns it as
`GeminiQuotaStats.gemini_quota` — consumed by `apps/admin-web/types/index.ts`
and `apps/admin-web/app/page.tsx`. Per user decision, this phase fixes
admin-backend's coupling **and** renames the Gemini-specific naming
(`GeminiQuotaStats`/`gemini_quota`) to provider-neutral naming end-to-end.

**Red-team findings (2026-09-05, accepted) that substantially reshaped this
phase's design — this is not a "wire it in as-is" phase anymore:**

1. **`check_daily_quota()` is `INCR`-then-compare, not a check (Critical).**
   `rate_limiter.py:88` increments the Redis counter *before* comparing it to
   the limit, and it did so on every task attempt — including retries of the
   same failed property, and including the attempt that itself trips the
   limit. Placed naively before the provider call, the "quota" becomes a count
   of attempts, not successful API calls, and a bad batch (validation
   failures, transient 5xx) burns multiples of the real spend. Fixed below by
   splitting into a non-mutating check and a success-only increment.
2. **The exhausted-quota retry path never reaches the FAILED-marking code
   (Critical).** `tasks.py:205-208`'s `DAILY_QUOTA_EXCEEDED` branch calls
   `self.retry(exc=exc, countdown=3600)` unconditionally, with no
   `self.request.retries >= self.max_retries` guard. With `max_retries=3`
   (`tasks.py:79`) that's 3 retries × 1 hour = 3 hours, not "retried
   tomorrow" as the code comment and this phase's original draft both
   claimed — and when retries exhaust, Celery raises `MaxRetriesExceededError`
   from inside that branch, which never reaches the sibling `FAILED`-marking
   code at `tasks.py:210-220`. The report is left in `PROCESSING` forever with
   no `error_message`. Fixed below with an explicit retry-exhaustion guard.
3. **Interacts with `check_dlq` to create a duplicate-dispatch storm
   (Critical).** `parse_with_llm` sets `status='PROCESSING'` at task start
   (`tasks.py:104-110`), *before* this phase's throttle call. `check_dlq`
   (runs every 15 min, `tasks.py:308-386`) re-dispatches any report that's
   been `PROCESSING` for >10 minutes. A bounded queue backlog under
   `wait_for_token()` can leave a report's `updated_at` stale past 10 minutes
   while it's legitimately waiting its turn, causing DLQ to fire a *second*
   `parse_with_llm` for the same report — which increments the quota counter
   again and lengthens the queue further, a feedback loop. Fixed below by
   refreshing `updated_at` around long waits/retries and bounding
   `wait_for_token()`'s max wait.
4. **The Redis-key-rename "ship together" requirement isn't achievable with
   this repo's deploy tooling (Critical).** `Makefile`'s `deploy` target runs
   `kubectl apply` sequentially with no `kubectl rollout status` wait between
   services, and all three affected Deployments (`llm-parser-worker`,
   `admin-backend`, `admin-web`) run `replicas: 1` with the K8s default
   RollingUpdate strategy — meaning the old pod (writing/reading the
   `openai:*` keys and the `gemini_quota` field) keeps serving traffic
   *during* the new pod's startup, for both services independently. There is
   no atomic cutover. Fixed below with a dual-emit compatibility window
   instead of an atomicity assumption the infrastructure can't provide.

## Requirements

- Functional: a non-mutating quota check runs before the provider call; the Redis counter is incremented only after a successful provider response (so it counts real usage, matching what the admin dashboard should show).
- Functional: `wait_for_token()` has a bounded maximum wait (well under the DLQ's 10-minute staleness window) and raises a retryable error on timeout instead of blocking indefinitely.
- Functional: any code path that schedules a Celery retry with a non-trivial delay also bumps `property_reports.updated_at` so `check_dlq` doesn't mistake a legitimately-scheduled retry for a crashed worker.
- Functional: the daily-quota-exhausted path retries up to a bounded number of times with a delay computed from seconds-until-next-UTC-midnight, and explicitly marks the report `FAILED` with a clear message if retries exhaust before the day rolls over — it must never leave a report silently stuck in `PROCESSING`.
- Functional: Redis keys are no longer hardcoded under an `openai:` prefix (misleading once Anthropic/Google are live) — rename to a provider-neutral prefix (e.g. `llm:rate_limit:*`, `llm:daily_count:*`).
- Functional: `services/admin-backend` and `apps/admin-web` dual-emit/dual-read both the old and new field/Redis-key names for one release (see Architecture), since the deploy tooling cannot guarantee an atomic cutover across services.
- Functional: `GeminiQuotaStats` (Pydantic schema) → `LlmQuotaStats`; `DashboardStats.gemini_quota` field → `llm_quota` (with a deprecated `gemini_quota` alias emitting the same value for one release); matching TypeScript type/fields updated in `apps/admin-web/types/index.ts` and **all four** reference sites in `apps/admin-web/app/page.tsx` (not "the one usage site" — verified by grep: lines 9, 60, 66, 87, including a hardcoded "Gemini API Quota" UI heading).
- Non-functional: `LLM_MAX_RPM` must never be `0` at the point `wait_for_token()` computes `token_interval = WINDOW_SECONDS / MAX_RPM` — Phase 1 already added `ge=1` config validation for this; do not re-introduce the division-by-zero risk here.

## Architecture

**Split the quota primitive** (`rate_limiter.py`):
```python
def is_daily_quota_exhausted() -> bool:
    """Non-mutating check. Read-only GET, never increments."""
    today = time.strftime("%Y-%m-%d")
    count = int(redis_client.get(f"{DAILY_COUNT_KEY_PREFIX}{today}") or 0)
    return count >= settings.LLM_DAILY_QUOTA

def record_llm_request() -> None:
    """Call ONLY after a successful provider response — counts real usage."""
    today = time.strftime("%Y-%m-%d")
    key = f"{DAILY_COUNT_KEY_PREFIX}{today}"
    if redis_client.incr(key) == 1:
        redis_client.expire(key, 86_400)
```
`check_daily_quota()` (the old INCR-then-raise function) is removed, not kept
alongside the new functions — two quota primitives with different semantics
sitting in the same module is a footgun for the next person who wires
something in.

**Bound `wait_for_token()`:**
```python
def wait_for_token(max_wait_seconds: int = 240) -> None:
    deadline = time.monotonic() + max_wait_seconds
    while True:
        if time.monotonic() > deadline:
            raise RuntimeError("RATE_LIMIT: token wait exceeded max_wait_seconds")
        ...  # existing token-bucket logic unchanged
```
240s is comfortably under the DLQ's 600s (10 min) staleness window with
margin for the rest of the task's work.

**`tasks.py` call site**, replacing the two-line version from the original
draft:
```python
from app.services.rate_limiter import is_daily_quota_exhausted, wait_for_token, record_llm_request

...
# 4. Call LLM API
if is_daily_quota_exhausted():
    raise RuntimeError(f"DAILY_QUOTA_EXCEEDED: {settings.LLM_DAILY_QUOTA} requests already used today")
wait_for_token()  # raises RATE_LIMIT on timeout — existing "RATE_LIMIT" string match handles it
raw_json_str = llm_client.generate_json(SYSTEM_PROMPT, user_prompt)
record_llm_request()  # only after a successful response
```

**Fix the exhausted-retry path** in the `except` block (`tasks.py:197-222`):
```python
if "DAILY_QUOTA_EXCEEDED" in err_msg:
    seconds_until_utc_midnight = _seconds_until_next_utc_midnight()
    with db.cursor() as cur:
        cur.execute(
            "UPDATE property_reports SET updated_at = NOW() WHERE id = %s",
            (property_report_id,),
        )
        db.commit()
    try:
        raise self.retry(exc=exc, countdown=seconds_until_utc_midnight, max_retries=24)
    except MaxRetriesExceededError:
        with db.cursor() as cur:
            cur.execute(
                "UPDATE property_reports SET status='FAILED', error_message=%s, updated_at=NOW() WHERE id=%s",
                (err_msg[:1000], property_report_id),
            )
            db.commit()
        raise
```
Apply the same `updated_at` bump before the generic `"RATE_LIMIT"`/`"429"`
retry branch too, so a `wait_for_token()` timeout retry doesn't trip the DLQ
either. `_seconds_until_next_utc_midnight()` is a small new helper (a few
lines using `datetime.now(timezone.utc)`).

**Redis key rename** (already reads `settings.LLM_MAX_RPM`/
`settings.LLM_DAILY_QUOTA` post-Phase-1):
```python
TOKEN_KEY = "llm:rate_limit:tokens"
LAST_REFILL_KEY = "llm:rate_limit:last_refill"
DAILY_COUNT_KEY_PREFIX = "llm:daily_count:"
```
Also fix the module docstring (currently: "Supports Gemini, NVIDIA, GitHub
Models, and Ollama APIs" — stale/inaccurate) to describe the real, generic
design.

**Red-team finding, accepted: the Redis-key-rename migration claim was wrong.**
Only the daily-count keys carry a TTL; `TOKEN_KEY`/`LAST_REFILL_KEY` are
written with a plain `SET` and live forever. After the rename, the old
`openai:rate_limit:tokens`/`openai:rate_limit:last_refill` keys are orphaned
permanently (nothing reads them, nothing expires them) — add a one-time
cleanup step (`DEL openai:rate_limit:tokens openai:rate_limit:last_refill`)
to the deploy runbook. Separately: the daily counter resets to 0 under the new
key name regardless of what the old key held that day — for one calendar day
during cutover, the effective quota is `(whatever the old key already used) +
LLM_DAILY_QUOTA`. This is a bounded, self-correcting, one-day inaccuracy in an
internal cost-tracking counter; per YAGNI, do not build key-migration/copy
logic for it — just note it in the deploy runbook.

**Deployment coordination — dual-emit instead of "ship atomically."**
The original draft required admin-backend and llm-parser-worker to deploy in
lockstep; verified against `Makefile`'s `deploy` target (sequential
`kubectl apply`, no `rollout status` waits) and the three services' K8s
manifests (`replicas: 1`, default RollingUpdate), that guarantee does not
exist in this repo's tooling. Instead:
- `admin-backend`'s `/stats` response includes **both** `llm_quota` (new) and
  `gemini_quota` (deprecated alias, same `LlmQuotaStats` object) for this
  release. Remove `gemini_quota` in a later, separate cleanup once the
  rollout has fully settled — not part of this phase.
- `apps/admin-web` reads `stats.llm_quota ?? stats.gemini_quota` so it works
  against either an old or new admin-backend pod during the rollout window.
- `rate_limiter.py`'s daily-count read/write targets the new `llm:*` key only
  (no dual-read needed there — the one-day quota reset described above is the
  accepted cost of not building that).

## Related Code Files

- Modify: `services/llm-parser-worker/app/services/rate_limiter.py` — replace `check_daily_quota()` with `is_daily_quota_exhausted()` + `record_llm_request()`; add bounded `max_wait_seconds` to `wait_for_token()`; rename the three Redis key constants; fix the stale module docstring.
- Modify: `services/llm-parser-worker/app/tasks.py` — new call-site ordering (quota check → `wait_for_token()` → provider call → `record_llm_request()`); fix the `DAILY_QUOTA_EXCEEDED` retry branch (bounded retries + explicit FAILED fallback + `_seconds_until_next_utc_midnight()` helper); add the `updated_at` bump before both long-delay retry branches; add the import.
- Modify: `services/llm-parser-worker/tests/unit/test_tasks.py` — mock `is_daily_quota_exhausted`, `wait_for_token`, `record_llm_request` in the happy-path test; add a test for the quota-exhausted-then-max-retries-exceeded path asserting the report ends up `FAILED` with a populated `error_message`, not stuck in `PROCESSING`.
- Modify: `services/llm-parser-worker/tests/unit/test_rate_limiter.py` — update for the renamed keys and the new `is_daily_quota_exhausted`/`record_llm_request` split (remove tests for the deleted `check_daily_quota`).
- Modify: `services/llm-parser-worker/tests/integration/test_task_pipeline.py` — **8 test methods** (`:30, 66, 97, 122, 148, 170, 197, 226`) currently patch only `app.tasks.llm_client` and `app.tasks.get_db_connection`; once this phase lands they will hit the real Redis client at import time (`rate_limiter.py`'s module-level `redis_lib.from_url(...)`). Add `patch("app.tasks.is_daily_quota_exhausted", return_value=False)` and `patch("app.tasks.wait_for_token")` (and `patch("app.tasks.record_llm_request")`) to all 8, or add an autouse `conftest.py` fixture that patches all three for the whole integration suite.
- Modify: `services/admin-backend/app/config.py:43` — rename `OPENAI_DAILY_QUOTA` → `LLM_DAILY_QUOTA`.
- Modify: `services/admin-backend/app/routers/stats.py` — rename `get_gemini_quota_stats()` → `get_llm_quota_stats()`; change the hardcoded Redis key from `f"openai:daily_count:{today}"` to `f"llm:daily_count:{today}"`; update `settings.OPENAI_DAILY_QUOTA` → `settings.LLM_DAILY_QUOTA`; remove the obsolete "kept for API compatibility" comment; populate both `llm_quota` and the deprecated `gemini_quota` alias in the response for this release.
- Modify: `services/admin-backend/app/schemas/stats.py` — rename `GeminiQuotaStats` → `LlmQuotaStats`; `DashboardStats` gains `llm_quota: LlmQuotaStats` and keeps `gemini_quota: LlmQuotaStats` as a deprecated, same-valued alias field for this release (remove in a later cleanup, not this phase).
- Modify: `services/admin-backend/.env.example` — rename `OPENAI_DAILY_QUOTA` → `LLM_DAILY_QUOTA`; update the comment pointing at llm-parser-worker's `.env`.
- Modify: `apps/admin-web/types/index.ts` — add `llm_quota` alongside the existing `gemini_quota` field on the dashboard-stats type (both present during the compatibility window).
- Modify: `apps/admin-web/app/page.tsx` — update **all four** references (verified by grep: the `quotaPercentage` calculation, and three further dereferences including a literal `"Gemini API Quota"` heading) to read `stats.llm_quota ?? stats.gemini_quota` and rename the displayed heading to "LLM API Quota".
- Check: `services/admin-backend/tests/` — grep for `gemini_quota`/`GeminiQuotaStats`/`OPENAI_DAILY_QUOTA` in test fixtures/assertions and update, keeping one test asserting the deprecated alias still round-trips correctly.
- Reference (no change): `docs/06-llm-parser-worker.md` — its claim "Redis-backed token bucket to enforce limits strictly across all worker processes" becomes true again after this phase; corrected wording lands in Phase 7 (Docs Sync) since that phase depends on this one.

## Implementation Steps

1. Replace `check_daily_quota()` with `is_daily_quota_exhausted()` + `record_llm_request()` in `rate_limiter.py`; add the bounded `max_wait_seconds` to `wait_for_token()`; rename the three Redis key constants; fix the docstring.
2. Add `_seconds_until_next_utc_midnight()` helper and rewrite `tasks.py`'s call site and the `DAILY_QUOTA_EXCEEDED` except-branch per the Architecture section; add the `updated_at` bump to both long-delay retry branches.
3. Update `test_tasks.py` (new mocks, new FAILED-on-retry-exhaustion test) and `test_rate_limiter.py` (renamed keys, new function split).
4. Add the Redis-mocking fixture/patches to all 8 `test_task_pipeline.py` integration tests.
5. In the same change: rename admin-backend's `OPENAI_DAILY_QUOTA`→`LLM_DAILY_QUOTA` (config.py + .env.example), update `stats.py`'s Redis key to `llm:daily_count:{today}` and its settings reference, rename `GeminiQuotaStats`→`LlmQuotaStats` with the dual-emit `llm_quota`/`gemini_quota` fields, and update all four `apps/admin-web/app/page.tsx` references plus `types/index.ts` to read the new field with a fallback to the old one.
6. Manually verify locally: set `LLM_MAX_RPM=1`, fire 3 `parse_with_llm` calls back-to-back, confirm the 2nd and 3rd visibly block/sleep (log line `"No tokens available, sleeping..."`) rather than firing immediately.
7. Manually verify the admin dashboard's quota widget shows a real, non-zero `llm_quota.used_today` after step 6's test calls.
8. Add a deploy-runbook note (not code): after this phase ships, run `redis-cli DEL openai:rate_limit:tokens openai:rate_limit:last_refill` once against production Redis to clear the now-orphaned keys.

## Success Criteria

- [x] `is_daily_quota_exhausted()` is checked, and `record_llm_request()` is called, exactly once per successful `parse_with_llm` provider call — a failed/retried attempt does not increment the counter.
- [x] Setting `LLM_MAX_RPM=1` and firing 3 tasks in quick succession measurably serializes them (verified via log timestamps or a test with a fake clock).
- [x] Setting `LLM_DAILY_QUOTA=0` causes every `parse_with_llm` call that day to raise `DAILY_QUOTA_EXCEEDED`, retry with a midnight-aligned countdown, and — once `max_retries=24` is exhausted without the day rolling over — mark the report `FAILED` with a populated `error_message`. It must never remain silently stuck in `PROCESSING`.
- [x] A report whose retry is scheduled with a non-trivial countdown does not get double-dispatched by `check_dlq` while the retry is pending (verified by a test asserting `updated_at` is bumped before the retry is scheduled).
- [x] All Redis keys used by the rate limiter are provider-neutral (no `openai:` prefix left in `rate_limiter.py` or `admin-backend/app/routers/stats.py`).
- [x] Admin dashboard quota widget reflects real usage after an LLM call, and keeps working against either an old (`gemini_quota`-only) or new (`llm_quota`-emitting) admin-backend pod during a rolling deploy.
- [x] `apps/admin-web/app/page.tsx` has zero remaining references to a hardcoded "Gemini" label.
- [x] Existing + updated unit and integration tests pass in both `llm-parser-worker` and `admin-backend`.

## Risk Assessment

**Corrected during red-team review:** the original risk note claimed an
unreachable Redis would make `wait_for_token()` "block indefinitely." Traced
through the actual code, a connection failure raises `redis.ConnectionError`
from `pipe.watch(...)`, which is **not** caught by the function's own
`except redis_lib.WatchError` and instead propagates immediately into
`tasks.py`'s generic exception handler → a normal Celery retry. That is not
the real risk. The real risks, both addressed above, are: (a) sustained
multi-writer token-bucket contention during a rolling deploy where old and
new pods briefly both draw from the same bucket, and (b) `wait_for_token()`
genuinely waiting past the DLQ's 10-minute staleness window under a large
backlog (e.g. from `trigger_state_refresh`), which is why it's now bounded to
240s with an explicit timeout error instead of an unbounded loop.

This phase now spans two backend services (`llm-parser-worker`,
`admin-backend`) plus their frontend consumer (`admin-web`). The dual-emit
compatibility window (rather than an assumed atomic deploy) is the key
mitigation — verify the fallback (`stats.llm_quota ?? stats.gemini_quota`)
actually works by testing admin-web against an admin-backend pod that has
*not* yet deployed this phase's changes, not just the fully-updated pair.
