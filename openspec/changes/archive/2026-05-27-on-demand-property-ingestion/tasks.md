## 1. Database Migration

- [x] 1.1 Create Alembic migration: add `requested_by_user_id UUID REFERENCES users(id) NULLABLE` to `property_reports`
- [x] 1.2 Create Alembic migration: drop `review_flag` column from `property_reports`
- [x] 1.3 Create Alembic migration: update `status` CHECK constraint — remove `SCRAPING`, `PENDING_LLM`, `PROCESSING_LLM`, `REVIEW_REQUIRED`, `FAILED_SCRAPE`, `FAILED_LLM`; add `QUEUING`, `PROCESSING`; keep `READY`, `FAILED`. Migrate existing rows: `SCRAPING`/`PENDING_LLM`/`PROCESSING_LLM` → `PROCESSING`; `FAILED_SCRAPE`/`FAILED_LLM` → `FAILED`; `REVIEW_REQUIRED` → `READY`
- [x] 1.4 Drop index `idx_reports_review_queue` (was `WHERE review_flag = TRUE`)
- [x] 1.5 Verify migrations run cleanly on fresh DB and against DB with existing READY rows

## 2. Thin Property Import Script

- [x] 2.1 Update the existing properties import script (or create-properties make target) to use thin import: `INSERT INTO properties (gnaf_pid, address_string, geom, state, address_tokens) SELECT gnaf_pid, address_string, geom, state, to_tsvector('simple', address_string) FROM gnaf_addresses`
- [x] 2.2 Remove the PostGIS spatial join (`ST_Contains` against `spatial_zones`) from the import script
- [x] 2.3 Verify thin import completes in ~20 min for 15M rows and text search + bbox map work afterwards

## 3. Public API — Modify `request-scrape` Endpoint

- [x] 3.1 Add lazy `lga_id` resolution: if `properties.lga_id IS NULL`, run `ST_Contains` against `spatial_zones (zone_type='LGA')` and update the property row before dispatching the scrape
- [x] 3.2 Add deduplication: check for existing `property_reports` row with `status IN (QUEUING, PROCESSING, READY)` — if found, return existing status instead of creating new job
- [x] 3.3 Allow re-request for FAILED reports: insert new `property_reports` row with `status = QUEUING`
- [x] 3.4 Set `requested_by_user_id` from `get_optional_user` when user is authenticated
- [x] 3.5 Update status values in the endpoint from `SCRAPING`/`PENDING_LLM`/`PROCESSING_LLM` to `QUEUING`/`PROCESSING`
- [x] 3.6 Update response schema to include `report_id` in the returned payload

## 4. Scraper Worker — Status Simplification

- [x] 4.1 Update `services/scraper-worker/app/tasks.py` and `services/scraper-worker/app/services/db.py`: change initial status write from `SCRAPING` to `PROCESSING`
- [x] 4.2 Remove any `PENDING_LLM` intermediate status update — go directly from scrape complete to dispatching LLM task (status stays `PROCESSING`)
- [x] 4.3 Remove `review_flag = FALSE` from DB update statements in `services/scraper-worker/app/services/db.py`

## 5. LLM Parser Worker — Status + Review Removal

- [x] 5.1 Update `services/llm-parser-worker/app/tasks.py` `parse_with_llm`: change initial status from `PROCESSING_LLM` to `PROCESSING`
- [x] 5.2 Remove `REVIEW_REQUIRED` path — line 139: always set `new_status = "READY"` (remove `if confidence.review_required` branch)
- [x] 5.3 Remove `review_flag` from the UPDATE statement (lines 149, 158)
- [x] 5.4 Change `FAILED_LLM` to `FAILED` in the error handler (line 188)
- [x] 5.5 Remove `trigger_state_refresh` task entirely (lines 203-263)
- [x] 5.6 Update `check_dlq` task: change `PROCESSING_LLM` → `PROCESSING` and `PENDING_LLM` → `QUEUING` (lines 278-306)
- [x] 5.7 Update `celery_app.py` beat_schedule: remove `refresh-vic-monthly` and `refresh-nsw-monthly` entries; keep `check-dlq-every-15m`

## 6. LLM Parser Worker — Email Notification

- [x] 6.1 Add `resend` to `services/llm-parser-worker/pyproject.toml` dependencies
- [x] 6.2 Add `RESEND_API_KEY` to `services/llm-parser-worker/app/config.py` settings
- [x] 6.3 Create `services/llm-parser-worker/app/services/email_service.py` with `send_report_ready_email(to_email, address, property_id)` — mirror the pattern from `services/public-api/app/services/email_service.py`
- [x] 6.4 In `parse_with_llm` task: after writing `READY`, look up `requested_by_user_id` → `users.email` via DB query; if email exists, call `send_report_ready_email` (non-fatal, log warning on failure)

## 7. Shared Packages — Review Flag Cleanup

- [x] 7.1 Remove `review_flag` from `shared/py-types/parceliq_types/property_report.py` (if it exists)
- [x] 7.2 Update any Pydantic models or types that previously referenced `review_flag` or `REVIEW_REQUIRED` field exists — remove it

## 8. Frontend — On-Demand Report Request UX

- [x] 8.1 Update `apps/public-web/components/property/PropertyDetail.tsx`: update status value checks from `SCRAPING`/`PENDING_LLM`/`PROCESSING_LLM` to `QUEUING`/`PROCESSING`
- [x] 8.2 Add 10-second polling: `setInterval` calling `GET /api/properties/{id}/detail` while status is `QUEUING` or `PROCESSING`; clear interval on `READY`, `FAILED`, or panel close/unmount
- [x] 8.3 Add anonymous CTA in the QUEUING/PROCESSING panel: "Sign up or log in to receive an email when this report is ready" with Clerk `<SignUpButton>` / `<SignInButton>`
- [x] 8.4 For logged-in users in QUEUING/PROCESSING panel: show "We'll email you at {email} when your report is ready"
- [x] 8.5 Show error state with "Try again" button when status is `FAILED`

## 9. Admin — Remove Review + Scrape Trigger

- [x] 9.1 Remove review/approve/reject actions from `services/admin-backend/app/routers/reports.py` (keep list/detail endpoints, remove approve/reject/re-parse actions)
- [x] 9.2 Remove `review_flag` filter parameter from report and property list endpoints in admin-backend
- [x] 9.3 Remove `services/admin-backend/app/routers/scrape.py` entirely
- [x] 9.4 Remove corresponding admin-web Server Actions for review + scrape trigger (`apps/admin-web/actions/reports.ts` review actions, `apps/admin-web/actions/scrape.ts`)
- [x] 9.5 Remove admin-web pages for review queue and scrape trigger (`apps/admin-web/app/reports/` review UI, `apps/admin-web/app/scrape/`)
- [x] 9.6 Remove `review_flag` from admin-backend property/report schemas (`services/admin-backend/app/schemas/reports.py`, `services/admin-backend/app/schemas/properties.py`)
- [x] 9.7 Update `awaiting_review` stat in `services/admin-backend/app/routers/stats.py` — remove or zero it out

## 10. Tests

- [x] 10.1 Update `services/llm-parser-worker/tests/unit/test_confidence_scoring.py` — remove `test_llm_review_flag_propagates`
- [x] 10.2 Update `services/llm-parser-worker/tests/unit/test_celery_config.py` — remove `test_beat_schedule_has_vic_refresh` and `test_beat_schedule_has_nsw_refresh`; keep DLQ test
- [x] 10.3 Update `services/admin-backend/tests/integration/test_reports.py` — remove review_flag test cases
- [x] 10.4 Add integration test for request-scrape deduplication logic
- [x] 10.5 Add integration test for lazy lga_id resolution
- [x] 10.6 Add unit test for email notification on READY (mock Resend)

## 11. Documentation

- [x] 11.1 Update `docs/current_data_flow.md` — remove human-in-the-loop review workflow, document on-demand ingestion priority queue logic
- [x] 11.2 Update `docs/01-system-architecture.md` — replace `cron/beat schedule` mention with `on-demand priority queue` logic for scrapers
- [x] 11.3 Update `docs/05-scraper-worker.md` — remove beat schedule section, update status names
- [x] 11.4 Update `docs/06-llm-parser-worker.md` — remove REVIEW_REQUIRED section, add email notification
