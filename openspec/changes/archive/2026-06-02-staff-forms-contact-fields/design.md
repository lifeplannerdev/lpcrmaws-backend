## Context

The backend models and Staff list/details UI were recently updated to distinguish between Company Phone (`office_phone`) and Personal Phone (`personal_phone`). However, the frontend forms (`EditStaffPage` and `AddStaffPage`) were left with a generic "Phone Number" field that maps to `phone` only.

## Goals / Non-Goals

**Goals:**
- Update the Staff forms (Add/Edit) to accept and submit separate `officePhone` and `personalPhone` fields.

**Non-Goals:**
- Refactoring the entire forms structure or styling.
- Adding completely new logic to the backend (backend already accepts these fields).

## Decisions

- We will modify `PersonalInfoSection.jsx` to render two phone fields instead of one, providing clarity and matching the new backend logic.
- The `EditStaffPage.jsx` and `AddStaffPage.jsx` will include `officePhone` and `personalPhone` in their local `formData` state.

## Risks / Trade-offs

- **Risk**: API validation might fail if one of the phone numbers is sent empty but marked as required on the backend.
  - **Mitigation**: Make `companyPhone` the primary required field and leave `personalPhone` as optional, ensuring it aligns with backend validation rules.
