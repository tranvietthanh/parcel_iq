# Credit Purchase & Payment Integration — Operations Runbook

## Overview

This runbook covers operational procedures for the credit purchase payment integration.
Users buy credits via Stripe checkout; credits are granted by a verified webhook.

**Service boundaries:**
- Checkout + webhook: `services/public-api` → `app/routers/credit_purchases.py`
- Reconciliation: `services/admin-backend` → `app/routers/reconciliation.py`
- Schema: `shared/db-migrations/versions/026_credit_purchase_orders.py`

---

## Key Design Properties

| Property | Behaviour |
|---|---|
| Credit grant timing | ONLY after verified Stripe webhook (not at checkout creation) |
| Advisory lock | Same key as download debit: `pg_advisory_xact_lock(hashtext('credit:' \|\| user_id::text))` |
| Idempotency | `payment_event_receipts` table deduplicates on `provider_event_id` |
| Terminal state guard | Order in `PAID` or `FAILED` is never mutated by a new event |
| Spending order | Purchased credits consumed AFTER daily free credits |
| Refund/clawback | **None.** Credits are non-refundable consumables. Disputes → order `FAILED`, wallet unchanged. |

---

## Reconciliation

### Check for missing credit grants

Run the admin reconciliation endpoint to find `PAID` orders with no `PURCHASE_CREDIT` ledger entry:

```bash
curl -s -H "X-Service-Token: $ADMIN_SERVICE_TOKEN" \
  http://admin-backend:8001/reconciliation/payments | jq .
```

A non-zero `total_missing` means a fulfillment gap: the order was marked `PAID` but credits were not written to the ledger. This can happen if:
- The advisory lock acquisition failed under extreme contention (rare)
- A mid-transaction crash occurred after `UPDATE credit_purchase_orders` but before ledger INSERT

**Resolution for a missing grant:**

```sql
-- 1. Find the user and credit amount from the order
SELECT user_id, credits FROM credit_purchase_orders WHERE id = '<order_id>';

-- 2. Admin top-up via the admin-web UI for the exact credit amount
--    Reason: "Reconciliation top-up for order <order_id>"
--    This is the safe path — it uses the same advisory lock and ledger path
--    as a normal credit grant.
```

> **Do not** manually UPDATE `purchased_credits_balance`. Always go through the admin top-up endpoint to ensure the ledger is consistent.

### Payment summary dashboard

```bash
curl -s -H "X-Service-Token: $ADMIN_SERVICE_TOKEN" \
  "http://admin-backend:8001/reconciliation/payments/summary?window_days=7" | jq .
```

---

## Incident: Webhook Not Firing

Symptoms: User completed checkout (Stripe shows payment success), but credits not added.

1. Check Stripe Dashboard → Webhooks → failed deliveries
2. Retry the `checkout.session.completed` event from Stripe Dashboard — the handler is idempotent
3. If retry succeeds, check `payment_event_receipts` to confirm dedup entry was written
4. If Stripe cannot retry (event expired), use admin top-up as the fallback

---

## Incident: Stripe Webhook Signature Errors

Symptoms: 400 responses logged for webhook endpoint.

Checks:
1. Verify `STRIPE_WEBHOOK_SECRET` matches the signing secret in Stripe Dashboard → Webhooks
2. Ensure the raw request body reaches the handler unmodified (no JSON parsing middleware before signature check)
3. Check for clock skew if signature is within tolerance but still failing

---

## Adding a New Payment Provider

If adding a payment provider beyond Stripe:

1. Create a new webhook handler function (`_handle_<provider>_event`) in `credit_purchases.py`
2. **Must** acquire the same advisory lock before wallet mutation:
   ```python
   await db.execute(
       "SELECT pg_advisory_xact_lock(hashtext('credit:' || $1::text))",
       str(user_id),
   )
   ```
3. Write `PURCHASE_CREDIT` ledger entry with `related_order_id` inside the same transaction
4. Add `provider_event_id` to `payment_event_receipts` for deduplication
5. Set `provider` field to the new provider name on all new rows

---

## No-Clawback Policy

Credits are non-refundable. On a payment dispute or chargeback:
- The `credit_purchase_orders` record transitions to `FAILED` for audit
- No compensating ledger entry is written
- The user's `purchased_credits_balance` is unchanged

This is an explicit product decision. Disputes should be handled commercially with Stripe (e.g., provide evidence to dispute), not by revoking credits from the user.
