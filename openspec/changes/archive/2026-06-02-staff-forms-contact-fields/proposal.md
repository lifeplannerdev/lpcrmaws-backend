## Why

While the `staff-page-overhaul` change introduced new contact logic (falling back to personal phone when company phone is absent) and updated the Staff List and Staff Details pages to display `office_phone` and `personal_phone`, the Add Staff and Edit Staff forms were not updated. Currently, these forms only present a single `Phone Number` field, meaning users cannot input or modify the separate company and personal phone numbers. This change bridges that gap.

## What Changes

- Add a `Company Phone` (mapping to `officePhone`/`office_phone`) field to the `PersonalInfoSection` form component.
- Rename the existing `Phone Number` field to `Personal Phone` (mapping to `personalPhone`/`personal_phone`) for clarity.
- Update `EditStaffPage.jsx` and `AddStaffPage.jsx` to fetch, initialize, and handle the state for the new phone fields.
- Update `EditStaffForm.jsx` and `AddStaffForm.jsx` to correctly map these fields into the payload sent to the backend.

## Capabilities

### New Capabilities
- `staff-forms-contact-fields`: Ensures the Staff Add/Edit forms properly support inputting and managing company and personal phone numbers.

### Modified Capabilities
- None.

## Impact

- `lpcrm-frontend/src/Components/staffs/newstaff/PersonalInfoSection.jsx`
- `lpcrm-frontend/src/Pages/EditStaffPage.jsx`
- `lpcrm-frontend/src/Components/staffs/editstaff/EditStaffForm.jsx`
- `lpcrm-frontend/src/Pages/AddStaffPage.jsx`
- `lpcrm-frontend/src/Components/staffs/newstaff/AddStaffForm.jsx`
