## Context

This design replaces subscription-tier gating with a deterministic credit system while preserving the existing property/report production pipeline:

- `properties` to `property_reports` stays 1:1
- Once report status is `READY`, any authenticated user can download if they have credits
- Anonymous users can trigger report creation but cannot download until authenticated

The design prioritizes:
- Correct accounting under concurrency
- Auditability for finance/support/admin operations
- Smooth migration from existing quota/subscription model

## Goals / Non-Goals

**Goals**
- Charge exactly 1 credit per successful full report download, including duplicate downloads
- Daily grant credits are capped at `X` per AU day, no rollover
- Debit order is daily credits first, then purchased credits (all credits are whole integers)
- Debit credit only after successful PDF retrieval — no refund mechanism
- Support admin manual top-up from a user detail page
- Support anonymous-to-auth request claim and surface claimed requests in My Properties
- Fully decommission Clerk Billing subscription-tier gating, `daily_downloads` table, and `payments.py` router

**Non-Goals**
- Reintroducing report approval/review gates
- Property/report schema redesign (1:1 already enforced)
- Anonymous report download support
- Cross-device anonymous request claiming (cookie-bound only)
- Payment-processor credit purchase (separate OpenSpec change)

## Decisions

### Decision 1: Use append-only ledger + derived wallet snapshot

Use immutable ledger entries as source of truth and maintain a fast wallet snapshot for read performance.

**Tables**

1. `user_credit_wallet`
   - `user_id` (PK/FK)
   - `daily_grant_credits` (int, current-day allowance)
   - `daily_used_credits` (int, current-day consumption)
   - `purchased_credits_balance` (int)
   - `wallet_day_au` (date)
   - `updated_at`

2. `credit_ledger`
   - `id` (uuid PK)
   - `user_id` (FK users)
   - `entry_type` enum: `DAILY_GRANT`, `DOWNLOAD_DEBIT`, `ADMIN_TOPUP`
   - `delta_credits` (signed int)
   - `balance_after` (int, NOT NULL — computed atomically in same transaction)
   - `idempotency_key` (nullable unique)
   - `related_property_id` (nullable)
   - `related_report_id` (nullable)
   - `metadata` (jsonb)
   - `created_at`

**Invariant:** `wallet.purchased_credits_balance == SUM(ledger.delta_credits) for non-daily entries`. The wallet is treated as a materialised view updated atomically alongside each ledger write.

### Decision 2: Strict daily-reset model with no rollover

At first credit-touch each AU day, reconcile wallet day:
- set `wallet_day_au = today_au`
- set `daily_used_credits = 0`
- ensure `daily_grant_credits = X` (from config)
- do not carry unused daily credits

### Decision 3: Every successful download debits 1 credit

No free re-download rule. Duplicate downloads are chargeable.

**UX mitigation:** before debit, provide a precheck endpoint returning whether the user has downloaded this report before and show a warning modal. The precheck is a best-effort advisory hint, not a transactional guarantee.

### Decision 4: Post-download debit model

Credit is debited **only after** successful PDF retrieval. This eliminates the need for a refund mechanism entirely.

Flow:
1. Pre-validate auth + report READY
2. Read wallet — verify spendable credits >= 1 (fast, non-locking read)
3. Retrieve/generate PDF from MinIO cache or renderer
4. Begin DB transaction, acquire per-user advisory lock: `pg_advisory_xact_lock(hashtext('credit:' || user_id::text))`
5. Reconcile daily wallet (if day changed)
6. Atomic debit: deduct 1 credit (daily first, then purchased) with balance check `WHERE spendable >= 1`
7. Write `DOWNLOAD_DEBIT` ledger entry with mandatory `balance_after` and idempotency key
8. If debit succeeds → stream PDF to client
9. If debit fails (race: credits exhausted between step 2–6) → return 403 with guidance

**Accepted race condition:** Between step 2 (check) and step 6 (debit), a parallel session could drain the user's last credit. The user would see "you have credits" but then get a 403 after PDF generation. This is a rare edge case; the cost is wasted compute (PDF is cached in MinIO), not a financial loss. This tradeoff is acceptable.

Once `StreamingResponse` is returned to the ASGI server, the debit is final. No post-stream refund mechanism exists.

### Decision 5: Anonymous request identity and claim

Add `anon_requester_id` to request tracking (cookie + DB column on report/request context).

Anonymous request flow:
- On first anonymous request, server issues `anon_requester_id`
- Cookie attributes: `Secure; SameSite=Strict; HttpOnly; Path=/api`
- Report request stores this key

Claim flow after login:
- Authenticated client calls claim endpoint
- Server attaches unclaimed rows with matching `anon_requester_id` to `requested_by_user_id`
- **Claim window: 7 days** — requests older than 7 days are not claimable
- Claimed rows become visible in My Properties

**Non-goal:** Cross-device claiming is not supported. The `anon_requester_id` is cookie-bound; a user who browses anonymously on one device and authenticates on another cannot claim those requests.

### Decision 6: Public My Properties page

Add `My Properties` page with tabs:
- `Requested`: includes authenticated and claimed-anonymous requests (paginated)
- `Saved`: existing saved list behavior

Requested row fields:
- property id, address, state
- report status
- requested_at
- ready_at (if READY)
- has_downloaded_before flag

### Decision 7: Admin user-friendly credit operations

Admin app adds:
- Users list page (search, paginate)
- User detail page (credit summary, history, top-up form)

Top-up operation writes immutable `ADMIN_TOPUP` ledger entries with reason and actor metadata. Top-up amounts must be positive integers.

### Decision 8: Decommission subscription infrastructure

Fully remove:
- Clerk Billing JWT `pla` claim extraction (`extract_plan_from_jwt`)
- `subscription_tier` field from `UserRow` schema
- `require_active_subscription` dependency
- `payments.py` router (`GET /api/payments/status/{property_id}`)
- `quota.py` module (entire file)
- `daily_downloads` table
- Subscription columns on `users` table (`subscription_tier`, `stripe_customer_id`, `stripe_subscription_id`, `subscription_status`, `current_period_end`)
- Clerk `<PricingTable />` component and subscription UI/copy in public-web
- Admin analytics queries referencing `daily_downloads` (migrate to `credit_ledger`)

## API Contracts (Proposed)

### Public API

1. `GET /api/credits/me`
   - Returns wallet summary: daily remaining, purchased balance, total spendable

2. `GET /api/properties/{property_id}/full/precheck`
   - Returns `is_duplicate_download`, previous_download_at, spendable credits
   - Best-effort advisory hint — not a transactional guarantee

3. `GET /api/properties/{property_id}/full/pdf`
   - Performs PDF retrieval, then atomic debit on success
   - Returns 403 if credits insufficient at debit time

4. `POST /api/properties/claim-anonymous-requests`
   - Claims prior anonymous requests (within 7-day window) for current user

5. `GET /api/properties/my/requested`
   - Returns paginated requested history for current user

### Admin Backend

1. `GET /users`
   - Paginated user list + credit summary fields

2. `GET /users/{user_id}`
   - User profile + wallet + recent ledger

3. `POST /users/{user_id}/credits/top-up`
   - Body: `{ credits, reason }` — credits must be positive integer
   - Writes `ADMIN_TOPUP`

## Concurrency + Idempotency

- Advisory lock scoped to user: `pg_advisory_xact_lock(hashtext('credit:' || user_id::text))` — no day scoping since purchased credits span days
- Lock is held only during the brief wallet update + ledger write, not during PDF generation
- Idempotency key for debit attempts to avoid double-charging retried requests

## Migration Plan

1. Add credit schema + indexes
2. Backfill `user_credit_wallet` rows for all existing users (initial `daily_grant_credits = X`, `purchased_credits_balance = 0`)
3. Introduce new endpoints and UI under feature flag (env-var toggle)
4. Switch full PDF entitlement to credits
5. Remove subscription-based entitlement checks, `payments.py` router, `quota.py` module
6. Remove `daily_downloads` table, subscription columns on `users`, Clerk Billing UI
7. Migrate admin analytics queries from `daily_downloads` to `credit_ledger`
8. Implement payment processor purchase flow in a separate OpenSpec change

## Risks / Mitigations

1. **Risk:** Double-charge under retries
   - **Mitigation:** idempotency key + advisory lock + unique index

2. **Risk:** Race between credit check and debit (credits drained by parallel session)
   - **Mitigation:** Atomic debit with balance check; worst case is 403 after PDF generation — no financial loss to user

3. **Risk:** Ambiguous anon claim identity
   - **Mitigation:** random opaque key issuance + `Secure; SameSite=Strict; HttpOnly; Path=/api` cookie + 7-day claim window

4. **Risk:** Admin misuse of top-up
   - **Mitigation:** mandatory reason + actor audit metadata + activity log visibility + positive-integer-only validation
