## ADDED Requirements

### Requirement: Admin console SHALL provide a Users list page
The admin application SHALL expose a user-friendly list of platform users with credit-relevant summary fields.

#### Scenario: Admin opens Users page
- **WHEN** an authenticated admin navigates to Users
- **THEN** page SHALL show paginated list with user identity and credit summary
- **THEN** page SHALL support search/filter by common identifiers (email, clerk_user_id)

### Requirement: Admin console SHALL provide User detail page
The admin application SHALL expose a dedicated user detail view.

#### Scenario: Admin selects a user from list
- **WHEN** admin opens user detail
- **THEN** page SHALL display profile metadata, wallet summary, and recent credit ledger events

#### Scenario: Admin opens detail for non-existent user
- **WHEN** admin navigates to a user ID that does not exist
- **THEN** page SHALL display a 404 not-found state

### Requirement: Admin SHALL be able to top up credits from User detail page
The user detail page SHALL include a top-up action for manual support operations.

#### Scenario: Admin submits valid top-up request
- **WHEN** admin enters credit amount and reason and submits
- **THEN** system SHALL add credits to target user
- **THEN** system SHALL record immutable `ADMIN_TOPUP` ledger entry with actor metadata and reason
- **THEN** updated balance SHALL be visible immediately in UI

#### Scenario: Admin submits invalid top-up request
- **WHEN** top-up payload fails validation (e.g., non-positive amount, missing reason)
- **THEN** system SHALL reject mutation and return validation error
- **THEN** UI SHALL display actionable error feedback

#### Scenario: Admin attempts excessively large top-up
- **WHEN** top-up amount exceeds a reasonable upper bound
- **THEN** system SHALL reject with validation error to prevent accidental mass grants

### Requirement: Admin top-up actions SHALL be auditable
All admin credit adjustments SHALL be traceable.

#### Scenario: Audit review of admin adjustments
- **WHEN** support/compliance reviews credit history
- **THEN** each admin top-up SHALL include who performed it, when, amount, and reason
