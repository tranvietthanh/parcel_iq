## ADDED Requirements

### Requirement: User can request a property report on demand
The system SHALL allow any user (anonymous or authenticated) to request a property intelligence report via the existing `POST /api/properties/{property_id}/request-scrape` endpoint. If a non-FAILED report already exists for the property, the system SHALL return the existing report status without queuing a new job.

#### Scenario: User requests a report for a property with no existing report
- **WHEN** a user submits a report request for a `property_id` with no existing `property_reports` row
- **THEN** the system SHALL resolve `lga_id` via PostGIS if NULL on the property
- **THEN** the system SHALL insert a `property_reports` row with `status = QUEUING`
- **THEN** the system SHALL set `requested_by_user_id` to the user's ID if authenticated, or NULL if anonymous
- **THEN** the system SHALL dispatch a `scrape_property` Celery task
- **THEN** the API SHALL return `{ status: "queued", property_id, report_id, message }`

#### Scenario: Report already queued or in progress
- **WHEN** a user requests a report for a property that already has a `property_reports` row with `status IN (QUEUING, PROCESSING, READY)`
- **THEN** the system SHALL NOT create a new job
- **THEN** the API SHALL return the existing status

#### Scenario: Previously failed report is re-requested
- **WHEN** a user requests a report for a property whose latest `property_reports` row has `status = FAILED`
- **THEN** the system SHALL insert a new `property_reports` row with `status = QUEUING` and queue a new Celery task
- **THEN** the old FAILED row SHALL be retained for audit

### Requirement: Report status lifecycle follows a 4-state model
The system SHALL use exactly four values for `property_reports.status`: `QUEUING`, `PROCESSING`, `READY`, `FAILED`.

#### Scenario: Scraper worker picks up job
- **WHEN** the scraper worker begins processing a `property_reports` row
- **THEN** it SHALL update `status = PROCESSING`

#### Scenario: LLM parsing completes successfully
- **WHEN** the LLM worker successfully parses and validates the scraped data
- **THEN** it SHALL update `status = READY`
- **THEN** the report SHALL be immediately visible to all users without admin approval

#### Scenario: Any worker stage fails after max retries
- **WHEN** either the scraper or LLM worker exhausts retries
- **THEN** it SHALL update `status = FAILED` with an `error_message`

### Requirement: Frontend polls for status updates at 10-second intervals
The UI SHALL poll `GET /api/properties/{property_id}/detail` every 10 seconds when the displayed report status is `QUEUING` or `PROCESSING`, and stop polling when status transitions to `READY` or `FAILED`.

#### Scenario: Panel is open with QUEUING status
- **WHEN** a property panel is open and the report status is `QUEUING` or `PROCESSING`
- **THEN** the frontend SHALL issue a GET request to the detail endpoint every 10 seconds
- **THEN** the panel SHALL display a loading/in-progress indicator

#### Scenario: Status transitions to READY
- **WHEN** the detail endpoint returns `status = READY`
- **THEN** polling SHALL stop
- **THEN** the panel SHALL display the full report without requiring a page refresh

#### Scenario: Panel is closed or user navigates away
- **WHEN** the user closes the property panel or navigates away while polling is active
- **THEN** polling SHALL stop immediately (clear interval, no orphaned requests)

### Requirement: Anonymous users are shown a sign-up CTA after requesting a report
The UI SHALL display a prompt to register or log in when an anonymous user has successfully queued a report request.

#### Scenario: Anonymous user sees the QUEUING panel
- **WHEN** an anonymous user successfully requests a report
- **THEN** the property panel SHALL display the report-in-progress state
- **THEN** the panel SHALL show a CTA: "Sign up or log in to receive an email when this report is ready"
- **THEN** the CTA SHALL include Clerk sign-up and log-in action buttons

#### Scenario: Logged-in user sees the QUEUING panel
- **WHEN** a logged-in user successfully requests a report
- **THEN** the panel SHALL display the report-in-progress state
- **THEN** the panel SHALL show: "We'll email you at {email} when your report is ready"
- **THEN** NO sign-up CTA SHALL be shown
