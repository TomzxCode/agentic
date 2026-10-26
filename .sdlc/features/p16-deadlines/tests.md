---
title: "Task deadlines"
status: done
revision: 1
---

# Test Plan: Task deadlines

## Scope

Covers the deadline lifecycle on the API (set, change, clear, upcoming listing), the UTC normalization of a naive value, the SPA's deadline controls and upcoming-deadlines section, and the CLI flags and `task deadlines` command.
Out of scope: a real clock (tests pass fixed instants) and phone-width rendering (checked by hand).

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | `deadlineInfo` derives the label and tone by calendar day | deadlines relative to now (overdue, today, tomorrow, later) | `Overdue`/danger, `Due today`/warn, `Due tomorrow`/warn, `Due in <n>d`; null without a parseable deadline |
| TC-2 | `formatDeadline` renders in the reader's zone | an ISO instant | `YYYY-MM-DD HH:MM` local text |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-3 | The deadline lifecycle and the upcoming view | create, update, and clear through the API | the task returns the set, changed, and cleared deadline; `GET /api/tasks/deadlines` lists in-flight tasks within the window, soonest first, overdue included, done and archived excluded |
| TC-4 | A naive deadline is treated as UTC | a create payload with no timezone | the stored value is that instant in UTC |
| TC-5 | A zero window keeps only overdue deadlines | `within_days=0` with overdue and future deadlines | only the overdue task is returned |
| TC-6 | Changing a deadline is recorded on the timeline | a PATCH that sets the deadline | an `updated` event with the before and after values |

## End-to-End Tests

| ID | Description | Steps | Expected Outcome |
|---|---|---|---|
| TC-7 | The tasks page's upcoming-deadlines section | mount `TasksView` with near, far, done, and deadline-less tasks | the section shows the near in-flight deadlines soonest first; the window control widens it; the badge shows on rows via `TaskCard` |
| TC-8 | Set and clear from the task page | mount `TaskView`, use `DeadlinePicker` | the PATCH carries the new value; clearing sends an explicit null |
| TC-9 | The CLI deadlines command and flags | `task deadlines --within-days`, `task create --deadline`, `task update --clear-deadline` against a fake client | the request bodies and the rendered `due <iso>` lines |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-10 | The deadline is not a parseable date | the API rejects it with a validation error (422) |
| TC-11 | A snooze-or-deadline badge in the past | no badge, no effect (covered with the store helpers) |

## Test Infrastructure

- `backend/tests/conftest.py` provides the TestClient with a temp data directory.
- Frontend tests mount the views with a mocked `api` and fixed `now` arguments for the store helpers.

## Test Files

| File | Covers |
|---|---|
| `backend/tests/test_deadlines.py` | TC-3, TC-4, TC-5 |
| `backend/tests/test_api.py` | timeline recording shared with other field updates (TC-6) |
| `frontend/src/__tests__/store.test.js` | TC-1, TC-2 |
| `frontend/src/__tests__/tasksView.test.js` | TC-7 |
| `frontend/src/__tests__/components_small.test.js` | TC-8 (DeadlinePicker) |
| `frontend/src/__tests__/cards.test.js` | the TaskCard deadline badge |
| `cli/tests/test_commands_tasks.py` | TC-9 |

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-3, TC-8 |
| FR-2 | TC-3, TC-5 |
| FR-3 | TC-8 |
| FR-4 | TC-7 |
| FR-5 | TC-9 |
| FR-6 | TC-6 |
| FR-7 | TC-4 |
| NFR-1 | TC-3 (the column is added by `db._ensure_columns`, covered in `test_db.py`) |
| NFR-2 | Not automated (manual phone-width check) |
| NFR-3 | TC-3 and TC-7 (the same window rule on both sides) |
