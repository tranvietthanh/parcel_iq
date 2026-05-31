## ADDED Requirements

### Requirement: Users SHALL be able to purchase credits through checkout
The system SHALL provide a checkout flow that allows authenticated users to buy additional credits.

#### Scenario: Valid checkout request
- **WHEN** an authenticated user requests checkout with `credits >= 5`
- **THEN** the system SHALL create a pending purchase order
- **THEN** the system SHALL return a checkout URL for payment completion

#### Scenario: Invalid checkout quantity
- **WHEN** user requests checkout with `credits < 5`
- **THEN** the system SHALL reject the request with validation error

### Requirement: Credits SHALL be granted only after verified payment success
The system SHALL grant purchased credits only after processing a verified payment success webhook.

#### Scenario: Successful verified payment webhook
- **WHEN** payment provider sends a verified success event for a pending order
- **THEN** the system SHALL acquire the per-user advisory lock (`pg_advisory_xact_lock(hashtext('credit:' || user_id::text))`)
- **THEN** order SHALL transition to `PAID`
- **THEN** system SHALL write `PURCHASE_CREDIT` ledger entry with `related_order_id` exactly once
- **THEN** system SHALL increment purchased credit balance

#### Scenario: Checkout created but payment not completed
- **WHEN** no success webhook is received
- **THEN** order SHALL remain `PENDING`
- **THEN** no credits SHALL be granted

#### Scenario: Payment failure event received
- **WHEN** payment provider sends a verified failure event
- **THEN** order SHALL transition to `FAILED`
- **THEN** no credits SHALL be granted

### Requirement: Webhook processing SHALL be idempotent
Webhook replay or duplicate delivery SHALL NOT grant credits multiple times.

#### Scenario: Duplicate success webhook event arrives
- **WHEN** an already-processed success event is received again
- **THEN** system SHALL detect duplicate/replay
- **THEN** no additional ledger grant SHALL be written
- **THEN** response SHALL remain successful for provider retry compatibility

### Requirement: Purchased credits are non-refundable
The system SHALL NOT claw back credits on payment disputes or chargebacks.

#### Scenario: Payment dispute or chargeback received
- **WHEN** payment provider notifies of a dispute or chargeback
- **THEN** order record SHALL be updated to `FAILED` for audit traceability
- **THEN** no compensating ledger entry SHALL be written
- **THEN** user's credit balance SHALL remain unchanged

### Requirement: Purchased credits spend after daily credits
Purchased credits SHALL be consumed after the user's daily free credits are exhausted.

#### Scenario: User has both daily and purchased credits
- **WHEN** a user with daily credits remaining downloads a report
- **THEN** 1 daily credit SHALL be consumed first
- **THEN** purchased credits SHALL remain unchanged until daily allocation is exhausted
