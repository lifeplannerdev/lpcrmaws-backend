## 1. Update Form Component

- [x] 1.1 Update `PersonalInfoSection.jsx` to render `Company Phone` (mapping to `officePhone`) and `Personal Phone` (mapping to `personalPhone`) fields.

## 2. Update Page States

- [x] 2.1 Update `AddStaffPage.jsx` `formData` to initialize and handle `officePhone` and `personalPhone`.
- [x] 2.2 Update `EditStaffPage.jsx` `formData` to fetch, initialize, and handle `officePhone` and `personalPhone`.

## 3. Update Form Submission Logic

- [x] 3.1 Update `AddStaffForm.jsx` (which is inside `AddStaffPage.jsx`) to construct the payload mapping `formData.officePhone` to `office_phone` and `formData.personalPhone` to `personal_phone`.
- [x] 3.2 Update `EditStaffForm.jsx` to construct the payload with the same mappings.
