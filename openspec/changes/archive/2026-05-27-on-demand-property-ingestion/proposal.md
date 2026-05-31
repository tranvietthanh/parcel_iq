## Why

ParcelIQ currently requires a 3–4 hour upfront property creation pipeline (PostGIS spatial join of 15M addresses × LGA polygons) and admin-managed monthly scrape schedules. Shifting to a thin property import (no spatial join) and user-demand-driven scraping eliminates the bootstrap time burden, reduces infrastructure waste, and naturally prioritises data for properties people actually care about.

## What Changes

- **BREAKING** Replace the 3–4 hour full `properties` import with a thin import — copy basic fields from `gnaf_addresses` without the PostGIS spatial join (~20 min instead of ~4 hours). `lga_id` resolved lazily at report request time.
- **BREAKING** Remove Celery Beat monthly scrape refresh schedules (VIC, NSW) — scraping is triggered only on demand via user requests
- **BREAKING** Remove the admin review queue — LLM reports auto-publish when ready (no `REVIEW_REQUIRED` status, no `review_flag` column)
- **BREAKING** Remove admin scrape trigger and review/approve/reject endpoints
- Modify existing `POST /api/properties/{property_id}/request-scrape` to also accept `gnaf_pid` for properties with no report yet, and perform lazy `lga_id` resolution via PostGIS before dispatching the scrape
- Add simplified status model: `QUEUING → PROCESSING → READY / FAILED` (replaces 8-state model)
- Add `requested_by_user_id` column on `property_reports` — used to send Resend email notification on completion for logged-in requesters
- Add anonymous-to-registered conversion CTA: after requesting a report, anonymous users are prompted to sign up to receive email notification
- Add 10-second polling on the frontend when report status is `QUEUING` or `PROCESSING`
- Keep existing Clerk Billing subscription tiers, quota enforcement, payments router, and `/pricing` page as-is
- Keep DLQ checker task (update status names from `PROCESSING_LLM` → `PROCESSING`)
- Clean `review_flag` references from `pdf_renderer` shared package

## Capabilities

## New Capabilities

- `on-demand-report-request`: Modifying the existing `request-scrape` endpoint to support the full on-demand flow — deduplication check, lazy `lga_id` resolution, QUEUING/PROCESSING/READY status lifecycle, 10s polling, email notification for logged-in users, and anonymous conversion CTA
- `thin-property-import`: Replace the 3–4 hour full spatial-join import with a fast thin import that copies only basic fields (`gnaf_pid`, `address_string`, `geom`, `state`, `address_tokens`) from `gnaf_addresses` — no PostGIS spatial join, `lga_id = NULL`
- `report-ready-email`: Resend email sent to logged-in requesters when their requested property report transitions to `READY`

## Modified Capabilities

_(None — no existing spec files to delta against)_

## Impact

**Removed code:**
- Celery Beat schedule definitions in `services/llm-parser-worker/app/celery_app.py` (monthly VIC/NSW refresh)
- `trigger_state_refresh` task in `services/llm-parser-worker/app/tasks.py`
- Admin review workflow: `review_flag` column, `REVIEW_REQUIRED` status, admin approval/rejection endpoints and UI
- Admin scrape trigger endpoints and UI
- `review_flag` references in `shared/pdf-renderer`

**Modified services:**
- `services/public-api` — modify `request-scrape` endpoint to add lazy `lga_id` resolution, `requested_by_user_id` tracking, deduplication; simplify download auth to `require_auth` (keep quota enforcement); trigger email on READY
- `services/scraper-worker` — simplified status transitions (`PROCESSING` instead of `SCRAPING`)
- `services/llm-parser-worker` — remove `REVIEW_REQUIRED` path; always publish as `READY` or `FAILED`; update `check_dlq` status names; remove `trigger_state_refresh`; add Resend email on READY
- `shared/db-migrations` — new migration: add `requested_by_user_id` to `property_reports`; drop `review_flag`; simplify `status` CHECK constraint
- `shared/pdf-renderer` — remove `review_flag` references
- `apps/public-web` — update PropertyDetail to show QUEUING/PROCESSING states with polling + anonymous CTA
- `apps/admin-web` — remove review queue views and scrape trigger views
- `services/admin-backend` — remove review/approve/reject endpoints and scrape trigger endpoints

**Unchanged (kept as-is):**
- `properties` table structure and queries (map bbox + text search continue to query `properties`)
- Clerk Billing subscription tiers (`FREE`/`PRO`/`UNLIMITED`), `daily_downloads` table, quota enforcement
- `payments.py` router, `/pricing` page, `UnlockButton.tsx`, `/profile` page
- Admin analytics, stats, queue management, task inspection, data source config, LGA listing, user listing, property listing

**Dependencies added:**
- `resend` added to `services/llm-parser-worker` dependencies (for email notification on READY)
