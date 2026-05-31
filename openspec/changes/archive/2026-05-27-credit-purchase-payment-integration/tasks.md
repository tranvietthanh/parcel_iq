## 1. Database + Schema (migration 026)

- [x] 1.1 Create migration for `credit_purchase_orders` (states: PENDING, PAID, FAILED — no REFUNDED)
- [x] 1.2 Add required indexes and uniqueness constraints for provider ids
- [x] 1.3 Add `payment_event_receipts` table for webhook replay protection
- [x] 1.4 Add `PURCHASE_CREDIT` to `credit_entry_type` enum via `ALTER TYPE` (outside transaction)
- [x] 1.5 Update `delta_credits` CHECK constraint on `credit_ledger` to allow PURCHASE_CREDIT > 0
- [x] 1.6 Add `related_order_id UUID FK` column to `credit_ledger` for direct reconciliation JOIN
- [x] 1.7 Add downgrade path (note: `ALTER TYPE ADD VALUE` is not reversible in Postgres — document this)

## 2. Public API

- [x] 2.1 Implement `POST /api/credits/checkout` (min 5 credits, server-validates total)
- [x] 2.2 Implement `POST /api/credits/webhook/stripe` with signature verification (no Clerk auth)
- [x] 2.3 Webhook route must be registered without `require_credits_available` or `get_current_user` dependencies
- [x] 2.4 Implement idempotent order transition logic using `payment_event_receipts` + terminal status guard
- [x] 2.5 Webhook credit grant MUST acquire per-user advisory lock: `pg_advisory_xact_lock(hashtext('credit:' || user_id::text))`
- [x] 2.6 Write `PURCHASE_CREDIT` ledger entry with `related_order_id` populated (inside advisory lock)
- [x] 2.7 Increment `purchased_credits_balance` inside same transaction as ledger write
- [x] 2.8 Implement `GET /api/credits/purchases` — order history (not ledger entries)
- [x] 2.9 Router file must be named `credit_purchases.py` (not `payments.py` — tombstoned)
- [x] 2.10 Dispute/chargeback event: mark order `FAILED`, do NOT write a compensating ledger entry

## 3. Frontend (public-web)

- [x] 3.1 Replace "coming soon" placeholder in `/pricing` page with actual buy-credits UI
- [x] 3.2 Add quantity selector (min 5, price display: 1 credit = $1 AUD)
- [x] 3.3 Integrate checkout redirect flow (POST /api/credits/checkout → redirect to checkout_url)
- [x] 3.4 Add post-checkout success/cancel pages with clear messaging
- [x] 3.5 Show pending/paid order status in user UI (optional — link to /pricing or dedicated page)

## 4. Reliability + Reconciliation

- [x] 4.1 Add reconciliation query: orders in PAID state with no corresponding PURCHASE_CREDIT ledger entry
- [x] 4.2 Add alerts/logging for webhook signature failures and duplicate event replays
- [x] 4.3 Ensure `payment_event_receipts` is written atomically with order + wallet update

## 5. Tests

- [x] 5.1 Unit tests for checkout validation (min 5, pricing formula)
- [x] 5.2 Integration tests for successful payment grant (advisory lock, ledger entry, wallet increment)
- [x] 5.3 Integration tests for webhook replay/idempotency (duplicate event_id ignored)
- [x] 5.4 Integration tests for invalid signature rejection (400, no mutation)
- [x] 5.5 Integration tests for FAILED order on payment failure (no credit grant)
- [x] 5.6 Integration tests for dispute event: order → FAILED, no ledger clawback, wallet unchanged

## 6. Documentation

- [x] 6.1 Update API docs with checkout + webhook contracts
- [x] 6.2 Document no-clawback policy: credits purchased are non-refundable consumables
- [x] 6.3 Document advisory lock requirement for future payment providers
- [x] 6.4 Add operational runbook for reconciliation and incident handling
- [x] 6.5 Link dependency on `credit-based-downloads` change (wallet/ledger, advisory lock key)
