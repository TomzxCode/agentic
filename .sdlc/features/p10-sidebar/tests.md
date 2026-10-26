---
title: "Sidebar"
status: done
session_link: "http://localhost:10000/?session=ses_ed267ac83ffevHmFcwZ0aUr1Hf"
---

# Test Plan: Sidebar

## Scope

Covers the sidebar's task entries (in-flight filter, single-line content, active marker, empty and loading states), the drawer and swipe gestures, the width resizer, the visibility toggle, and the bottom nav's per-device order and visibility preference.
The tag-filter clauses of FR-1 and FR-5 are not implemented (tag filtering was removed from the sidebar on 2026-10-16), so no test covers them.

## Unit Tests

| ID | Description | Expected Outcome |
|---|---|---|
| TC-1 | `sidebarNav.js` folds a stored choice onto the current item set | unknown and duplicate ids drop, hidden ids validate, items added since the choice append, corrupt JSON falls back to defaults |
| TC-2 | `sidebarNav.js` mutations persist | hide/show, move (swap, clamped move-to, no-op at the ends), and reset update `localStorage` (`agentic.sidebarNav`) and the customized flag |
| TC-3 | The nav grid sizes to the visible items | one to six columns from the visible count |

## Integration Tests (frontend, jsdom)

| ID | Description | Expected Outcome |
|---|---|---|
| TC-4 | The sidebar lists only in-flight tasks, each as one `.task-card` with status control, title, open next-steps count, and relative age | done and archived tasks are absent; no tags render |
| TC-5 | Empty states | no tasks shows "No tasks yet."; only finished tasks shows "All caught up." |
| TC-6 | The entry for the open task is marked active | `route.params.id` matches the entry's task |
| TC-7 | Drawer gestures | a rightward swipe (including edge, flick, and drift cases) opens the drawer, leftward closes, short swipes spring back, vertical drags and sideways-scrolling strips are ignored, modals suppress it |
| TC-8 | Width resizer | dragging changes the width within 260 to 560px, the choice persists in `localStorage`, double-click restores the default, the mobile layout has no resizer |
| TC-9 | Visibility toggle | the floated toggle hides the sidebar and remembers it (desktop preference), Cmd/Ctrl+B toggles, the mobile menu button reveals it, a drawer close never writes the desktop preference |
| TC-10 | Status change from an entry | picking a status updates the task and drops done/archived entries; a failed update reverts the row |

## Test Infrastructure

- Vitest with jsdom, `pool: 'vmThreads'`; `App.vue` mounts with stubbed child components and a stubbed `StatusSelect`.
- Swipe tests dispatch real PointerEvents (vue-test-utils cannot build pointer events with `clientX`).
- `localStorage` is cleared between tests; `location` is never stubbed.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 (in flight) | TC-4 |
| FR-1 (tag filter) | not implemented, not tested (sync drift, 2026-10-26) |
| FR-2 | TC-4 |
| FR-4 | TC-6 |
| FR-5 | TC-5 |
| FR-6 | TC-10 |
| NFR-2 | asserted inline in TC-4 (the status control carries an `aria-label`) |
