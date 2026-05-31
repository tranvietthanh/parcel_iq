## Why

ParcelIQ currently gates full report downloads through a subscription-tier model (FREE/PRO/UNLIMITED + daily quota) backed by Clerk Billing JWT claims. Product direction has shifted to a credit economy:

- Every full report download costs exactly 1 credit
- Daily free credits reset each Australia/Sydney day and do not roll over
- Anonymous users may request report generation but must sign in to download
- Reports are globally available once READY (no per-user unlock approval workflow)
- Admin operators need first-class user tooling to inspect balances and top up credits
- Clerk Billing subscription model is fully decommissioned; credit purchase is handled by a separate change

This change replaces subscription-based entitlement with a ledger-backed credit system, decommissions Clerk Billing gating, adds anonymous-request claiming for conversion, and introduces a user-friendly admin user detail/top-up experience.

## What Changes

- **BREAKING** Decommission Clerk Billing subscription-tier entitlement (JWT `pla` claim extraction, `subscription_tier` on `UserRow`, `require_active_subscription` dependency)
- **BREAKING** Decommission `daily_downloads` table and `GET /api/payments/status/{property_id}` endpoint
- Add credit wallet + immutable credit ledger model
- Add daily grant mechanism (configurable `X` credits/day, no rollover)
- Charge `1` credit for **every** successful full report download, including duplicate downloads of the same property/report
- Credit is debited only after successful PDF retrieval — no refund mechanism required
- Add duplicate-download precheck/warning flow in public UI
- Add anonymous request identity (`anon_requester_id`) and post-login claim flow (7-day claim window)
- Add **My Properties** page for public users with requested history and saved list
- Add admin **Users** list page and **User Detail** page with manual top-up action and credit activity view
- Defer payment-processor credit purchase integration to a separate OpenSpec change

## Capabilities

### New Capabilities

- `credit-based-downloads`: Ledger-backed credits for entitlement, debit, and top-up
- `my-properties-history`: Requested-properties history (including claimed anonymous requests)
- `admin-user-credit-management`: Admin users list/detail and manual credit top-up UX

### Modified Capabilities

- `on-demand-report-request` (existing): extend to persist anonymous requester key for later claim

## Impact

**Public API**
- Replace subscription/quota checks in full PDF download flow with credit checks
- Replace `require_active_subscription` dependency with `require_credits_available`
- Add duplicate precheck endpoint
- Add anonymous claim endpoint
- Add my-properties endpoint(s)
- Add `GET /api/credits/me` wallet summary endpoint
- Decommission `GET /api/payments/status/{property_id}` endpoint
- Remove `payments.py` router, `quota.py` module, and Clerk Billing JWT plan extraction

**Admin Backend + Admin Web**
- Add users list/detail endpoints + top-up mutation endpoint
- Add admin pages for user browsing and top-up operations
- Migrate admin analytics queries from `daily_downloads` to `credit_ledger`

**Database**
- Add credit wallet and credit ledger tables
- Add anonymous requester identity columns/relations for request claiming
- Decommission `daily_downloads` table
- Decommission subscription-specific columns on `users` table (`subscription_tier`, `stripe_customer_id`, `stripe_subscription_id`, `subscription_status`, `current_period_end`)

**Frontend (public-web)**
- Show duplicate-download warning modal
- Show credit balance and usage cues
- Add My Properties page with Requested and Saved tabs
- Remove Clerk `<PricingTable />` component and subscription-related UI/copy

## Rollout Strategy

1. Introduce credit tables and services behind feature flag
2. Dual-write usage telemetry where needed
3. Switch read path for entitlement to credits
4. Decommission old subscription entitlement paths (Clerk Billing, `daily_downloads`, `payments.py`)
5. Remove obsolete subscription schema and UI dependencies
