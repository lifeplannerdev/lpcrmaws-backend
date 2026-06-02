## Why

The desktop navigation bar has several items, and items with longer text (such as "Attendance Docs" and "Staff Reports") are currently wrapping their text onto multiple lines. This breaks the visual alignment and creates an unpolished UI.

## What Changes

- Add `whitespace-nowrap` to the navigation button items to prevent text from wrapping.
- Make the main navigation container horizontally scrollable (`overflow-x-auto`) while hiding the scrollbar so that if there are too many items to fit on the screen, users can scroll horizontally rather than the layout breaking.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `staff-page-ui-overhaul`: Modifying UI behavior to prevent layout breaks in the navbar.

## Impact

- `lpcrm-frontend/src/Components/layouts/DesktopNavbar.jsx`
- Main application navigation layout
