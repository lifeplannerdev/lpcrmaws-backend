## ADDED Requirements

### Requirement: Navigation Bar Overflow Handling
The desktop navigation bar MUST NOT wrap text for individual navigation items and MUST allow horizontal scrolling if the items exceed the available viewport width.

#### Scenario: Viewing navigation on a small screen
- **WHEN** the browser window is too narrow to display all navigation items
- **THEN** the text inside the navigation items SHALL NOT wrap to a second line
- **AND** the user SHALL be able to scroll horizontally to view hidden items.
