## Why

The current staff page section needs an overhaul to reach production readiness. We need to implement all remaining screens, features, and rules, ensuring a highly optimized, complete, and visually impressive ("wow" factor) user experience. This overhaul will also address specific requirements regarding contact number display priority, deeper integration with asset management, and corresponding permission updates, making the staff module robust and fully connected with other system components.

## What Changes

- Complete implementation of all screens and features in the staff section.
- Optimization of code, usability, and visual aesthetics (premium, dynamic design).
- **Phone Number Logic**: Update contact information to strictly handle company phone number (optional) and personal number. Introduce a "single glance" display rule: prioritize showing the company number, falling back to the personal number if the company number is missing.
- **Asset Integration (Staff Details)**: Add a dedicated "Assets" tab within each staff member's detail view to display all assigned assets.
- **Asset Integration (Updates)**: Ensure that assets correctly update the company number details and any asset-related fields in the staff page.
- **Asset Timeline**: Display a timeline of assets specifically for each staff member.
- **Permissions**: Add any new permissions and screens introduced by this overhaul to the permission management page.

## Capabilities

### New Capabilities
- `staff-page-ui-overhaul`: Complete overhaul of the staff page UI, focusing on usability, performance, and visual excellence (production readiness).
- `staff-contact-logic`: Specific rules for handling and displaying company vs. personal phone numbers.
- `staff-asset-management`: Integration of asset data within the staff profile, including a dedicated assets tab, asset timeline, and synchronization of asset-related fields.

### Modified Capabilities
- `permission-management`: Updates to handle new permissions and screens introduced by the staff page overhaul.

## Impact

- Frontend components related to the staff page, staff details, and permission management.
- Backend API endpoints handling staff retrieval, updates, and asset associations.
- Database models (if new fields for company vs personal phone or asset tracking per staff are needed).
- Routing and navigation within the staff section.
