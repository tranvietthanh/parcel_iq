## Why

Credit-based download entitlement is being delivered first via daily auto-grants and admin top-ups. To support self-service scale, users also need to buy additional credits through a payment processor.

This integration is intentionally split into a dedicated change so core report flow can be tested end-to-end without payment dependencies.

## What Changes

- Add public checkout endpoint for buying credit packs
- Enforce purchase pricing rules: `1 AUD/credit`, minimum order `5`
- Add payment webhook processing to grant credits only after verified payment success
- Add idempotent processing for webhook retries/replays
- Add purchase order state tracking and reconciliation tooling
- Add public UI for buy-credits flow and success/failure messaging

## Capabilities

### New Capabilities

- `credit-purchase-payments`: Payment-processor-backed purchase of credits

### Modified Capabilities

- `credit-based-downloads` (from separate change): consume purchased credits granted by payment events

## Impact

**Public API**
- Add checkout session creation endpoint
- Add payment webhook endpoint
- Add purchase history endpoint(s) if needed by UI

**Database**
- Add purchase order table and idempotency metadata
- Add ledger event type usage for purchase grants

**Frontend (public-web)**
- Add buy-credits UI entry points and checkout redirect flow
- Add purchase status UI feedback

## Dependencies

- Depends on `credit-based-downloads` change for wallet and ledger infrastructure

## Rollout Strategy

1. Deploy purchase schema and webhook endpoint behind feature flag
2. Validate webhook idempotency in staging with replay tests
3. Enable buy-credits button for a test cohort
4. Roll out broadly once reconciliation checks pass
