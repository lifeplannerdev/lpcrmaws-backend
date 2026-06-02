## Context

The staff page currently lacks complete functionality and a robust, "wow" visual aesthetic. In a production-ready application, the staff section must act as the primary interface for managing users and their related assets, along with managing specific edge cases like phone numbers (company vs. personal) accurately. It also requires tight integration with the overarching permissions system. This design focuses on filling those functionality gaps, introducing an optimized and visually striking UI, and seamlessly connecting staff data with asset and permission management.

## Goals / Non-Goals

**Goals:**
- Create a complete, fully functional Staff Page and Staff Details page.
- Implement highly responsive, aesthetically premium components.
- Establish a phone number prioritization mechanism: Display company phone by default, fallback to personal phone.
- Build a dedicated "Assets" tab on the Staff Details page that shows assigned assets and an asset timeline.
- Automatically synchronize asset updates with the staff details (e.g., if an asset changes the company phone number, the staff detail should reflect this).
- Extend the permission management UI to cover any new capabilities within the staff module.

**Non-Goals:**
- Completely rewriting the backend user authentication system.
- Designing an entirely new asset management module (we are just integrating existing or planned asset functionality into the staff view).
- Mobile native application development (this is strictly for the web app UI).

## Decisions

**Decision 1: Phone Number Fallback Logic Implementation**
- We will implement this as a frontend getter or computed property (e.g., `primaryContactNumber = companyPhone || personalPhone`). This keeps the backend data models clean (storing both separately) while providing the requested "single glance" view in the UI.

**Decision 2: Asset Tab Architecture in Staff Details**
- The Staff Details page will use a tabbed interface. We will fetch the staff member's core details on initial load. When the user navigates to the "Assets" tab, we will lazily fetch the associated assets and timeline for that specific staff member to optimize initial page load performance.

**Decision 3: Synchronizing Asset Details to Staff Details**
- The backend will need to broadcast or return updated staff details whenever an asset is assigned/unassigned/modified that impacts staff attributes (like the company phone number).
- Alternatively, on the frontend, upon a successful asset mutation related to a staff member, we will trigger a re-fetch of the staff member's details to ensure the UI is synchronized.

**Decision 4: Visual and UI Strategy**
- We will use modern CSS features (Grid, Flexbox, custom variables for theming) to ensure a high-quality, premium visual feel. Animations will be used subtly for transitions between tabs (e.g., switching to the Assets tab).

## Risks / Trade-offs

- **Risk:** Overcomplicating the Staff Details page with too much asset data.
  - **Mitigation:** Use pagination or infinite scrolling within the Assets tab if a staff member has many assets. Ensure the timeline is compact and visually clear.
- **Risk:** Performance issues due to complex timeline rendering.
  - **Mitigation:** Only load the timeline when the Assets tab is active. Optimize the API endpoint returning timeline events.
- **Risk:** Data inconsistency if asset updates fail to reflect on the staff profile.
  - **Mitigation:** Ensure backend transactions are atomic where asset updates directly modify staff fields, and rely on robust frontend state management to trigger re-fetches when necessary.
