---
id: "3"
title: "Web UI people surfaces"
status: draft
size: M
depends_on: [1]
completed_date: null
blocker: null
session_link: "http://localhost:10000/?session=ses_ed1c7d2feffevews1ZEr34mSZC"
---

# Task 3: Web UI people surfaces

## Description

Add the people surfaces to the SPA: a `PeoplePanel` on the task page, people chips and a linker on the Items page, a `PeopleView` page, and the navigation and palette entries.

## Acceptance Criteria

- [ ] FR-6: The task page lists its people, removes them, links an existing person, and creates a new one.
- [ ] FR-7: Each item shows its people and can link a person.
- [ ] FR-8: A People page lists each person with their tasks and items, with rename and delete.
- [ ] NFR-3: The people controls are usable at 375 px without horizontal scrolling.

## Notes

Mirror `ItemsPanel.vue` for the task panel and `ItemsView.vue` for the page.
Reuse `SearchSelect` and `EditableText`.
