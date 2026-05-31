# ParcelIQ — Code Review

**Date:** 2026-05-26  
**Scope:** Full monorepo (`parcel_iq.zip`) — public-api, admin-backend, scraper-worker, llm-parser-worker, shared libraries, DB migrations  
**Total findings:** 14 across Security (4), Logic (3), Performance (4), Code Quality (3)

---

## Table of Contents

1. [Finding Index](#finding-index)
2. [Security Risks](#security-risks)
   - [SEC-1 · JWKS cache never expires](#sec-1--jwks-cache-never-expires--critical)
   - [SEC-2 · Webhook secret timing attack](#sec-2--webhook-secret-timing-attack--high)
   - [SEC-3 · PII stripping too narrow](#sec-3--pii-stripping-too-narrow--high)
   - [SEC-4 · Rate limit key trusts unverified JWT](#sec-4--rate-limit-key-trusts-unverified-jwt--medium)
3. [Logic Gaps](#logic-gaps)
   - [LOG-1 · Quota TOCTOU race condition](#log-1--quota-toctou-race-condition--critical)
   - [LOG-2 · DLQ retries without a cap](#log-2--dlq-retries-without-a-cap--high)
   - [LOG-3 · BBOX accepts invalid coordinates](#log-3--bbox-accepts-invalid-coordinates--medium)
4. [Performance Bottlenecks](#performance-bottlenecks)
   - [PERF-1 · PDF generation blocks event loop](#perf-1--pdf-generation-blocks-the-event-loop--high)
   - [PERF-2 · State refresh loads all rows into RAM](#perf-2--state-refresh-loads-entire-state-into-ram--high)
   - [PERF-3 · Saved list is unbounded](#perf-3--saved-properties-list-has-no-pagination--medium)
   - [PERF-4 · record_download uses two round-trips](#perf-4--record_download-uses-two-db-round-trips--low)
5. [Code Quality](#code-quality)
   - [QA-1 · Full PDF endpoint missing rate limit](#qa-1--full-pdf-endpoint-missing-rate-limit-decorator--medium)
   - [QA-2 · Celery app created inline in routers](#qa-2--celery-app-instantiated-inline-in-router-files--low)
   - [QA-3 · Missing Content-Security-Policy header](#qa-3--missing-content-security-policy-header--low)
6. [Positive Observations](#positive-observations)

---

## Finding Index

| ID | Severity | Category | File | Summary |
|----|----------|----------|------|---------|
| SEC-1 | 🔴 Critical | Security | `public-api/core/clerk.py:50` | JWKS cache never expires — key rotation breaks auth |
| SEC-2 | 🔴 High | Security | `public-api/routers/users.py:31,54` | Webhook secret compared with `==` — timing attack |
| SEC-3 | 🔴 High | Security | `scraper-worker/utils/pii.py:45` | PII stripping covers only 2 of many text fields |
| SEC-4 | 🟡 Medium | Security | `public-api/core/rate_limit.py:19` | Rate limit key uses unverified JWT claims |
| LOG-1 | 🔴 Critical | Logic | `public-api/routers/properties.py:221–293` | Quota check and record are not atomic (TOCTOU) |
| LOG-2 | 🔴 High | Logic | `llm-parser-worker/tasks.py:297–345` | DLQ re-dispatches stuck reports with no retry cap |
| LOG-3 | 🟡 Medium | Logic | `public-api/routers/search.py:123–132` | BBOX coordinates not validated for geographic range |
| PERF-1 | 🔴 High | Performance | `public-api/routers/properties.py:156,283` | `generate_report_pdf_bytes` blocks asyncio event loop |
| PERF-2 | 🔴 High | Performance | `llm-parser-worker/tasks.py:241–260` | `trigger_state_refresh` loads entire state into RAM |
| PERF-3 | 🟡 Medium | Performance | `public-api/routers/saved.py:85–90` | `list_saved` fetches all rows with no LIMIT |
| PERF-4 | 🔵 Low | Performance | `public-api/core/quota.py:94–108` | `record_download` uses two DB round-trips |
| QA-1 | 🟡 Medium | Quality | `public-api/routers/properties.py:207` | `property_full_pdf` missing `@limiter.limit()` |
| QA-2 | 🔵 Low | Quality | `public-api/routers/properties.py:39` | Celery app instantiated inline via `os.getenv` |
| QA-3 | 🔵 Low | Quality | `public-api/middleware/security_headers.py` | Missing `Content-Security-Policy` header |

---

## Security Risks

---

### SEC-1 · JWKS cache never expires — **Critical**

**File:** `services/public-api/app/core/clerk.py`, lines 50–56

**Current code:**

```python
@lru_cache(maxsize=1)
def get_jwks() -> dict:
    """Cached JWKS fetch.  Cache is invalidated on app restart."""
    resp = httpx.get(settings.CLERK_PUBLIC_JWKS_URL, timeout=10)
    resp.raise_for_status()
    return resp.json()
```

**Problem:**

`@lru_cache(maxsize=1)` with no TTL means the JWKS is fetched exactly once per process lifetime. Clerk rotates its RS256 signing keys periodically. After a rotation:

- All tokens signed with the new key will fail verification (every authenticated request returns 401) until the pod restarts.
- Depending on the overlap window, tokens signed with the old (now-revoked) key may continue to pass verification — allowing reuse of stolen tokens.

The comment `"Cache is invalidated on app restart"` acknowledges the intent but not the danger of indefinite caching in long-lived pods.

**Fix:**

Replace `lru_cache` with a TTL-aware cache. Retry once with a fresh JWKS on `JWTError` to handle the race between key rotation and token issuance.

```python
# pip install cachetools
from cachetools import TTLCache, cached
from cachetools.keys import hashkey
import threading

_jwks_cache: TTLCache = TTLCache(maxsize=1, ttl=1800)  # 30 min
_jwks_lock = threading.Lock()

def get_jwks() -> dict:
    with _jwks_lock:
        key = hashkey("jwks")
        if key not in _jwks_cache:
            resp = httpx.get(settings.CLERK_PUBLIC_JWKS_URL, timeout=10)
            resp.raise_for_status()
            _jwks_cache[key] = resp.json()
        return _jwks_cache[key]


async def verify_clerk_token(credentials: ...) -> dict | None:
    ...
    try:
        jwks = get_jwks()
        return jwt.decode(credentials.credentials, jwks, ...)
    except JWTError:
        # Key may have rotated — bust cache and retry once
        with _jwks_lock:
            _jwks_cache.clear()
        try:
            jwks = get_jwks()
            return jwt.decode(credentials.credentials, jwks, ...)
        except JWTError:
            return None
```

---

### SEC-2 · Webhook secret timing attack — **High**

**File:** `services/public-api/app/routers/users.py`, lines 31 and 54

**Current code:**

```python
# sync_user (line 31)
if x_webhook_secret != settings.INTERNAL_WEBHOOK_SECRET:
    raise HTTPException(status_code=401, detail="Invalid webhook secret.")

# delete_user_by_webhook (line 54)
if x_webhook_secret != settings.INTERNAL_WEBHOOK_SECRET:
    raise HTTPException(status_code=401, detail="Invalid webhook secret.")
```

**Problem:**

Python's `!=` on strings short-circuits on the first differing byte. Response time varies slightly based on how many leading characters of the secret the attacker has correct. With enough requests, an attacker can reconstruct the `INTERNAL_WEBHOOK_SECRET` byte-by-byte via a timing oracle. This secret guards the user sync and deletion webhooks — compromising it allows an attacker to delete arbitrary user accounts or inject fake users.

**Fix:**

Use `hmac.compare_digest()` which runs in constant time regardless of where the strings diverge:

```python
import hmac

# Both endpoints — replace the != check:
if not hmac.compare_digest(x_webhook_secret, settings.INTERNAL_WEBHOOK_SECRET):
    raise HTTPException(status_code=401, detail="Invalid webhook secret.")
```

> **Note:** The Clerk webhook endpoint in `apps/public-web/app/api/webhooks/clerk/route.ts` correctly uses Svix's cryptographic signature verification (`wh.verify()`). The internal backend hop is the weak link.

---

### SEC-3 · PII stripping too narrow — **High**

**File:** `services/scraper-worker/app/utils/pii.py`, lines 40–51

**Current code:**

```python
def strip_pii_from_scraped_data(data: dict) -> dict:
    text_fields = [
        "council_planning_applications_text",
        "council_meeting_minutes_text",
    ]
    for field in text_fields:
        if field in data and isinstance(data[field], str):
            data[field] = strip_pii(data[field])
    return data
```

**Problem:**

Only two fields are scrubbed. The council adapters (`generic_html.py`, `objective.py`, `tech_one.py`) can return various other free-text fields scraped from development application portals — these often include applicant names, contact emails, phone numbers, and street addresses. Additionally:

1. The TFN regex `\b\d{3}\s?\d{3}\s?\d{3}\b` will false-positive on legitimate data (postcodes, lot numbers, measurements), potentially redacting useful planning information.
2. The ABN regex `\b\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b` can also match non-ABN numbers.

Unredacted PII reaching `property_reports.raw_scraped_data` is a potential breach of the **Privacy Act 1988 (Cth)**, as documented in `docs/07-legal-compliance.md`.

**Fix:**

Apply PII stripping recursively to all string values in the merged dict, rather than a hardcoded allowlist:

```python
def strip_pii_from_scraped_data(data: dict) -> dict:
    """Recursively strip PII from all string values in the scraped data dict."""
    for key, value in data.items():
        if isinstance(value, str):
            data[key] = strip_pii(value)
        elif isinstance(value, dict):
            data[key] = strip_pii_from_scraped_data(value)
        elif isinstance(value, list):
            data[key] = [
                strip_pii_from_scraped_data(item) if isinstance(item, dict)
                else strip_pii(item) if isinstance(item, str)
                else item
                for item in value
            ]
    return data
```

Also tighten the TFN regex with contextual anchors to reduce false positives (e.g. require surrounding non-digit context, or check Luhn-like digit sum for TFNs).

---

### SEC-4 · Rate limit key trusts unverified JWT — **Medium**

**File:** `services/public-api/app/core/rate_limit.py`, lines 14–25

**Current code:**

```python
def rate_limit_key(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = jwt.get_unverified_claims(auth[7:])
            return f"clerk:{payload.get('sub', get_remote_address(request))}"
        except Exception:
            pass
    return get_remote_address(request)
```

**Problem:**

`jwt.get_unverified_claims()` decodes the payload without verifying the signature. This is intentional for performance, but the extracted `sub` is used directly as the rate-limit bucket key without sanitisation. An attacker can:

1. **Target another user:** Craft a structurally-valid JWT (arbitrary payload, invalid signature) with `sub` set to a victim's Clerk user ID. All their requests land in the victim's rate-limit bucket, potentially locking the victim out.
2. **Collapse anonymous buckets:** Use `sub: ""` or `sub: null` to make the key degrade to `clerk:` + `None`, colliding with other similar requests.
3. **Inflate bucket keys:** Use extremely long or special-character `sub` values to pollute the rate-limit store.

**Fix:**

At minimum, sanitise and bound the extracted value:

```python
def rate_limit_key(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = jwt.get_unverified_claims(auth[7:])
            sub = payload.get("sub")
            # Validate sub looks like a Clerk user ID (non-empty, bounded length)
            if sub and isinstance(sub, str) and 1 <= len(sub) <= 64:
                return f"clerk:{sub}"
        except Exception:
            pass
    return get_remote_address(request)
```

For higher security, verify the JWT signature before using its claims (Clerk JWKS is cached, so the overhead is minimal).

---

## Logic Gaps

---

### LOG-1 · Quota TOCTOU race condition — **Critical**

**File:** `services/public-api/app/routers/properties.py`, lines 221–293  
**Related:** `services/public-api/app/core/quota.py`, lines 78–108

**Current code (simplified flow):**

```python
# Step A — check
already_downloaded = await has_downloaded_today(current_user.id, property_id, db)

if not already_downloaded:
    has_quota, used_today, quota_limit = await check_quota_available(...)
    if not has_quota:
        raise HTTPException(403, "Daily quota exceeded.")

# Step B — serve PDF (can take 1–3 seconds)
...
pdf_data = generate_report_pdf_bytes(...)

# Step C — record (too late)
if not already_downloaded:
    await record_download(current_user.id, property_id, db)
```

**Problem:**

Steps A and C are separated by PDF generation. If two requests arrive simultaneously (e.g. user double-clicks download), both pass the quota check before either records. A FREE user with 1 remaining slot can exhaust N downloads simultaneously where N = number of concurrent requests. At `@limiter.limit("200/hour")` (the `property_detail` limit — the full PDF endpoint has **no** rate limit, see QA-1), this is a significant over-consumption vector.

**Fix:**

Make the quota gate atomic using a single `INSERT ... ON CONFLICT DO NOTHING RETURNING id` statement. If the insert returns nothing, the slot was already consumed in a concurrent transaction.

```python
# In quota.py — atomic check-and-record:
async def claim_download_slot(
    user_id: UUID,
    property_id: UUID,
    subscription_tier: str,
    db: asyncpg.Connection,
) -> tuple[bool, int, int | None]:
    """
    Atomically claim a download slot.
    Returns (claimed, used_today, quota_limit).
    claimed=False means quota exceeded or already downloaded.
    """
    quota_limit = TIER_QUOTAS.get(subscription_tier)
    if quota_limit is None:
        return (True, 0, None)  # UNLIMITED

    today_au = await get_current_date_au()

    # Single atomic insert — fails cleanly if already downloaded or quota exceeded
    async with db.transaction():
        used_today = await db.fetchval(
            """
            SELECT COUNT(DISTINCT property_id)
            FROM daily_downloads
            WHERE user_id = $1 AND download_date_au = $2::date
            """,
            user_id, today_au,
        )
        if used_today >= quota_limit:
            return (False, used_today, quota_limit)

        result = await db.fetchval(
            """
            INSERT INTO daily_downloads (user_id, property_id, download_date_au)
            VALUES ($1, $2, $3::date)
            ON CONFLICT (user_id, property_id, download_date_au) DO NOTHING
            RETURNING id
            """,
            user_id, property_id, today_au,
        )
        # result is None if conflict (already downloaded today) — that's fine, allow re-download
        return (True, used_today, quota_limit)
```

Use this single function at the top of `property_full_pdf` before serving the PDF.

---

### LOG-2 · DLQ retries without a cap — **High**

**File:** `services/llm-parser-worker/app/tasks.py`, lines 297–345

**Current code:**

```python
@celery_app.task(name="app.tasks.check_dlq", ...)
def check_dlq(self) -> dict:
    ...
    with db.cursor() as cur:
        cur.execute(
            """SELECT pr.id::text AS report_id, ...
               FROM property_reports pr
               JOIN properties p ON p.id = pr.property_id
               WHERE pr.status = 'PROCESSING'
                 AND pr.raw_scraped_data IS NOT NULL
                 AND pr.updated_at < NOW() - INTERVAL '10 minutes'""",
        )
        stuck_rows = cur.fetchall()

    for row in stuck_rows:
        with db.cursor() as cur:
            cur.execute(
                """UPDATE property_reports
                   SET retry_count = retry_count + 1, updated_at = NOW()
                   WHERE id=%s AND status='PROCESSING'""",
                (row["report_id"],),
            )
            db.commit()
        parse_with_llm.apply_async(kwargs={...})  # re-dispatched unconditionally
```

**Problem:**

`retry_count` is incremented but never read. There is no guard preventing a report from being re-dispatched indefinitely. A report with:

- Malformed `raw_scraped_data` that consistently fails Pydantic validation, or
- A property where the LLM API always returns unparseable output

...will be re-dispatched every 10–15 minutes forever. Each dispatch burns an LLM quota call, then fails, then the DLQ picks it up again. The report never reaches `FAILED` status through this path.

**Fix:**

Add a `retry_count` cap to the query, and mark exhausted reports as `FAILED`:

```python
MAX_DLQ_RETRIES = 5

# In the SELECT:
WHERE pr.status = 'PROCESSING'
  AND pr.raw_scraped_data IS NOT NULL
  AND pr.updated_at < NOW() - INTERVAL '10 minutes'
  AND pr.retry_count < %(max_retries)s   # ← add this

# After the loop — mark the permanently stuck ones as FAILED:
with db.cursor() as cur:
    cur.execute(
        """UPDATE property_reports
           SET status = 'FAILED',
               error_message = 'Exhausted DLQ retries without completing LLM parse.',
               updated_at = NOW()
           WHERE status = 'PROCESSING'
             AND raw_scraped_data IS NOT NULL
             AND updated_at < NOW() - INTERVAL '10 minutes'
             AND retry_count >= %(max_retries)s""",
        {"max_retries": MAX_DLQ_RETRIES},
    )
    db.commit()
```

---

### LOG-3 · BBOX accepts invalid coordinates — **Medium**

**File:** `services/public-api/app/routers/search.py`, lines 123–132

**Current code:**

```python
async def _bbox_search(db: asyncpg.Connection, bbox: str, limit: int) -> FeatureCollection:
    parts = bbox.split(",")
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox must be 'minLng,minLat,maxLng,maxLat'.")
    try:
        min_lng, min_lat, max_lng, max_lat = (float(p) for p in parts)
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox values must be numeric.")

    rows = await db.fetch(BBOX_QUERY, min_lng, min_lat, max_lng, max_lat, limit)
```

**Problem:**

After converting to floats, there is no validation that:

1. Values are within valid geographic ranges: longitude `[-180, 180]`, latitude `[-90, 90]`.
2. `min_lng < max_lng` and `min_lat < max_lat` (inverted bbox).

**Consequences:**

- An inverted bbox (e.g. `maxLng,maxLat,minLng,minLat`) silently returns 0 results with no error, confusing clients.
- Out-of-range values (e.g. `lng=999`) cause `ST_MakeEnvelope` to receive an invalid geometry. Depending on the PostGIS version and configuration, this may return an error, return garbage results, or silently return empty results.
- A bbox spanning most of the globe (e.g. `-180,-90,180,90`) combined with `limit=500` can table-scan the entire `properties` table.

**Fix:**

```python
async def _bbox_search(db: asyncpg.Connection, bbox: str, limit: int) -> FeatureCollection:
    parts = bbox.split(",")
    if len(parts) != 4:
        raise HTTPException(400, "bbox must be 'minLng,minLat,maxLng,maxLat'.")
    try:
        min_lng, min_lat, max_lng, max_lat = (float(p) for p in parts)
    except ValueError:
        raise HTTPException(400, "bbox values must be numeric.")

    # Validate geographic ranges and ordering
    if not (-180 <= min_lng < max_lng <= 180):
        raise HTTPException(400, "Longitude values must satisfy -180 ≤ minLng < maxLng ≤ 180.")
    if not (-90 <= min_lat < max_lat <= 90):
        raise HTTPException(400, "Latitude values must satisfy -90 ≤ minLat < maxLat ≤ 90.")

    rows = await db.fetch(BBOX_QUERY, min_lng, min_lat, max_lng, max_lat, limit)
```

---

## Performance Bottlenecks

---

### PERF-1 · PDF generation blocks the event loop — **High**

**File:** `services/public-api/app/routers/properties.py`, lines 156 and 283

**Current code:**

```python
# lite_report_pdf (line 156) — MISSING run_in_threadpool
pdf_data = generate_report_pdf_bytes(
    data=pdf_insights,
    address=row["address_string"] or "Property Report",
    variant="lite",
)

# property_full_pdf (line 283) — same issue
pdf_data = generate_report_pdf_bytes(
    data=insights,
    address=row["address_string"] or "Property Report",
    variant="full",
)
```

**Contrast with the correctly wrapped MinIO calls:**

```python
exists = await run_in_threadpool(report_pdf_exists, object_key)   # ✅ wrapped
pdf_data = await run_in_threadpool(get_report_pdf_bytes, object_key)  # ✅ wrapped
await run_in_threadpool(put_report_pdf_bytes, object_key, pdf_data)   # ✅ wrapped
# but ↑ generate_report_pdf_bytes is not ↓
```

**Problem:**

`generate_report_pdf_bytes()` is a synchronous, CPU-intensive call (ReportLab or WeasyPrint rendering). Calling it directly in an `async def` route blocks the entire asyncio event loop for the duration of the render — typically 0.5–3 seconds for a full report. During this window, all other concurrent requests on the same worker process are frozen: healthchecks fail, search queries stall, other users' API calls time out.

**Fix:**

```python
# Both endpoints — wrap with run_in_threadpool:
pdf_data = await run_in_threadpool(
    generate_report_pdf_bytes,
    data=insights,
    address=row["address_string"] or "Property Report",
    variant="full",
)
```

If PDF generation is frequently requested, consider moving it to the Celery worker and caching the result in MinIO before the user requests it (pre-warm on report READY).

---

### PERF-2 · State refresh loads entire state into RAM — **High**

**File:** `services/llm-parser-worker/app/tasks.py`, lines 241–260

**Current code:**

```python
with db.cursor() as cur:
    cur.execute(
        """SELECT p.id::text AS property_id, p.gnaf_pid, p.address_string, ...
           FROM properties p
           LEFT JOIN spatial_zones z ON ...
           WHERE p.state = %s
           ORDER BY p.last_scraped_at ASC NULLS FIRST""",
        (state,),
    )
    rows = cur.fetchall()  # ← loads ALL rows for the state into memory

dispatched = 0
for row in rows:
    celery_app.send_task("scraper_worker.tasks.scrape_property", ...)
    dispatched += 1
```

**Problem:**

`fetchall()` materialises every property in the state before any tasks are dispatched. Victoria alone has 2.8 million+ GNAF addresses. Each row contains address strings, coordinates, and LGA names — conservatively 200 bytes each. The full VIC refresh would require ~560 MB of heap memory in the worker pod, likely triggering an OOM kill before dispatch finishes.

**Fix:**

Use a server-side (named) cursor to stream rows in chunks:

```python
BATCH_SIZE = 500

with db.cursor("state_refresh_cursor") as cur:  # named cursor = server-side
    cur.itersize = BATCH_SIZE
    cur.execute(
        """SELECT p.id::text AS property_id, ...
           FROM properties p
           LEFT JOIN spatial_zones z ON ...
           WHERE p.state = %s
           ORDER BY p.last_scraped_at ASC NULLS FIRST""",
        (state,),
    )

    dispatched = 0
    for row in cur:  # fetches BATCH_SIZE rows at a time from PG
        celery_app.send_task(
            "scraper_worker.tasks.scrape_property",
            kwargs={...},
            queue="data_acquisition_queue",
        )
        dispatched += 1

        if dispatched % BATCH_SIZE == 0:
            time.sleep(0.1)  # gentle back-pressure on the broker
            logger.info("[REFRESH] Dispatched %d tasks for state=%s", dispatched, state)
```

---

### PERF-3 · Saved properties list has no pagination — **Medium**

**File:** `services/public-api/app/routers/saved.py`, lines 85–90  
**Related:** `SAVED_LIST_QUERY` lines 22–37

**Current code:**

```python
@router.get("")
async def list_saved(
    current_user: UserRow = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[PropertyDetail]:
    rows = await db.fetch(SAVED_LIST_QUERY, current_user.id)  # no LIMIT

    results: list[PropertyDetail] = []
    for row in rows:
        # Full Python-side detail assembly for EVERY row
        insights = _normalize_insights(row.get("llm_parsed_insights")) or {}
        raw_scraped = _normalize_insights(row.get("raw_scraped_data")) or {}
        detail_sections = _build_detail_sections(insights, raw_scraped)
        results.append(PropertyDetail(...))
    return results
```

**Problem:**

The query has no `LIMIT`. `SAVED_LIST_QUERY` does join `property_reports` via a lateral, and `_normalize_insights()` + `_build_detail_sections()` are called for every row in Python. A power user with 500 saved properties triggers a query returning 500 rows of JSONB, followed by 500 Python-side parse-and-extract operations, all in a single request with no streaming. This will be slow and memory-heavy as usage grows.

**Fix:**

Add `limit` and `offset` query parameters with sensible defaults:

```python
@router.get("")
async def list_saved(
    current_user: UserRow = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    limit: int = Query(default=50, le=200, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[PropertyDetail]:
    rows = await db.fetch(
        SAVED_LIST_QUERY + " LIMIT $2 OFFSET $3",
        current_user.id, limit, offset,
    )
    ...
```

Return total count via a `X-Total-Count` header or a wrapper response type so clients can implement pagination controls.

---

### PERF-4 · `record_download` uses two DB round-trips — **Low**

**File:** `services/public-api/app/core/quota.py`, lines 94–108

**Current code:**

```python
await db.execute(
    """INSERT INTO daily_downloads (user_id, property_id, download_date_au)
       VALUES ($1, $2, $3::date)
       ON CONFLICT (user_id, property_id, download_date_au) DO NOTHING""",
    user_id, property_id, today_au,
)
# Second trip to check if the row now exists:
existing = await db.fetchval(
    """SELECT 1 FROM daily_downloads
       WHERE user_id = $1 AND property_id = $2 AND download_date_au = $3::date""",
    user_id, property_id, today_au,
)
return existing is not None
```

**Problem:**

Two sequential database round-trips to accomplish what one can do. The `INSERT ... ON CONFLICT DO NOTHING RETURNING id` pattern communicates insert-or-no-op in a single statement — the returned value is `None` on conflict, or the new UUID on success.

**Fix:**

```python
result = await db.fetchval(
    """INSERT INTO daily_downloads (user_id, property_id, download_date_au)
       VALUES ($1, $2, $3::date)
       ON CONFLICT (user_id, property_id, download_date_au) DO NOTHING
       RETURNING id""",
    user_id, property_id, today_au,
)
return result is not None  # True = newly inserted, False = already existed
```

---

## Code Quality

---

### QA-1 · Full PDF endpoint missing rate limit decorator — **Medium**

**File:** `services/public-api/app/routers/properties.py`

**Current code:**

```python
@router.get("/{property_id}/lite-report/pdf")
@limiter.limit("100/hour")            # ✅ rate limited
async def lite_report_pdf(request: Request, ...):
    ...

@router.get("/{property_id}/detail")
@limiter.limit("200/hour")            # ✅ rate limited
async def property_detail(request: Request, ...):
    ...

@router.get("/{property_id}/full/pdf")
# ❌ no @limiter.limit() — request: Request not even in the signature
async def property_full_pdf(
    property_id: UUID,
    current_user: UserRow = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> StreamingResponse:
    ...

@router.post("/{property_id}/request-scrape")
@limiter.limit("10/hour")             # ✅ rate limited
async def request_property_scrape(request: Request, ...):
    ...
```

**Problem:**

`property_full_pdf` is the heaviest endpoint in the service (database query + MinIO round-trip + PDF generation). It has no rate limit. A PRO/UNLIMITED user can re-download the same cached PDF at unbounded concurrency — because cached properties cost no quota (the `already_downloaded` path skips the quota check), a loop over cached properties has zero throttle beyond Cloudflare.

**Fix:**

```python
@router.get("/{property_id}/full/pdf")
@limiter.limit("60/hour")
async def property_full_pdf(
    request: Request,          # ← must be first positional for slowapi
    property_id: UUID,
    current_user: UserRow = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> StreamingResponse:
    ...
```

---

### QA-2 · Celery app instantiated inline in router files — **Low**

**Files:**  
- `services/public-api/app/routers/properties.py`, lines 39–49  
- `services/admin-backend/app/routers/properties.py`, lines 31–47

**Current code (both files):**

```python
celery_app = Celery(
    "public-api",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)
```

**Problems:**

1. `os.getenv()` bypasses the validated `settings` object. If `REDIS_URL` is missing from the environment, the app silently defaults to `redis://localhost:6379/0` — which will work in local dev but fail silently in production until the first task is dispatched.
2. The Celery configuration is duplicated identically in two router files. Any routing or configuration change must be applied in two places.
3. Creating a `Celery()` instance at module import time initialises the broker transport layer prematurely — connection errors at import time can crash the entire API process before it starts serving.

**Fix:**

Create a shared Celery factory module in each service:

```python
# services/public-api/app/celery.py
from celery import Celery
from app.config import settings

def make_celery() -> Celery:
    app = Celery(
        "public-api",
        broker=settings.REDIS_URL,
        backend=settings.REDIS_URL,
    )
    app.conf.update(
        task_routes={
            "scraper_worker.tasks.*": {"queue": "data_acquisition_queue"},
            "llm_parser_worker.tasks.*": {"queue": "llm_processing_queue"},
        },
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
    )
    return app

celery_app = make_celery()
```

Then import this singleton in any router that needs it:

```python
# In properties.py router:
from app.celery import celery_app
```

---

### QA-3 · Missing Content-Security-Policy header — **Low**

**File:** `services/public-api/app/middleware/security_headers.py`

**Current code:**

```python
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # ← Content-Security-Policy is absent
        return response
```

**Problem:**

Five of the six recommended OWASP security headers are set. `Content-Security-Policy` is missing. For a JSON API this is lower-risk, but the two PDF download endpoints stream binary content directly. Without a CSP, browsers have more latitude in interpreting response bodies, and any XSS vector in an adjacent service could use these endpoints as exfiltration targets.

**Fix:**

```python
response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
```

For the PDF endpoints specifically, `Content-Disposition: attachment` is already set (good), which forces download rather than inline rendering — but an explicit CSP reinforces this at the browser policy layer.

---

## Positive Observations

The following aspects of the codebase are well-implemented and worth preserving as patterns:

- **Structured Celery retry logic** — `scraper_worker/tasks.py` uses `bind=True`, `acks_late=True`, `reject_on_worker_lost=True`, and exponential backoff (`countdown=30 * (2**retries)`). This is correct and resilient.

- **Parameterised queries throughout** — No raw string interpolation of user-supplied values into SQL. asyncpg's `$N` and psycopg2's `%s` placeholders are used consistently, eliminating SQL injection risk.

- **Lateral join for latest report** — `DETAIL_QUERY`, `FULL_REPORT_QUERY`, and `SAVED_LIST_QUERY` all use `LEFT JOIN LATERAL (... LIMIT 1)` rather than a subquery or application-side filtering. This is the correct, index-friendly pattern for "latest per group" in PostgreSQL.

- **Clerk Billing JWT claim for subscription tier** — Deriving `subscription_tier` from the `pla` JWT claim rather than a database column means subscription state is always consistent with Clerk's source of truth, with zero sync lag.

- **Svix webhook signature verification** — `apps/public-web/app/api/webhooks/clerk/route.ts` correctly uses the Svix SDK's `wh.verify()` method for cryptographic webhook authentication.

- **MinIO PDF caching strategy** — Checking MinIO for a cached PDF before generating is a sound approach. The `build_report_pdf_object_key(report_id, variant)` key strategy using the database `report_id` correctly ties cache validity to the report lifecycle.

- **`robots.txt` compliance in scraper** — `services/scraper-worker/app/utils/robots.py` checks `robots.txt` before scraping, which is important for legal compliance.

- **Migration discipline** — 23 sequential, down-revision-linked Alembic migrations with clear names and explicit `downgrade()` implementations. The schema evolution is traceable and reversible.

---

*Review produced from static analysis of the full monorepo. No runtime testing performed.*
