## 1. Database + Migrations

- [x] 1.1 Create migration for `user_credit_wallet`
- [x] 1.2 Create migration for `credit_ledger` with mandatory `balance_after`, idempotency, and audit indexes
- [x] 1.3 Extend request-tracking schema for `anon_requester_id` claim linkage
- [x] 1.4 Add constraints for valid credit deltas (positive for grants/topup, negative for debit)
- [x] 1.5 Backfill `user_credit_wallet` rows for all existing users
- [x] 1.6 Add rollback-safe downgrade path for all new objects

## 2. Public API Credit Core

- [x] 2.1 Implement wallet reconciliation service (AU day reset, no rollover)
- [x] 2.2 Implement post-download debit service (daily first, then purchased; atomic with balance check)
- [x] 2.3 Add `require_credits_available` dependency to replace `require_active_subscription`
- [x] 2.4 Add `GET /api/credits/me`
- [x] 2.5 Add `GET /api/properties/{property_id}/full/precheck` duplicate-warning endpoint
- [x] 2.6 Refactor full PDF download endpoint to use post-download atomic debit model

## 3. Subscription Infrastructure Decommission

- [x] 3.1 Remove `extract_plan_from_jwt` and Clerk Billing JWT `pla` claim extraction
- [x] 3.2 Remove `subscription_tier` from `UserRow` schema and all references
- [x] 3.3 Remove `require_active_subscription` dependency
- [x] 3.4 Remove `payments.py` router (`GET /api/payments/status/{property_id}`)
- [x] 3.5 Remove `quota.py` module entirely
- [x] 3.6 Create migration to drop `daily_downloads` table
- [x] 3.7 Create migration to drop subscription columns from `users` table
- [x] 3.8 Migrate admin analytics queries from `daily_downloads` to `credit_ledger`
- [x] 3.9 Update user deletion cascade for `user_credit_wallet` + `credit_ledger`

## 4. Anonymous Request Claim + My Properties

- [x] 4.1 Issue and persist `anon_requester_id` for anonymous request-scrape calls
- [x] 4.2 Set cookie with `Secure; SameSite=Strict; HttpOnly; Path=/api` attributes
- [x] 4.3 Add claim endpoint to bind anonymous requests to authenticated user (7-day window)
- [x] 4.4 Add requested-history query endpoint for current user (paginated)
- [x] 4.5 Build public-web `My Properties` page with Requested and Saved tabs
- [x] 4.6 Trigger claim flow after sign-in and refresh requested history

## 5. Admin User Management + Top-Up

- [x] 5.1 Add admin-backend users list endpoint with credit summary fields
- [x] 5.2 Add admin-backend user detail endpoint with wallet + recent ledger entries
- [x] 5.3 Add admin-backend top-up mutation endpoint with reason field and positive-integer validation
- [x] 5.4 Add admin-web Server Action wrappers for user endpoints
- [x] 5.5 Add admin-web Users list page with search and pagination
- [x] 5.6 Add admin-web User detail page with top-up form and activity table
- [x] 5.7 Add success/error toasts and validation UX for top-up actions

## 6. Frontend Download UX

- [x] 6.1 Add duplicate-download warning modal prior to debit/download
- [x] 6.2 Display current spendable credits in property detail actions
- [x] 6.3 Ensure repeated download attempts always communicate 1-credit charge
- [x] 6.4 Remove Clerk `<PricingTable />` component and subscription UI/copy
- [x] 6.5 Handle 403 on credit-exhausted race with clear user messaging

## 7. Tests

- [x] 7.1 Unit tests for debit ordering (daily before purchased)
- [x] 7.2 Unit tests for no-rollover daily reset behavior
- [x] 7.3 Integration tests for duplicate download charge behavior
- [x] 7.4 Integration tests for post-download debit atomicity
- [x] 7.5 Integration tests for anonymous claim workflow (including 7-day window expiry)
- [x] 7.6 Integration tests for admin top-up mutation permissions and auditing
- [x] 7.7 E2E tests for My Properties requested-history visibility
- [x] 7.8 Tests for subscription decommission (no regressions in download flow)

## 8. Documentation

- [x] 8.1 Update architecture docs for credit-based entitlement model
- [x] 8.2 Update API docs with new credit and my-properties endpoints
- [x] 8.3 Add admin operations runbook for manual top-up and reconciliation
- [x] 8.4 Update product copy to remove subscription language
- [x] 8.5 Document cross-device anonymous claim as known non-goal

## 9. Follow-up Change Coordination

- [x] 9.1 Create and approve separate OpenSpec change for payment processor credit purchases
- [x] 9.2 Link this change and the payment change in both proposals/designs for rollout dependency clarity
