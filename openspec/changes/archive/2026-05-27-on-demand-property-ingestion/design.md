## Context

ParcelIQ currently pre-populates ~15M `properties` rows via a 3–4 hour PostGIS spatial join at deploy time (every GNAF address × every LGA polygon to resolve `lga_id`). It uses Celery Beat to run monthly re-scrapes of entire states, and the admin console includes a review queue that gates LLM-parsed reports before they reach investors.

The new model keeps the `properties` table but populates it with a **thin import** — copying basic fields from `gnaf_addresses` without the spatial join (~20 min). The `lga_id` is resolved lazily when a user requests a report. Scraping is entirely demand-driven via user requests. Admin review is removed.

**Current state being replaced:**
- `properties` table: 15M rows created via full PostGIS spatial join (`lga_id`, `suburb_id` resolved upfront)
- `property_reports.status`: 8 states including `REVIEW_REQUIRED`, `SCRAPING`, `PENDING_LLM`, `PROCESSING_LLM`
- `review_flag` column gating report visibility
- Celery Beat running `refresh-vic-monthly`, `refresh-nsw-monthly`, `check-dlq-every-15m`
- Admin console: review/approve/reject endpoints, scrape trigger endpoints

**What stays unchanged:**
- `properties` table structure and all map/search queries
- Clerk Billing subscription tiers, daily_downloads, quota enforcement
- payments.py router, /pricing page, UnlockButton, /profile page
- Admin: property list, user list, analytics, stats, queue mgmt, task inspection, data source config

## Goals / Non-Goals

**Goals:**
- Reduce bootstrap time from ~4 hours to ~30 minutes by replacing spatial-join import with thin import
- Drive data enrichment (scraping + LLM parsing) organically via user traffic
- Simplify the report status model to 4 states: `QUEUING → PROCESSING → READY / FAILED`
- Auto-publish all LLM reports (no admin review gate)
- Notify logged-in users via Resend email when their requested report is ready
- Prompt anonymous users to sign up after requesting a report (conversion CTA)
- Keep DLQ checker to handle stuck reports (update status names)

**Non-Goals:**
- Changing the subscription/billing model (kept as-is)
- Changing map or text search queries (they continue to query `properties`)
- Removing or restructuring the admin console beyond review+scrape-trigger routes
- Changing the property permalink URL scheme

## Decisions

### Decision 1: Thin properties import (no spatial join)

**Choice:** Replace the full spatial-join import with a simple `INSERT INTO properties SELECT ... FROM gnaf_addresses` that copies only: `gnaf_pid`, `address_string`, `geom`, `state`, and generates `address_tokens` (TSVECTOR). `lga_id`, `suburb_id`, `beds`, `baths`, `estimated_value` are all NULL.

**Rationale:** The spatial join (15M point-in-polygon checks) is the 3-4 hour bottleneck. Skipping it reduces bootstrap to ~20 min. The `lga_id` is only needed when scraping (to dispatch the correct council adapter), so it can be resolved lazily at report-request time with a single-point spatial query (~50ms).

**Alternative considered:** Remove `properties` table entirely and query `gnaf_addresses` for map/search. Rejected — would require rewriting all search and detail queries, changing frontend response schemas, and changing URL structure. Too much disruption for no additional benefit.

```sql
-- Thin import: ~15-20 min for 15M rows
INSERT INTO properties (gnaf_pid, address_string, geom, state, address_tokens)
SELECT gnaf_pid, address_string, geom, state,
       to_tsvector('simple', address_string)
FROM gnaf_addresses;
-- lga_id, suburb_id = NULL (resolved lazily)
-- beds, baths, cars, land_size_sqm, estimated_value = NULL (filled by scraping)
```

---

### Decision 2: Lazy `lga_id` resolution at report request time

**Choice:** When a user requests a report for a property with `lga_id = NULL`, the API runs a PostGIS `ST_Contains` query against `spatial_zones` to resolve it, then updates the `properties` row before dispatching the scrape task.

```sql
SELECT id FROM spatial_zones
WHERE zone_type = 'LGA'
  AND ST_Contains(geom, (SELECT geom FROM properties WHERE id = $1))
LIMIT 1
```

**Rationale:** Single-point spatial queries against the GiST-indexed `spatial_zones` table are ~50ms. This is negligible compared to the 2-3 minute scrape+LLM pipeline that follows.

**Race condition:** Two simultaneous requests for the same property could both try to resolve `lga_id`. This is harmless — both would compute the same value and the UPDATE is idempotent.

---

### Decision 3: Modify existing `request-scrape` endpoint

**Choice:** Modify the existing `POST /api/properties/{property_id}/request-scrape` endpoint rather than creating a new one. Add:
- Deduplication: check for existing non-FAILED `property_reports` row
- `requested_by_user_id` tracking for email notification
- Lazy `lga_id` resolution before dispatch
- Return `{ status, property_id, report_id }` response

**Rationale:** The endpoint already exists, the frontend already calls it from `PropertyDetail.tsx`, and it has the correct Celery dispatch logic. Modifying it avoids creating dead code and maintains backward compatibility.

---

### Decision 4: Simplified 4-state status model

**Choice:** Replace the 8-state model with `QUEUING → PROCESSING → READY / FAILED`.

| Old status | New status |
|---|---|
| PENDING | QUEUING |
| SCRAPING | PROCESSING |
| PENDING_LLM | PROCESSING |
| PROCESSING_LLM | PROCESSING |
| READY | READY |
| FAILED_SCRAPE | FAILED |
| FAILED_LLM | FAILED |
| REVIEW_REQUIRED | _(removed)_ |

**Rationale:** The granular intermediate states were only useful for the admin review workflow. Users only need: waiting / active / done / broken.

---

### Decision 5: Email notification via `requested_by_user_id`

**Choice:** Add `requested_by_user_id UUID REFERENCES users(id) NULLABLE` to `property_reports`. When a logged-in user requests a report, this field is set. When the LLM worker transitions to `READY`, it sends a Resend email if the field is set.

The email send happens inside the LLM parser worker (add `resend` dependency to its `pyproject.toml`). The existing `send_report_ready_email` function in `public-api` serves as the pattern — duplicate a similar function in the LLM worker.

**Anonymous users:** `requested_by_user_id = NULL`. No email sent. Panel shows a "Sign up to get notified" CTA.

**Anonymous-then-registers:** We do not retroactively associate the request. The CTA is a conversion prompt.

---

### Decision 6: Remove review queue, keep everything else in admin

**Choice:** Remove only:
- Review/approve/reject endpoints from `admin-backend` (routers/reports.py review actions)
- Scrape trigger endpoints from `admin-backend` (routers/scrape.py)
- Corresponding admin-web pages and Server Actions

Keep: property list, user list, analytics, stats, queue management, task inspection, data source config, LGA listing.

**Rationale:** The review queue is the only workflow being fundamentally changed. The rest of the admin console is still operationally useful.

---

### Decision 7: Keep DLQ checker, remove only Beat refresh schedules

**Choice:** Keep the `check_dlq` task but:
- Update it to look for `PROCESSING` instead of `PROCESSING_LLM`
- Remove `trigger_state_refresh` task entirely
- Remove the Beat schedule entries for `refresh-vic-monthly` and `refresh-nsw-monthly`
- Keep the `check-dlq-every-15m` schedule entry (or run it differently)

**Rationale:** With on-demand scraping, stuck reports matter more — a user is actively waiting. The DLQ checker is a safety net that should remain.

**Open question:** Celery Beat is being kept solely for `check-dlq-every-15m`. Alternatives: run `check_dlq` as a startup hook in the worker, or keep a minimal Beat container for just this one schedule.

## Risks / Trade-offs

**Risk: `lga_id` resolution fails for some addresses**
→ Mitigation: Property can have `lga_id = NULL`. Scrape still proceeds with `state` from the properties row as fallback for adapter dispatch. VicPlan adapter uses lat/lng directly, not `lga_id`.

**Risk: LLM output quality without human review**
→ Mitigation: Pydantic v2 strict validation still runs. If validation fails, report goes to `FAILED`. Confidence scores still stored. A future change can re-introduce soft review if needed.

**Risk: Resend email fails (Resend outage)**
→ Mitigation: Non-fatal — log the failure, report still transitions to READY. User can always come back and check.

**Risk: Stuck reports with no DLQ checker if Beat is removed**
→ Mitigation: Keep DLQ checker. Either keep a minimal Beat container or use an alternative scheduling mechanism.

## Migration Plan

1. **Deploy DB migration** (zero-downtime):
   - Add `requested_by_user_id` column to `property_reports`
   - Drop `review_flag` column from `property_reports`
   - Update `status` CHECK constraint (remove `REVIEW_REQUIRED`, `SCRAPING`, `PENDING_LLM`, `PROCESSING_LLM`, `FAILED_SCRAPE`, `FAILED_LLM`; add `QUEUING`, `PROCESSING`)
   - Migrate existing status values: `SCRAPING`/`PENDING_LLM`/`PROCESSING_LLM` → `PROCESSING`; `FAILED_SCRAPE`/`FAILED_LLM` → `FAILED`
   - Existing READY reports remain intact

2. **Deploy backend services** (new images):
   - `public-api`: modified request-scrape endpoint with lazy lga_id + deduplication
   - `llm-parser-worker`: remove REVIEW_REQUIRED path, remove trigger_state_refresh, update DLQ checker, add Resend email
   - `scraper-worker`: simplified status transitions
   - `admin-backend`: remove review + scrape-trigger endpoints

3. **Deploy frontend** (new images):
   - `public-web`: update PropertyDetail polling + QUEUING state + anonymous CTA
   - `admin-web`: remove review queue + scrape trigger pages

4. **Update thin import script** — replace full spatial-join import with simple INSERT

5. **Rollback:** DB migration is reversible — `review_flag` can be re-added as nullable, old status values can be re-introduced.

## Open Questions

**Celery Beat for DLQ:** Keep a minimal Beat container just for `check-dlq-every-15m`, or switch to an alternative scheduler (e.g., APScheduler inside the worker process)?
