# staff-forms-contact-fields Specification

## Purpose
TBD - created by archiving change staff-forms-contact-fields. Update Purpose after archive.
## Requirements
### Requirement: Staff Forms Contact Fields Update
The Add and Edit Staff forms MUST allow users to input separate Company Phone and Personal Phone numbers.

#### Scenario: Submitting staff details
- **WHEN** a user fills out the Add or Edit Staff form
- **THEN** they see two distinct fields for "Company Phone" and "Personal Phone"
- **AND** both fields are successfully saved and sent in the API payload as `office_phone` and `personal_phone` respectively.

