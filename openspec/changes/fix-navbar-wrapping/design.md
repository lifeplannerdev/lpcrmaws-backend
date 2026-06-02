## Context

The navigation bar on the desktop view contains many items. When the window width is too small to accommodate all the items in a single row without squeezing, the text inside the navigation buttons (like "Attendance Docs" and "Staff Reports") wraps to a second line. This breaks the UI vertical alignment and makes the navigation bar look unpolished.

## Goals / Non-Goals

**Goals:**
- Prevent text wrapping inside the navigation items.
- Ensure the navigation bar handles overflow gracefully (e.g., by enabling horizontal scrolling).

**Non-Goals:**
- Redesigning the entire navigation structure (like moving items into a "More" dropdown).
- Modifying the mobile navigation layout.

## Decisions

- **Add `whitespace-nowrap`:** This utility class will be added to the text span or the button itself to prevent the text from wrapping onto a second line.
- **Add `overflow-x-auto` and hide the scrollbar:** To handle the increased horizontal width of the items, the parent container holding the navigation items will be allowed to scroll horizontally. We will hide the scrollbar using a custom utility or `hide-scrollbar` class to keep the UI clean.

## Risks / Trade-offs

- **Trade-off:** Hiding the scrollbar might make it less obvious that the area is scrollable.
  - **Mitigation:** The items will likely cut off halfway at the edge, providing a visual cue that there is more content to scroll to.
