# Admin Credit Operations — Manual Top-Up and Reconciliation Runbook

## Overview

This runbook covers operational procedures for administrative credit management, daily credit resets, manual top-ups, and ledger reconciliation within the OZ Property Report platform.

---

## 1. Daily Credit Resets

### Mechanism
- Free daily credits are allocated to active users.
- The reset uses the Australia/Sydney timezone (`Australia/Sydney` / `AEST` / `AEDT`).
- The reset is performed **lazily / Just-in-Time (JIT)** when the user accesses their wallet or triggers a credit check.
- When accessed, the system checks if the wallet's logged day (`wallet_day_au`) is older than the current date in Sydney. If it is, the wallet's `daily_used_credits` is reset to 0, `daily_grant_credits` is set to the configured grant amount (default: 3), and `wallet_day_au` is updated to the current date.
- The day rollover does **not** stack or roll over unused credits from the previous day.

### Configuration
The default daily credit grant amount is configured via the `DAILY_CREDIT_GRANT` environment variable on `services/public-api`.
- Default value: `3`

---

## 2. Manual Credit Top-Up

When a user requires a manual credit adjustment (e.g., support resolution, customer goodwill, testing, or payment reconciliation fallback), admins can top up their account via the Admin Web console.

### Admin Web Flow
1. Navigate to the Admin Console (typically via port-forward): `http://localhost:3001/users`
2. Search for the user by email or Clerk User ID.
3. Click on the user to open the User Details page.
4. Locate the **Manual Credit Top-Up** form.
5. Enter the number of credits to add (must be a positive integer, up to 10,000).
6. Enter a mandatory, detailed **Reason** (e.g., "Reconciled Stripe order ch_12345", "Customer support goodwill").
7. Click **Top Up**. The UI will display a success toast and update the wallet summary and ledger history table.

### API Endpoint (Internal Only)
```bash
POST /users/{user_id}/credits/top-up
```
**Headers Required:**
- `X-Service-Token`: Internal shared service secret
- `X-Admin-User-Id`: Clerk admin user ID of the operator

**Request Body:**
```json
{
  "credits": 5,
  "reason": "Goodwill top-up for support ticket #481"
}
```

---

## 3. Reconciliation & Auditing

Because all credit mutations must be recorded in the ledger, inconsistencies between wallet balances and ledger entries must be detected and resolved.

### Database Auditing Queries

To check consistency between the `user_credit_wallet` record and the sum of ledger mutations:

#### 1. Audit Wallet Balance Consistency
Run this query to find any users whose wallet balances do not align with the sum of historical credit ledger entries:
```sql
WITH ledger_summary AS (
    SELECT 
        user_id,
        SUM(CASE WHEN entry_type = 'DAILY_GRANT' THEN delta_credits ELSE 0 END) AS total_daily_grants,
        SUM(CASE WHEN entry_type = 'PURCHASE_CREDIT' THEN delta_credits ELSE 0 END) AS total_purchased_grants,
        SUM(CASE WHEN entry_type = 'ADMIN_TOPUP' THEN delta_credits ELSE 0 END) AS total_admin_grants,
        SUM(CASE WHEN entry_type = 'DOWNLOAD_DEBIT' THEN delta_credits ELSE 0 END) AS total_debits
    FROM credit_ledger
    GROUP BY user_id
)
SELECT 
    w.user_id,
    w.purchased_credits_balance,
    COALESCE(l.total_purchased_grants + l.total_admin_grants + l.total_debits, 0) AS calculated_purchased_balance,
    w.daily_used_credits,
    -- debits are stored as negative numbers, count debits applied against daily first
    (w.purchased_credits_balance - COALESCE(l.total_purchased_grants + l.total_admin_grants + l.total_debits, 0)) AS balance_skew
FROM user_credit_wallet w
LEFT JOIN ledger_summary l ON w.user_id = l.user_id
WHERE w.purchased_credits_balance != COALESCE(l.total_purchased_grants + l.total_admin_grants, 0) + (
    -- Accounting for debits that spilled over from daily to purchased balance
    SELECT COALESCE(SUM(delta_credits), 0) FROM credit_ledger 
    WHERE user_id = w.user_id AND entry_type = 'DOWNLOAD_DEBIT'
);
```

### Manual Adjustments / Correction
If a wallet balance is somehow skewed:
1. **Never** run `UPDATE user_credit_wallet SET purchased_credits_balance = ...` directly without a corresponding ledger entry.
2. Determine the discrepancy amount.
3. Perform a manual top-up via the Admin Console with reason "Reconciliation correction for skew".
4. If a subtraction is required (e.g. accidental over-grant), top-up with a negative ledger entry is not allowed via the UI. If necessary, database administrators can insert a compensating debit entry in the ledger and update the wallet within an advisory lock.

---

## 4. Disaster Recovery / Double-Spend Incident

If a user bypasses concurrency locks (e.g., due to database lock contention failure) and downloads a report multiple times without being debited:

1. Review the logs for `concurrency_error` or lock timeout alerts.
2. Verify the user's ledger for `DOWNLOAD_DEBIT` entries for that `property_id`.
3. If a duplicate download was not debited, no action is needed as the resource is now unlocked. If a double-debit occurred, reimburse the user by executing a manual admin top-up of `1` credit.
