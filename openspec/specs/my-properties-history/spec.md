## ADDED Requirements

### Requirement: Anonymous report requests SHALL be claimable after sign-in
The system SHALL support linking previously anonymous report requests to a newly authenticated user identity within a 7-day claim window.

#### Scenario: Anonymous user requests report and later signs in
- **WHEN** the same browser session authenticates and calls claim endpoint
- **THEN** unclaimed requests associated with that anonymous requester key SHALL be linked to current user
- **THEN** linked requests SHALL appear in user's Requested history
- **THEN** only requests made within the last 7 days SHALL be claimable

#### Scenario: Anonymous requester has no pending claimable records
- **WHEN** claim endpoint is called and no matching anonymous requests exist
- **THEN** endpoint SHALL return success with zero claimed count

#### Scenario: Anonymous request is older than 7-day claim window
- **WHEN** claim endpoint is called and matching anonymous requests are older than 7 days
- **THEN** those requests SHALL NOT be linked to the authenticated user
- **THEN** endpoint SHALL return success with zero claimed count for expired requests

#### Scenario: Anonymous request claim on different device
- **WHEN** a user browses anonymously on one device and authenticates on a different device
- **THEN** the system SHALL NOT automatically claim requests from the other device
- **THEN** this is a documented non-goal (cookie-bound identity)

### Requirement: Public app SHALL provide My Properties page
The public-web application SHALL provide a `My Properties` view for authenticated users.

#### Scenario: Authenticated user opens My Properties
- **WHEN** user navigates to My Properties
- **THEN** page SHALL render at least two tabs: `Requested` and `Saved`

### Requirement: Requested tab SHALL include report lifecycle visibility
Requested properties history SHALL show request and readiness states to support follow-up downloads. Results SHALL be paginated.

#### Scenario: Requested list contains mixed statuses
- **WHEN** user views Requested tab
- **THEN** each row SHALL include property identity, request timestamp, report status, and ready timestamp when available
- **THEN** READY rows SHALL expose download action

#### Scenario: Requested list exceeds single page
- **WHEN** user has more requested properties than a single page
- **THEN** results SHALL be paginated with navigation controls

### Requirement: Saved tab SHALL preserve existing saved-properties behavior
Existing saved properties functionality SHALL remain available in My Properties.

#### Scenario: User has saved properties
- **WHEN** user opens Saved tab
- **THEN** saved properties SHALL be listed using current saved-properties semantics

### Requirement: My Properties SHALL be authentication-gated
Anonymous users SHALL NOT access My Properties data.

#### Scenario: Unauthenticated access attempt
- **WHEN** an unauthenticated client requests My Properties routes/endpoints
- **THEN** system SHALL return authentication-required response and UI SHALL prompt sign-in
