---
title: "Scheduled shell tasks"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: Scheduled shell tasks

## Scope

The backend suite (`backend/tests/test_schedules.py`) covers CRUD, validation, timezone handling, the preview endpoint, real command execution, the scheduler tick, and reconciliation.
The frontend suites (`frontend/src/__tests__/schedules.test.js`, `frontend/src/__tests__/cron.test.js`) cover the page's components and the browser-side cron preview against a stubbed API.
The CLI suites (`cli/tests/test_commands_schedules.py`, `test_commands_renderers.py`) cover the `agentic schedule` commands and their renderers.
Out of scope: the timeout kill path is documented behavior verified by code review, not by a test; no test covers a 20,000-character output.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Schedule validation | `"0 9 * * *"` with padding; empty, 4-field, 6-field, and symbolic strings | Trimmed expression accepted, each bad one raises ValueError |
| TC-2 | Next occurrence stays on the wall clock | `compute_next_run("0 9 * * *")` with the server zone patched to Europe/Paris across the 2026 spring-forward | The next run is 09:00 Paris time on both offsets |
| TC-3 | Upcoming runs are ordered and consistent | `upcoming_runs("0 9 * * *", count=5)` | Five sorted future runs at 09:00 local; a stored next run leads the preview while still ahead |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-4 | CRUD and run now over the API | Fresh tables | Create 201 with next_run_at and resolved timezone, bad schedule and blank fields 400, pause clears next_run_at and enable restores it, bad schedule patch 400, run now 201, run settles succeeded with exit 0, per-task and cross-task history and single-run reads, 404 on every unknown id, delete 204 empties the list |
| TC-5 | Timezone decides when a schedule fires | Task with `0 9 * * *` in Asia/Tokyo | next_run_at is 00:00 UTC; preview returns the same; unknown zone 400 on create and preview; changing the zone to Europe/Paris recomputes to 09:00 local |
| TC-6 | Preview endpoint | Valid and invalid expressions | Next runs with the zone used; a bad expression answers 400 |
| TC-7 | Failed command and missing cwd are recorded | Tasks running `exit 3` and `echo hi` with a nonexistent cwd | The first settles failed with exit code 3, the second failed with no exit code and a message naming the directory |
| TC-8 | Scheduler runs due tasks once | A due enabled task, a due disabled task, a future task | Exactly the enabled task started, its occurrence advanced into the future, a second tick starts nothing |
| TC-9 | Reconciliation fails stale runs | A run row left running | Marked failed with the "Interrupted" note in the output and ended_at stamped |

## Frontend Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-10 | Schedules page components (`schedules.test.js`, 16 tests) | Stubbed API | List rows with schedule and last status, next run in the task zone with paused marking, form hidden until New and Cancel closes it, silent refresh timer picks up scheduler-started runs, executions tab across tasks, empty state, create from the form, client-side validation before create, edit, per-form draft isolation, pause and delete, run now with reload after the poll, run history with output |
| TC-11 | Browser cron preview (`cron.test.js`, 7 tests) | Expressions and zones typed into the form | Next five runs computed in the browser with no preview request, recomputed when the expression or timezone changes, errors shown for bad input |
| TC-12 | CLI commands and renderers (`test_commands_schedules.py`, `test_commands_renderers.py`) | Fake API client | `schedule list/get/create/update/delete/run/runs` emit correct payloads and text; the line and text renderers show the cron, zone, next run, paused state, and run output |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-13 | A command that never started (spawn error) | Run settles failed with exit_code null and the failure message in the output |
| TC-14 | A due task that is already executing | The tick skips it; the running set prevents a second concurrent command |
| TC-15 | A task created or edited from the CLI without a timezone | The server's zone is used and reported on read |
| TC-16 | Command output longer than the cap | Only the last 20,000 characters are kept, prefixed with a truncation marker |

## Test Infrastructure

- `conftest.py` points `AGENTIC_DATA_DIR` at a fresh temp dir, so the suite runs against a disposable database.
- `_make_task(**fields)` seeds rows directly; `_wait_for_run` polls the newest run row until it leaves `running` (real subprocesses run `echo` and `exit`).
- Frontend tests mount components with a stubbed `api` module and Vitest fake timers for the refresh cycles.
- CLI tests use the shared `fake_client` fixture and assert both text and JSON emission.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-4 |
| FR-2 | TC-1, TC-4, TC-10 |
| FR-3 | TC-2, TC-5 |
| FR-4 | TC-4, TC-5 |
| FR-5 | TC-8 |
| FR-6 | TC-8 |
| FR-7 | TC-4, TC-7 |
| FR-8 | TC-7, TC-13 |
| FR-9 | TC-4 |
| FR-10 | TC-4 |
| FR-11 | TC-4 |
| FR-12 | TC-5, TC-6, TC-3 |
| FR-13 | TC-4 |
| FR-14 | TC-9 |
| FR-15 | TC-10, TC-11 |
| FR-16 | TC-12 |
| NFR-1 | TC-8 (tick cadence), TC-10 (background start) |
| NFR-2 | TC-4, TC-7 (real subprocesses settle while the API returns at once) |
| NFR-3 | TC-2 |
| NFR-4 | none directly (settings defaults verified by code review) |
| NFR-5 | TC-6, TC-11, TC-3 |
