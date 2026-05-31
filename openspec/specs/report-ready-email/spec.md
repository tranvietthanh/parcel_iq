## ADDED Requirements

### Requirement: Logged-in report requesters receive an email when their report is ready
The system SHALL send a Resend email to the authenticated user who requested a property report when that report's status transitions to `READY`. Anonymous requesters SHALL NOT receive email notifications.

#### Scenario: Logged-in user requests a report and it completes
- **WHEN** an authenticated user requests a report and the LLM worker transitions the report to `READY`
- **THEN** the LLM parser worker SHALL look up the requester's email from the `users` table via `requested_by_user_id`
- **THEN** it SHALL send a Resend email containing the property address and a link to view the report

#### Scenario: Anonymous user requests a report and it completes
- **WHEN** `property_reports.requested_by_user_id IS NULL` and the report transitions to `READY`
- **THEN** the system SHALL NOT send any email

#### Scenario: Resend email delivery fails
- **WHEN** the Resend API call fails (timeout, 5xx, quota exceeded)
- **THEN** the failure SHALL be logged as a warning
- **THEN** the report status SHALL remain `READY` — the notification failure SHALL NOT affect the report

#### Scenario: User's email is not available
- **WHEN** `requested_by_user_id` is set but the corresponding `users.email` is NULL or the user row is missing
- **THEN** the system SHALL log a warning and skip the email send without error
