## 1. Backend API & Permissions

- [x] 1.1 Add/Update endpoints for fetching a staff member's assets and related timeline events.
- [x] 1.2 Update the permissions seed or model to include new permissions for accessing the Staff Details Assets tab and contact logic modifications.
- [x] 1.3 Ensure the Staff API returns complete asset and contact information necessary for the frontend logic.
- [x] 1.4 (Optional) Add backend triggers/hooks to synchronize staff data when linked assets are updated.

## 2. Frontend Core Structure & Contact Logic

- [x] 2.1 Implement the `primaryContactNumber` logic (Company Phone fallback to Personal Phone).
- [x] 2.2 Update the Staff List view to display this primary contact number in a "single glance" context.
- [x] 2.3 Refactor the Staff Details page to utilize a modern, premium tabbed layout.

## 3. Frontend Assets & Timeline

- [x] 3.1 Create the "Assets" tab component inside the Staff Details page.
- [x] 3.2 Implement API integration to fetch and display the list of assigned assets for the staff member.
- [x] 3.3 Create the "Asset Timeline" sub-component (or separate tab) and integrate timeline API data.
- [x] 3.4 Ensure the UI gracefully handles loading states and empty states for assets.

## 4. Visual Overhaul & Polish

- [x] 4.1 Apply premium CSS styles (modern typography, subtle animations, improved spacing) to the Staff Page and Staff Details.
- [x] 4.2 Verify responsiveness across different screen sizes.
- [x] 4.3 Implement data synchronization on the frontend: When an asset is updated, trigger a re-fetch of the associated staff details to update contact numbers and other asset-related fields.

## 5. Permissions UI

- [x] 5.1 Update the permission management screen to expose and configure the new staff-related permissions.
- [x] 5.2 Validate that the new UI components (Assets tab, contact logic toggles) correctly respect the configured permissions.
