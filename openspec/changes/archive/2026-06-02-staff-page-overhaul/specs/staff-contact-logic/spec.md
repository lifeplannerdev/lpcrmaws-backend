## ADDED Requirements

### Requirement: Priority Display of Company Phone
The system SHALL display the company phone number by default when rendering a staff member's contact information in a single-glance context.

#### Scenario: Staff member has both company and personal phone
- **WHEN** a staff member has both a company phone and a personal phone number
- **THEN** the UI SHALL display the company phone number in primary list views and high-level detail summaries.

### Requirement: Fallback to Personal Phone
The system SHALL fall back to displaying the personal phone number if the company phone number is not available.

#### Scenario: Staff member only has a personal phone
- **WHEN** a staff member does not have a company phone number but has a personal phone number
- **THEN** the UI SHALL display the personal phone number in primary list views and high-level detail summaries.
