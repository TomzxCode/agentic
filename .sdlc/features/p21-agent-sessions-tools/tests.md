---
title: "Agent sessions, session links, and managed tools"
status: done
---

# Test Plan: Agent sessions, session links, and managed tools

## Scope

The recorded-session API (CRUD, timeline, harness defaulting, deletion rules), the link builder (templates, placeholders, resume commands), the managed tool manager (transports, ports, lifecycle, restart), the Sessions panel and item tool links in the SPA, and the CLI session commands' client wiring.
Out of scope: the ghx and slackx binaries themselves (faked everywhere), the OpenChamber side of the links, and the worker's run-produced sessions (the agent-run feature).

## Unit Tests

Backend, file `backend/tests/test_links.py` and `backend/tests/test_links_more.py` (pure link building):

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | No links without a session id or configuration | no session id, or empty settings and harness | empty list |
| TC-2 | OpenChamber and terminal links are built | base, path template, terminal template | filled URLs with `{session}` `{cwd}` `{harness}` substituted |
| TC-3 | `_fill` and `_join` helpers | template plus values, base plus path | substituted template; base joined with a single slash |
| TC-4 | `run_read` attaches OpenChamber and resume links | run with session id, harness with resume command | `RunRead.links` carries the URL link and the `cd <cwd> &&` command |

Backend, file `backend/tests/test_managed_tools.py` (fake process objects):

| ID | Description | Input | Expected Outcome |
|---|---|---|---|
| TC-5 | Managed starts the serve process and supplies its endpoint | ghx managed via stored override | `ghx serve --host 127.0.0.1 --port 8080` spawned; endpoint `http://127.0.0.1:8080/rpc` with empty token |
| TC-6 | slackx managed uses its own port | slackx managed | port 8280 |
| TC-7 | cli and rpc transports start nothing | each transport | no process, no endpoint |
| TC-8 | A stored override wins over the environment | env rpc, stored managed | managed wins |
| TC-9 | Switching away from managed stops the process | managed then cli | process terminated |
| TC-10 | Restart replaces the running process | managed tool running | old process stopped, new started |
| TC-11 | Restart starts a tool that never came up | no process yet | one started |
| TC-12 | Restart leaves a tool this server does not run | rpc tool | `None`, nothing touched |
| TC-13 | The all-tools flag manages both | `AGENTIC_MANAGED_TOOLS`, transport cli | both managed |
| TC-14 | An explicit rpc server is kept over the flag | `AGENTIC_MANAGED_TOOLS`, transport rpc | not managed |
| TC-15 | A missing binary leaves the endpoint without a process | spawn via `subprocess`, binary absent | start returns false, no crash |
| TC-16 | Tools this server does not run are never managed | unknown tool name | `manages` false |

## Integration Tests

Backend, file `backend/tests/test_sessions_api.py` (endpoints through the FastAPI test client):

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-17 | Session CRUD records timeline and task detail | a task | create, get, update, delete work; timeline entries and task detail follow |
| TC-18 | A session requires an id and a valid harness | blank id, unknown harness | 400 and 404 |
| TC-19 | The harness defaults to the task's and links are built | task with harness, no explicit harness | session's harness is the task's; links present |
| TC-20 | A session belongs to one task and survives harness deletion | second task, harness deleted | 404 from the other task's path; session kept with no harness |
| TC-21 | Deleting a task removes its sessions | task with sessions | sessions gone with the task |
| TC-22 | Links are empty without a configured target | no settings | `links: []` |

Frontend, `frontend/src/__tests__/sessions_panel.test.js` and `frontend/src/__tests__/toolLinks.test.js`:

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-23 | The panel renders each session with links and the resume command | sessions with links | labels, harness chip, link buttons, and copyable command shown |
| TC-24 | The panel prompts when nothing is recorded | no sessions | the `agentic session add` hint is shown |
| TC-25 | Removing asks and then removes | confirmed removal | the API is called and the panel refreshes |
| TC-26 | Declining the confirmation keeps the session | declined removal | the API is not called |
| TC-27 | A failed removal is reported | API rejects | a toast reports the error |
| TC-28 | GitHub item targets parse | issue and PR URLs | `{owner, repo, kind, number}`, casing kept; non-GitHub ignored |
| TC-29 | ghx item and repo URLs build | configured `ghx_url`, GitHub item or remote | hash route into ghx's UI; `null` without a URL |
| TC-30 | Slack targets parse | permalink, reply permalink, `channel:ts` external id | `{channel, stamp, threadTs}` with the thread root chosen; non-Slack ignored |
| TC-31 | slackx item URLs build | configured `slackx_url`, Slack item | archive route with the thread query; `null` without a URL |
| TC-32 | `itemToolLinks` picks the matching link | item source plus configured servers | only the link matching the item's source is returned |

CLI, `cli/tests/test_commands_runs.py` and `cli/tests/test_commands_renderers.py`:

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-33 | The session subcommands round-trip through the client fake | fake client with sessions | `session list`, `get`, `add`, `update`, `remove` print the outcome |
| TC-34 | Session renderers | a session dict | `_session_line` and `_session_text` show id, session id, label, harness, and cwd |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-35 | Blank session id on attach | 400 before anything is written |
| TC-36 | Unknown or foreign harness on attach or update | 404 |
| TC-37 | A session read through another task's path | 404, sessions are task-scoped |
| TC-38 | A managed tool whose binary is missing | start returns false, logged, API still starts |
| TC-39 | A wedged managed process | terminate, then kill after the 5 s grace period (not covered by a test; the fake process always exits on wait) |
| TC-40 | Restarting a tool this server does not run | 409 from the endpoint, `None` from the manager |
| TC-41 | No OpenChamber base, terminal template, or resume command | the corresponding links are absent, not empty strings |
| TC-42 | A stored blank transport override | the environment's value applies |

## Test Infrastructure

- `backend/tests/test_managed_tools.py` injects fake process objects through the manager's `spawn` parameter, so no test starts a ghx or slackx process.
- The settings store is driven through a temp `AGENTIC_DATA_DIR`; transport overrides are written as normal settings rows.
- `test_sessions_api.py` uses the FastAPI test client with seeded task and harness rows from the shared helpers.
- The frontend tests mount the actual `SessionsPanel` and `SessionLinks` components with a mocked `api` module, and `toolLinks.test.js` exercises the pure helpers directly.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-17, TC-18, TC-35 |
| FR-2 | TC-18, TC-19, TC-36 |
| FR-3 | TC-17, TC-25, TC-26, TC-27 |
| FR-4 | TC-20, TC-21 |
| FR-5 | TC-2, TC-4, TC-19 |
| FR-6 | TC-2, TC-3 |
| FR-7 | TC-1, TC-22, TC-41 |
| FR-8 | TC-33, TC-34 |
| FR-9 | TC-23, TC-24, TC-25 |
| FR-10 | TC-5, TC-6, TC-7 |
| FR-11 | TC-8, TC-42 |
| FR-12 | TC-13, TC-14 |
| FR-13 | TC-9, TC-10, TC-12, TC-40 |
| FR-14 | Settings view wiring (`settingsView.test.js` mocks the settings API; field visibility is component logic) |
| FR-15 | TC-28, TC-29, TC-30, TC-31, TC-32 |
| NFR-1 | TC-5, TC-6 (host pinned in the command) |
| NFR-2 | TC-15, TC-38 |
| NFR-3 | TC-10, TC-11 |
| NFR-4 | TC-20, TC-21 |
| NFR-5 | TC-24, TC-26 |
