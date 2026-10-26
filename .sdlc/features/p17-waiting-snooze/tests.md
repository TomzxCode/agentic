---
title: "Waiting on a person and snoozing a task"
status: done
revision: 1
---

# Test Plan: Waiting on a person and snoozing a task

## Scope

Covers the waiting-on and snooze fields on the task API, the parking rule in `stack.sync_stack` (park on set, return when the date passes, popped stays gone), the push-clears-deferral rule, person deletion and merge, the SPA controls and badges, and the CLI flags.
Out of scope: a real clock (tests pass fixed instants) and the stack's non-deferral behavior (covered by `test_stack.py`).

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | `snoozeInfo`, `waitingInfo`, and `parkedInfo` mirror the server's parking rule | tasks with a future snooze, a waiting person with and without a follow-up, expired dates | the same parked reasons as `stack.parked_reason`; a past snooze shows no badge |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-2 | Waiting parks the task until the follow-up | a task set to wait on a person with a future date, then the date moved to the past | off the stack while parked; back on it once the date passes |
| TC-3 | Clearing the wait reopens and clears the follow-up | a blocked, waiting task | status open, no person, no follow-up date |
| TC-4 | An explicit status wins over the waiting rule | one request setting a waiting person and `status: done` | the task is done |
| TC-5 | Waiting with no follow-up stays parked until pushed | a waiting task pushed onto the stack | the push clears the snooze and the wait and reopens the task |
| TC-6 | Snoozing parks without changing the status | an open task snoozed until tomorrow | still open, off the stack; back when the date passes |
| TC-7 | Deleting the waiting person clears the wait | a task waiting on a deleted person | no waiting person, no follow-up date |
| TC-8 | Merging a person moves the wait | a task waiting on the merge source | it waits on the target person |
| TC-9 | Naive snooze and follow-up dates are UTC | deferral dates with no timezone | stored as that instant in UTC |
| TC-10 | Timeline recording | set, change, and clear each field | `updated` events with the before and after values, the person named |

## End-to-End Tests

| ID | Description | Steps | Expected Outcome |
|---|---|---|---|
| TC-11 | The task page's waiting and snooze controls | mount `TaskView` with `WaitingOnSelect` and the snooze `DeadlinePicker` | each edit PATCHes one field; the palette can jump to both |
| TC-12 | The row badges | mount `TaskCard` with waiting and snoozed tasks | "Snoozed until …" and "Waiting on <name>" badges with the check-back date; `StackList` names the person on a stack row |
| TC-13 | The CLI flags | `task create/update --waiting-on/--follow-up/--snooze/--clear-waiting/--clear-snooze` against a fake client | the request bodies carry the fields; `task list`/`task show` render `waiting on <name>` and `snoozed until <when>` |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-14 | A waiting person id that does not exist | 404 from the task writer |
| TC-15 | A popped or removed task whose dates lapse | it stays off the stack (only a parking is undone automatically) |
| TC-16 | The person row disappears but tasks keep the id | `waiting_on_name` reads null and the badges degrade gracefully |

## Test Infrastructure

- `backend/tests/conftest.py` provides the TestClient with a temp data directory; `test_waiting_snooze.py` clears tasks between cases so the stack materialization starts clean.
- Frontend tests mount the components with a mocked `api` and pass fixed `now` values to the store helpers.

## Test Files

| File | Covers |
|---|---|
| `backend/tests/test_waiting_snooze.py` | TC-2, TC-3, TC-4, TC-5, TC-6, TC-7, TC-9 |
| `backend/tests/test_people_api.py` / `test_people_links.py` | TC-7, TC-8 (delete and merge) |
| `backend/tests/test_stack.py` | the materialization and rejoin rules the parking rides on |
| `frontend/src/__tests__/store.test.js` | TC-1 |
| `frontend/src/__tests__/taskView.test.js`, `components_small.test.js` | TC-11 |
| `frontend/src/__tests__/cards.test.js` | TC-12 |
| `cli/tests/test_commands_tasks.py` | TC-13 |

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-2, TC-3, TC-11, TC-13 |
| FR-2 | TC-6 |
| FR-3 | TC-1, TC-2, TC-5, TC-6 |
| FR-4 | TC-2, TC-6 (sessions survive, per the stack tests) |
| FR-5 | TC-15 |
| FR-6 | TC-3, TC-4 |
| FR-7 | TC-5 |
| FR-8 | TC-11, TC-12 |
| FR-9 | TC-13 |
| FR-10 | TC-10 |
| FR-11 | TC-7, TC-8 |
| NFR-1 | TC-2 (columns added by `db._ensure_columns`, covered in `test_db.py`) |
| NFR-2 | Not automated (manual phone-width check) |
| NFR-3 | TC-1 (the same rule on both sides) |
| NFR-4 | TC-9 |
