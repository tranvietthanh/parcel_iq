## Context

This change adds payment processor integration for self-service credit purchases. It is separated from core credit entitlement to reduce rollout risk and allow end-to-end testing using daily auto-grants plus admin top-up first.

The source of truth for balances remains the credit wallet/ledger introduced in the `credit-based-downloads` change.

## Goals / Non-Goals

**Goals**
- Users can purchase additional credits through a checkout flow
- Credits are only granted after verified successful payment webhook
- Processing is idempotent and safe under retries/replays
- Orders are traceable for support and reconciliation

**Non-Goals**
- Changes to download debit logic
- Credit refunds or clawbacks — credits are a non-refundable consumable once purchased
- Changes to anonymous request claim behavior
- Subscription model resurrection

## Decisions

### Decision 1: Purchase order as explicit state machine

Create `credit_purchase_orders` with states:
- `PENDING`
- `PAID`
- `FAILED`

Checkout creates `PENDING`; webhook transitions to `PAID` on success and triggers credit grant, or `FAILED` on payment failure. No `REFUNDED` state — credit clawback is not supported.

### Decision 2: Grant credits via ledger on webhook success

On verified payment success:
- Acquire per-user advisory lock: `pg_advisory_xact_lock(hashtext('credit:' || user_id::text))`
- Write `PURCHASE_CREDIT` ledger entry with `related_order_id`
- Increment `purchased_credits_balance`
- Mark order `PAID`

Credits MUST NOT be granted at checkout-session creation time.

### Decision 3: Idempotency and replay safety

- Store processed payment event id(s) via `payment_event_receipts`
- Ignore duplicate/replayed events once order is in a terminal state (`PAID` or `FAILED`)
- Use transaction + advisory lock on user_id during credit grant

### Decision 4: Pricing constraints server-enforced

Server validates:
- `credits >= 5`
- `unit_price = 100 AUD cents`
- `total = credits * unit_price`

Client-side validation is UX only; server remains authoritative.

### Decision 5: Spending order is unchanged

Purchased credits are consumed **after** the daily allocation — the debit logic in `credits.py` is not modified by this change. Users spending through their daily credits will draw down their purchased pool without any code changes.

### Decision 6: No credit clawback on payment dispute

If Stripe raises a dispute or chargeback, the order status transitions to `FAILED` for record-keeping. **Credits already granted are not clawed back.** This simplifies the system significantly and aligns with the no-refund policy established in the `credit-based-downloads` design.

## API Contracts (Proposed)

1. `POST /api/credits/checkout`
   - Input: `{ credits: number }`
   - Validation: min 5
   - Output: `{ checkout_url, order_id }`

2. `POST /api/credits/webhook/stripe`
   - **No Clerk auth** — called by Stripe, not the user
   - Verifies `Stripe-Signature` header
   - Handles success/failure events
   - Grants credits on success exactly once
   - Router file: `credit_purchases.py` (not `payments.py` — that module is tombstoned)

3. `GET /api/credits/purchases`
   - Auth required (Clerk JWT)
   - Returns order history: status, amount, timestamps, order_id
   - Does not return ledger entries — use `/api/credits/me` for balance

## Data Model (Proposed)

### `credit_purchase_orders`
- `id` uuid pk
- `user_id` fk users
- `credits` int (>=5)
- `unit_price_aud_cents` int
- `total_amount_aud_cents` int
- `status` enum (`PENDING`, `PAID`, `FAILED`)
- `provider` text (`stripe`)
- `provider_checkout_id` text nullable
- `provider_payment_intent_id` text nullable
- `provider_event_id_last` text nullable
- `created_at`, `updated_at`, `paid_at` nullable

### `payment_event_receipts`
- `provider_event_id` pk
- `provider` text
- `processed_at`
- `order_id` fk credit_purchase_orders nullable

### Schema changes to existing tables (migration 026)

The following changes are required to the schema created in migration 024:

```sql
-- 1. Add PURCHASE_CREDIT enum value
--    (Note: ALTER TYPE ADD VALUE cannot run inside a transaction in Postgres)
ALTER TYPE credit_entry_type ADD VALUE 'PURCHASE_CREDIT';

-- 2. Update delta_credits constraint to allow PURCHASE_CREDIT > 0
ALTER TABLE credit_ledger DROP CONSTRAINT credit_ledger_delta_credits_check;
ALTER TABLE credit_ledger ADD CONSTRAINT credit_ledger_delta_credits_check CHECK (
    (entry_type = 'DOWNLOAD_DEBIT' AND delta_credits < 0)
    OR (entry_type IN ('DAILY_GRANT', 'ADMIN_TOPUP', 'PURCHASE_CREDIT') AND delta_credits > 0)
);

-- 3. Add related_order_id to credit_ledger for reconciliation JOIN
ALTER TABLE credit_ledger
    ADD COLUMN related_order_id UUID REFERENCES credit_purchase_orders(id) ON DELETE SET NULL;
```

## Failure Handling

1. **Checkout created but not paid**
   - Order remains `PENDING`, no credits granted
   - User sees pending status; may abandon or retry

2. **Webhook signature invalid**
   - Reject with 400; do not mutate order or wallet
   - Log the failure for monitoring

3. **Webhook delayed**
   - User sees `PENDING` order status; credits appear once success event arrives
   - No polling timeout — credits simply appear when Stripe delivers the event

4. **Payment dispute / chargeback**
   - Record dispute against order for audit purposes
   - **No credit clawback** — credits already granted remain usable
   - Transition order record to `FAILED` if funds are lost

## Risks / Mitigations

1. **Risk:** duplicate webhook credits user twice
   - **Mitigation:** advisory lock + `payment_event_receipts` dedup + terminal status guard

2. **Risk:** mismatch between checkout amount and server price
   - **Mitigation:** server-controlled line items and total validation at checkout creation time

3. **Risk:** support overhead for pending payments
   - **Mitigation:** expose order status in admin user detail view (already shows credit ledger) and add reconciliation query

4. **Risk:** credit grant races with download debit
   - **Mitigation:** webhook grant acquires same per-user advisory lock as `debit_credit()`
