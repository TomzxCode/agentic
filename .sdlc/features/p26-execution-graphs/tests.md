---
title: "Execution graphs"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: Execution graphs

## Scope

The backend suite (`backend/tests/test_graphs.py`) covers the definition contract, the CRUD API, and the executor end to end with the real database and a `TestClient`.
The frontend suites (`frontend/src/__tests__/executionGraph.test.js`, `frontend/src/__tests__/graphsView.test.js`) cover the pure editor logic and the page's components against a stubbed API.
Out of scope: no automated test drives the `agentic graphs` CLI commands, and no test runs a real harness or a real CLI child process (both are stubbed).

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Normalization drops garbage | Nodes with unknown kind, non-object node, unknown field type, extra keys | Only known nodes and fields remain, ids and positions coerced, caps enforced |
| TC-2 | Validation reports every problem | Missing prompt, unknown placeholder, duplicate id, select without options, dangling and mistargeted edges | One English issue per problem |
| TC-3 | Cycle detection | Edges forming a loop, plus a sound chain for contrast | `topological_order` returns the chain order or None |
| TC-4 | Template rendering | `{{name}}`, `{{name[1]}}`, `{{name.join(", ")}}`, unknown name, out-of-range index | Rendered text plus error list; unknown placeholders left in place |
| TC-5 | Editor connect rules (frontend) | Self connection, unknown ports, form sources with fields, duplicates | `canConnect`/`connect` refuse or dedupe |
| TC-6 | Editor issues mirror the server (frontend) | Missing prompts, unconnected placeholders, cycles, dropdown without options | Same issue texts as the server's validator |
| TC-7 | Auto layout and canvas geometry | Unplaced and placed nodes, node rows, edge endpoints | Placed nodes keep positions, new ones layer by longest path |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-8 | Graph CRUD over the API | Fresh tables | Create (201, next_run_at set), empty shell stored, broken definition stored but refused at run (400), validate endpoint reports issues, blank name and bad cron 400, disable clears next_run_at, rename keeps the rest, delete 204 |
| TC-9 | Two-node chain renders downstream | Enqueue stubbed, fast poll | First run linked to the "[Graph] chain" task, settling it enqueues the second with the answer rendered in, execution succeeds with outputs recorded, detail and history endpoints report the nodes |
| TC-10 | Form pauses and an answer resumes | Chain run -> form -> run | Pending form appears with fields and defaults, the answer flows into the next prompt, answers stored in state |
| TC-11 | Cancelling a form fails it | Pending form | Cancel fails the form, downstream skipped, execution failed |
| TC-12 | Unused form skipped, conflicts | Graph with a run and an unconnected form | Second run 409, form skipped on success, answering a settled execution 409, editing the stored definition to empty makes run 400, cancelling a settled execution 409 |
| TC-13 | Cancel aborts a running execution | Execution with an active run | 200 cancelled, node skipped, second cancel 409 |
| TC-14 | Cli node runs and feeds stdout downstream | `_run_cli` stubbed to exit 0 | Command argv carries the rendered arguments and `--api-url`, stdout becomes the node output and the downstream prompt, no run row for the cli node |
| TC-15 | Cli node failure skips downstream | `_run_cli` stubbed to exit 1 | Node failed with "exit 1" in the error, downstream skipped, detail shows the error |
| TC-16 | Scheduler fires a due graph once | Graph with next_run_at in the past | First tick starts one schedule-triggered execution and advances the occurrence, second tick starts nothing while it runs |
| TC-17 | Reconciliation fails stale executions | Execution row left running | Marked failed with "restart" in the error, ended_at stamped, second pass finds nothing |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-18 | An unbalanced quote in a rendered cli command | The node fails with the `shlex` error, no process is spawned |
| TC-19 | A run row disappears while the executor polls | The node fails with "The run row disappeared" |
| TC-20 | A waiting form whose request future is lost | `_wait_for_progress` raises instead of spinning, failing the execution loudly |
| TC-21 | A scheduled tick while an execution is already running | The occurrence advances, no second execution starts |

## Test Infrastructure

- `conftest.py` points `AGENTIC_DATA_DIR` at a temp dir and disables the warm harness pool; the file's `_clear()` deletes graph, run, event, and task rows between tests.
- `_harness()` ensures a cheap `Harness(name="test", command="true")` row exists for run nodes.
- `_no_enqueue(monkeypatch)` stubs `agentic.jobs.enqueue_run` so no real worker runs; tests settle runs by writing the `AgentRun` row and a message `AgentEvent` directly.
- `POLL_SECONDS` is monkeypatched to 0.01 so the 1 Hz executor loop tests in milliseconds; async assertions use `_await_for` so sleeping does not block the loop.
- Frontend tests mount against a stubbed `api` module; AG Grid is not involved on this page.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-8 |
| FR-2 | TC-1, TC-6 |
| FR-3 | TC-5, TC-2 |
| FR-4 | TC-1, TC-6 |
| FR-5 | TC-2, TC-3, TC-6 |
| FR-6 | TC-8 |
| FR-7 | TC-8 |
| FR-8 | TC-8 |
| FR-9 | TC-16, TC-21 |
| FR-10 | TC-9, TC-12 |
| FR-11 | TC-4, TC-9, TC-14 |
| FR-12 | TC-14, TC-15, TC-18 |
| FR-13 | TC-15, TC-11 |
| FR-14 | TC-10 |
| FR-15 | TC-11, TC-12 |
| FR-16 | TC-9, TC-11, TC-12 |
| FR-17 | TC-13, TC-12 |
| FR-18 | TC-9, TC-10, frontend graphsView suite |
| FR-19 | TC-17 |
| FR-20 | frontend graphsView suite (tabs, rows, run, delete confirm, expand execution, form submit and cancel) |
| FR-21 | none (manual; the CLI calls the same endpoints the backend suite covers) |
| NFR-1 | TC-10 (endpoint write survives the executor's next persist) |
| NFR-2 | TC-1 to TC-4, TC-7 |
| NFR-3 | TC-9 to TC-16 (fast poll) |
| NFR-4 | TC-14, TC-18 (timeout and render error paths; process kill is by code review) |
| NFR-5 | TC-6 |
| NFR-6 | none (layout is by code review) |
