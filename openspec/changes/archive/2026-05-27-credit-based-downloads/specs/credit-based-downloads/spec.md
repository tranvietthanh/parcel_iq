## ADDED Requirements

### Requirement: Full report downloads SHALL use credit-based entitlement
The system SHALL authorize `GET /api/properties/{property_id}/full/pdf` based on spendable credits, not subscription tier.

#### Scenario: Authenticated user with spendable credits downloads full report
- **WHEN** an authenticated user requests a full PDF and has at least 1 spendable credit
- **THEN** the system SHALL retrieve/generate the PDF
- **THEN** the system SHALL debit exactly 1 credit only after successful PDF retrieval
- **THEN** the system SHALL stream the PDF to the client

#### Scenario: Authenticated user with zero spendable credits attempts download
- **WHEN** an authenticated user requests a full PDF and has 0 spendable credits
- **THEN** the system SHALL deny the request with a business error response
- **THEN** the response SHALL include actionable guidance to obtain additional credits

#### Scenario: Anonymous user requests full report download
- **WHEN** an unauthenticated user requests full PDF download
- **THEN** the system SHALL deny download and require sign-in

#### Scenario: Credits exhausted by parallel session during download
- **WHEN** a user passes the initial credit check but another session drains their credits before the atomic debit
- **THEN** the system SHALL deny the download with a 403 response at debit time
- **THEN** no credit SHALL be charged

### Requirement: Every successful download SHALL cost exactly 1 credit
A successful full report download SHALL always consume 1 credit, including repeated downloads of the same report/property by the same user.

#### Scenario: User re-downloads same report
- **WHEN** a user downloads a report they have previously downloaded
- **THEN** the system SHALL still debit 1 credit on success

### Requirement: Duplicate downloads SHALL show a warning before debit
The client SHALL be able to detect duplicate prior downloads and warn the user before they confirm a new charged download.

#### Scenario: Duplicate download precheck indicates prior download
- **WHEN** the client calls duplicate precheck and the user has prior download history for the target property/report
- **THEN** the API SHALL return a duplicate indicator and prior download timestamp as a best-effort advisory hint
- **THEN** the UI SHALL warn that continuing will consume 1 credit

### Requirement: Credit debit order SHALL prioritize daily credits
Debit logic SHALL consume daily credits before purchased credits. All credits are whole integers.

#### Scenario: User has both daily and purchased credits
- **WHEN** debit is performed
- **THEN** daily credits SHALL be consumed first
- **THEN** purchased credits SHALL only be used if daily credits are exhausted

### Requirement: Daily credits SHALL reset each AU day with no rollover
Daily grant credits SHALL reset by Australia/Sydney calendar day and SHALL NOT carry unused values into the next day.

#### Scenario: New AU day begins
- **WHEN** user wallet is accessed after day boundary
- **THEN** daily usage SHALL reset to zero for the new day
- **THEN** daily available credits SHALL equal configured daily grant value `X`
- **THEN** any prior unused daily credits SHALL be discarded

#### Scenario: Day boundary crosses during download session
- **WHEN** a user begins precheck before midnight AEST and completes download after midnight AEST
- **THEN** the wallet SHALL reconcile to the new day within the debit transaction
- **THEN** the debit SHALL consume from the new day's daily grant

### Requirement: Credit operations SHALL be auditable via immutable ledger
All credit-affecting operations SHALL be recorded as append-only ledger entries with mandatory `balance_after`.

#### Scenario: Any credit mutation occurs
- **WHEN** a daily grant, debit, or admin top-up is applied
- **THEN** an immutable ledger record SHALL be written with actor/context metadata and computed `balance_after`

## REMOVED Requirements

### Requirement: Subscription-tier entitlement for downloads
Subscription-tier checks (FREE/PRO/UNLIMITED) and Clerk Billing JWT `pla` claim extraction SHALL be decommissioned.

### Requirement: Daily download quota tracking
The `daily_downloads` table and associated quota logic SHALL be decommissioned. Download tracking is replaced by `DOWNLOAD_DEBIT` ledger entries.

### Requirement: Payment status endpoint
`GET /api/payments/status/{property_id}` SHALL be decommissioned. Credit status is served by `GET /api/credits/me` and the precheck endpoint.
