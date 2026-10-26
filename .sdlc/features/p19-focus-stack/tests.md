---
title: "Focus stack and launcher"
status: done
revision: 1
---

# Test Plan: Focus stack and launcher

## Scope

The backend tests cover the stack API through `TestClient`: materialization, push positions, pop and remove semantics, reorder and promote, derived session stats, history, parking (snooze and waiting), and task deletion cleanup.
The CLI tests cover the `agentic stack` commands against a fake API client.
The frontend tests cover the Stack page component with a mocked API module and the pure helpers in `stack.js`.
Out of scope: the launcher package has no automated tests, because a tray icon and a global hotkey need a desktop session; it is verified by hand following `launcher/README.md` and `docs/views/stack.md`.

## Unit tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | `targetIndexAt` picks the drop index from row midpoints | Midpoint list and pointer Y | Index 0..n-1, clamped to the last row, 0 on an empty list (`stack.test.js`) |
| TC-2 | `moveItem` moves an item without mutating the input | Array, from, to | A new array; the input untouched (`stack.test.js`) |
| TC-3 | `formatTimestamp` renders progressive timestamps | ISO value and now | Minutes in the hour, HH:MM in the day, DD HH:MM in the month, MM-DD in the year, full date otherwise, an em dash for missing or unparseable values (`stack.test.js`) |
| TC-4 | CLI `stack` commands render and validate | `StackFake` client | List, current, history, push, promote, reorder, edit, and remove print; `pop` on an empty stack prints "(none)"; a push without a title or task id exits 1 and writes to stderr (`test_commands_stack.py`) |

## Integration tests

Backend (`test_stack.py`, FastAPI `TestClient` over SQLite):

| ID | Test | What it covers |
|---|---|---|
| TC-10 | `test_push_positions_and_current` | Push positions top/next/last, the current flag, positions, first session, `execution_count` |
| TC-11 | `test_empty_stack_push_next_becomes_current` | A "next" push on an empty stack becomes current |
| TC-12 | `test_pop_marks_done_and_promotes_next` | Pop marks done, soft-deletes with reason popped, promotes the next, history shows it, repeated pops return an empty list |
| TC-13 | `test_reorder_and_promote_track_current_and_sessions` | Reorder keeps positions, promote re-makes an entry current, `execution_count` increments per focus stint |
| TC-14 | `test_remove_soft_deletes_without_status_change` | Remove keeps the task open, history keeps the entry, an unknown entry is 404 |
| TC-15 | `test_push_existing_task_is_already_on_the_stack` | Materialization of an existing task, duplicate push 409, unknown task 404 |
| TC-16 | `test_inflight_tasks_join_the_stack_automatically` | Open, in-progress, and blocked join; done and archived do not; exactly one current; a status change drops on the next read |
| TC-17 | `test_new_inflight_task_joins_at_the_bottom` | New tasks append without disturbing the order |
| TC-18 | `test_removed_task_stays_off_the_stack_until_pushed` | A removed task is not re-added; pushing it again returns it (201) |
| TC-19 | `test_update_entry_edits_the_task` | Title and description patch through the entry; a blank title is ignored |
| TC-20 | `test_current_endpoint` | Null on an empty stack, the head otherwise |
| TC-21 | `test_deleting_task_removes_its_stack_entries` | Task deletion removes its entries and sessions |
| TC-22 | `test_push_requires_a_title` | A blank title without a task_id is 400 |

Backend parking interplay (`test_waiting_snooze.py`):

| ID | Test | What it covers |
|---|---|---|
| TC-30 | `test_waiting_parks_the_task_until_the_follow_up` | Waiting parks off the stack, excluded from history, returns when the follow-up passes |
| TC-31 | `test_clearing_the_wait_reopens_and_clears_the_follow_up` | Clearing the wait reopens and returns the task to the stack |
| TC-32 | `test_an_explicit_status_wins_over_the_waiting_rule` | An explicit status override keeps the task unparked |
| TC-33 | `test_waiting_without_a_follow_up_stays_parked_until_pushed` | A wait with no date parks indefinitely; a push clears the wait, the follow-up, and reopens |
| TC-34 | `test_snooze_parks_the_task_without_changing_its_status` | A future snooze parks with status open; a past snooze returns the task; clearing keeps it |
| TC-35 | `test_deleting_the_waiting_person_clears_the_wait` | Deleting the waited-on person clears the wait |
| TC-36 | `test_naive_snooze_and_follow_up_are_treated_as_utc` | Naive datetimes are stored and compared as UTC (NFR-4) |

Frontend (`stack.test.js`, Vitest + jsdom, mocked `../api`):

| ID | Test | What it covers |
|---|---|---|
| TC-40 | lists the stack with the current task first | Rows, current class, title, `x2` count, duration, status picker per row |
| TC-41 | shows the priority of each task | Priority icons in the priority cell |
| TC-42 | changes a task priority from the stack | Priority picker calls `tasks.update` with the new priority |
| TC-43 | shows a deadline badge only when the task has one | "Due in 2d" badge only for a deadline |
| TC-44 | changes a task status from the stack | Status picker calls `tasks.update` with the new status |
| TC-45 | adds to the top on Enter and after the current on Shift+Enter | Push with position top, then next (FR-16) |
| TC-46 | filters the list as you type | Filter narrows the rows |
| TC-47 | promotes and removes a row from its actions | Promote and remove calls with the entry id |
| TC-48 | selects with the arrow keys and removes with Delete | Selection movement and Delete removal |
| TC-49 | shows the description editor for the selected task and saves on blur | Description patch on blur |
| TC-50 | toggles the history panel | History loads on open and renders entries |
| TC-51 | selects a row on click without navigating, and opens it via the link | Click selects; the open cell links to the task page |
| TC-52 | edits the title inline | Inline input takes focus and patches the title on Enter |
| TC-53 | reorders the clicked row with the arrow keys | ArrowLeft reorders the selected row (FR-17) |
| TC-54 | opens the description directly under the selected row | The editor row sits under its row |
| TC-55 | counts the current task duration up every second | The live duration ticks; a non-current duration is fixed (FR-17) |
| TC-56 | reorders rows by dragging with the mouse | Pointer drag past a midpoint reorders (FR-17) |
| TC-57 | drags from the handle on touch but not from the row body | Touch drag only from the handle (NFR-5) |
| TC-58 | ignores a drag while filtering | Dragging disabled while a filter is set (FR-17) |

## End-to-end tests

None automated.
The launcher is exercised by hand: run `uv run agentic-stack` against a running API and check the tray title, badge, Open Stack, Mark Done, and the hotkey (`docs/how-to/use-the-focus-stack.md`, "Verification").

## Edge cases and failure scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-70 | Pop on an empty stack | Returns an empty list, repeatedly (TC-12) |
| TC-71 | "next" push on an empty stack | Becomes the current task (TC-11) |
| TC-72 | Push with a blank title and no task_id | 400 (TC-22, TC-4) |
| TC-73 | Push of a task already on the stack | 409 (TC-15) |
| TC-74 | Push or remove of an unknown task or entry | 404 (TC-15, TC-14) |
| TC-75 | Blank title patch through an entry | Title kept as-is (TC-19) |
| TC-76 | Parked task read back | Off the stack and absent from history (TC-30) |
| TC-77 | Snooze or follow-up date passing | The task returns on the next read with its sessions intact (TC-30, TC-34) |
| TC-78 | Touch drag from the row body | No reorder, so the list can scroll (TC-57) |
| TC-79 | Drag while a filter is set | No reorder (TC-58) |
| TC-80 | Drop index past the last midpoint | Clamped to the last row; empty list yields 0 (TC-1) |

## Test infrastructure

- Backend: a shared SQLite engine; the autouse fixtures `_clean_stack` and `_clean_tasks` delete tasks, sessions, entries, timeline events, and related children in foreign-key-safe order before and after every test, so each test sees an empty stack.
- `backend/tests/conftest.py` points `AGENTIC_DATA_DIR` at a fresh temp directory per process.
- CLI: the `fake_client` fixture installs `StackFake` (`cli/tests/fakes/stack.py`); `text_format` output and `capsys` capture stderr.
- Frontend: Vitest under jsdom; `vi.mock('../api')` replaces every stack endpoint; `RouterLink` is stubbed through mount options; pointer events are dispatched as plain Events because jsdom has no `PointerEvent`; fake timers drive the duration tick.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-15, TC-16, TC-17 |
| FR-2 | TC-10, TC-20 |
| FR-3 | TC-10, TC-11, TC-18, TC-45 |
| FR-4 | TC-15, TC-22, TC-4, TC-72, TC-73 |
| FR-5 | TC-12, TC-70 |
| FR-6 | TC-14, TC-47 |
| FR-7 | TC-13, TC-48, TC-53, TC-56 |
| FR-8 | TC-10, TC-13, TC-40, TC-55 |
| FR-9 | TC-12, TC-14, TC-30, TC-50 |
| FR-10 | TC-30, TC-31, TC-34, TC-76, TC-77 |
| FR-11 | TC-33 |
| FR-12 | TC-19, TC-49, TC-52 |
| FR-13 | TC-16, TC-21 |
| FR-14 | TC-10 through TC-22 |
| FR-15 | TC-4 |
| FR-16 | TC-45, TC-46, TC-49, TC-52 |
| FR-17 | TC-48, TC-53, TC-55, TC-56, TC-57, TC-58, TC-43, TC-44 |
| FR-18 | None (manual, launcher untested) |
| FR-19 | None (manual, launcher untested) |
| NFR-1 | TC-13 (derived counts), TC-55 (live duration from data) |
| NFR-2 | None directly (structural, batched reads verified by code review) |
| NFR-3 | TC-14, TC-30 |
| NFR-4 | TC-36 |
| NFR-5 | TC-57 (partial; the modifier-key shortcut path is untested) |
| NFR-6 | None (manual, launcher untested) |
