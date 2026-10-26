---
title: "On-call view"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: On-call view

## Scope

The item identity and healing behavior of the on-call endpoints in `backend/src/agentic/routers/on_call.py`: resolve creating and updating Slack items, canonical external ids, legacy id and URL healing, and the scan's per-thread state.
Out of scope: the On-call page component (no frontend test exists), the slackx CLI itself, and Slack delivery (both are stubbed).

## Unit Tests

No pure unit module; the router's helpers are exercised through the endpoint tests below with stubbed subprocess and Slack calls.

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Resolving a thread creates one item with its canonical external id and watermark | channel id, thread ts, resolved_through_ts | 200, one item with external id `<channel>:<dotless ts>`, done true, done_message_ts set; a second resolve finds the same item |
| TC-2 | A named `#channel` is keyed by its resolved channel id | `#help-ml-infrastructure` with a stubbed channels lookup | the item's external id and permalink use the channel id |
| TC-3 | An item stored under the configured channel name is healed | legacy item with a `#name` external id and fragment URL | the same item is reused, external id and URL rewritten to canonical forms, done true |
| TC-4 | An item stored under the bare thread ts is healed | legacy item with external id equal to the dotted ts | the same item is reused and healed, no duplicate |

## Integration Tests

Covered by `backend/tests/test_on_call.py` (TestClient against the app, shared database, stubbed slackx and workspace URL).

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-5 | The scan heals an item stored under the configured channel name | legacy item plus a stubbed slackx response | 200, the legacy item healed to the canonical id and permalink |
| TC-6 | The scan finds a resolved thread by its canonical id and flags new activity | thread resolved at its root, a reply with a later ts in the stubbed slackx output | one thread, resolved true, has_new_activity true, still one item |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-7 | Re-resolving an already resolved thread | the same item is found and updated, not duplicated (TC-1) |
| TC-8 | A scan reply whose root is outside the fetched window | the reply is treated as its own root so it still appears (router grouping path, exercised by the stubbed fixtures) |
| TC-9 | slackx missing, failing, or returning invalid JSON | 502 (specified; no automated test, see gaps) |
| TC-10 | Rotation start in the future | the scan returns an empty inactive payload (specified; no automated test, see gaps) |

## Test Infrastructure

- Backend: `shell._cli_run` and `shell._run_cli` are monkeypatched to return canned slackx JSON, `slack_workspace_url` is pinned to a test workspace, and an autouse fixture prunes the Slack items the tests create from the shared database.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-5, TC-6 |
| FR-3 | TC-3, TC-4, TC-5, TC-6 |
| FR-5 | TC-1, TC-2, TC-3, TC-4 |
| FR-2 | (no automated test; see gaps) |
| FR-4 | (no automated test; see gaps) |
| FR-6 | (no frontend test; see gaps) |
| FR-7 | (no frontend test; see gaps) |
| NFR-1 | TC-1, TC-3, TC-4, TC-5 |

## Gaps

- The reply endpoint (400 and 502 paths, token precedence) and the rotation lookback computation have no automated tests.
- The scan's inactive payload, thread grouping of a reply without its root, and the 502 paths for a missing or failing slackx are untested.
- The On-call page has no frontend test: the persisted configuration, rotation states, draft reset, and task creation are unverified.
- No documentation exists under `docs/`; the docs phases are marked not started in `progress.md`.
