---
title: "Events feed"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: Events feed

## Scope

The cross-task feed query, filters, and cursor in `backend/src/agentic/routers/events.py`, and the `EventsView.vue` grouping, filters, and paging.
Out of scope: the in-process SSE bus in `backend/src/agentic/events.py` (covered by `backend/tests/test_events.py`, a separate streaming concern) and the task timeline endpoint that writes the events.

## Unit Tests

No pure unit module: the feed is a single query, so its behavior is covered at the endpoint level, and the Slack renderers it calls are exercised indirectly.

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 (frontend) | The page groups events by local day and links rows to tasks | today's and yesterday's events | Today and Yesterday groups, two timeline panels, task links, provenance text, exact timestamps |
| TC-2 (frontend) | Actor and client filters reload from the server | filter changes | each request carries actor and client, with limit 50 |
| TC-3 (frontend) | Load older pages with the last row as the cursor | a full 50-row first page | the second request carries before, beforeId, and limit; a short page removes the button |
| TC-4 (frontend) | An empty feed says so | no rows | "No activity yet." |

## Integration Tests

Covered by `backend/tests/test_events_feed.py` (TestClient against the app and its database).

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-5 | The stream carries both tasks' activity with task context and provenance, newest first | two tasks, one patched via CLI/agent headers | rows from both tasks, task_title, task_status, client cli, actor agent, descending created_at |
| TC-6 | Filters by task, type, actor, client, and search all narrow | one task patched by the CLI as an agent | only matching rows per filter; a non-matching search returns [] |
| TC-7 | The before cursor pages without repeating rows | four updates, page size 2 | disjoint ids across pages, second page continues where the first stopped |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-8 | Events written in the same instant | the id tie-breaker keeps pages disjoint and complete (TC-7's cursor, TC-3 on the page) |
| TC-9 | A failed page load with rows already shown | the view keeps the loaded rows and raises a toast (frontend behavior; first-load failure shows "Could not load events.") |
| TC-10 | Nothing to send to Slack | the endpoint returns 404 "No events to send" (specified; no automated test, see gaps) |

## Test Infrastructure

- Backend: `TestClient(app)` with the shared temp data directory; tasks are created and deleted per test so the feed assertions are isolated.
- Frontend: Vitest with `api.events.list` mocked and `RouterLink` stubbed.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-5, TC-1 |
| FR-2 | TC-6, TC-2 |
| FR-3 | TC-7, TC-3 |
| FR-4 | TC-1, TC-2, TC-3, TC-4 |
| FR-5 | (no automated test; see gaps below) |
| FR-6 | (no automated test; see gaps below) |
| FR-7 | (no automated test; see gaps below) |
| FR-8 | (no automated test; the CLI command is a thin API client, no cli test) |
| NFR-1 | TC-5 (only timeline rows come back) |
| NFR-2 | TC-7, TC-3 |

## Gaps

The Slack delivery endpoints (`POST /api/events/{id}/slack` and `POST /api/events/slack`), the recipient fallback order, and the `agentic events send-slack` command have no automated tests in `backend/tests` or `cli/tests`.
`docs/views/events.md` documents them as manual usage.
A future test pass should add endpoint tests that stub `services.slack.slack_send_events` and assert the rendered recipient and 404 and 502 paths.
