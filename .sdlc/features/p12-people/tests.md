---
title: "People: associate tasks and items with specific individuals"
status: done
session_link: "http://localhost:10000/?session=ses_ed1c7d2feffevews1ZEr34mSZC"
---

# Test Plan: People

## Scope

Covers the person directory CRUD, task and item links (idempotent), timeline events, deletion cascades, the merge, auto-population from GitHub and Slack metadata, and the task-requester links added after this feature was written.
Phone-width checks (NFR-3) and the merge confirmation copy at 375px (NFR-9) are verified by hand.

## Unit Tests

| ID | Description | Expected Outcome |
|---|---|---|
| TC-1 | Alias normalization and lookup | values trim, drop empties, and de-duplicate; `person_for_alias` finds a person by any carried alias |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-2 | Person CRUD over the API | none | create requires a name (400 otherwise), read returns aliases with task and item counts, update replaces fields, delete removes the person and their links (204, then 404) |
| TC-3 | Task links are idempotent and recorded | a task and a person | `POST /api/tasks/{id}/people` links once (a repeat is a no-op), writes `person_added`, unlink writes `person_removed`; `GET /api/tasks/{id}` carries `people` |
| TC-4 | Item links are idempotent | an item and a person | link then relink leaves one row; `ItemRead` carries `person_ids` |
| TC-5 | Deletion cascades | links in both directions | deleting a person detaches tasks and items; deleting a task or an item drops only its links |
| TC-6 | Merge moves aliases and links without duplicates | two people sharing an alias, a task, and an item | the target carries each alias and link exactly once, gains a `person_added` event where it newly links, the source is gone (404); self-merge is 400, unknown ids are 404 |
| TC-7 | Auto-population from a GitHub item | a `ghx` issue/PR payload with author, assignees, and commenters | one person per login, each with the login as an alias, all linked to the item |
| TC-8 | Auto-population from a Slack thread | a `slackx` thread payload with distinct participants | one person per user id, named from `slackx users list` with the message fallback |
| TC-9 | Auto-population is best effort | `ghx` or `slackx` missing or failing | the item still stores and no person is created (NFR-6) |
| TC-10 | Linking an item propagates its people to the task | an item already carrying auto-populated people | the task's people gain them, each with a `person_added` event |
| TC-11 | Task requesters | a task and a person | `POST /api/tasks/{id}/requesters` links a requester, `TaskDetail` carries `requesters`, unlink removes, and a `requester_added` event records it |

## Unit Tests (frontend)

| ID | Description | Expected Outcome |
|---|---|---|
| TC-12 | The people grid renders the directory | name, aliases, task and item counts, and created date as filterable columns; the row links to the person page |
| TC-13 | Person create and detail pages | a handle creates a person; the person page shows aliases, notes, relationships, and a confirmed merge into a picked target |
| TC-14 | The task's people picker | an existing person links, a new name creates and links, remove unlinks |
| TC-15 | Item people chips and linker | an item shows its people and links a person from the picker |

## Test Infrastructure

- `fastapi.testclient.TestClient` over the app; source payloads are stubbed at the `ghx`/`slackx` boundary, never the real CLIs (`backend/tests/test_people_*.py`, shared helpers in `_people_helpers.py`).
- CLI tests use a fake HTTP client asserting the `person` command surface (`cli/tests/`).
- Frontend tests run with Vitest and jsdom; grid tests stub `RouterLink` and wait on the grid's settle helper.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-2, TC-13 |
| FR-2 | TC-3, TC-14 |
| FR-3 | TC-4, TC-15 |
| FR-4 | TC-2, TC-12 |
| FR-5 | TC-2, CLI `person` commands |
| FR-6 | TC-3, TC-14 |
| FR-7 | TC-4, TC-15 |
| FR-8 | TC-12 |
| FR-9 | TC-3 |
| FR-10 | TC-5 |
| FR-11 | TC-7 |
| FR-12 | TC-8 |
| FR-13 | TC-10 |
| FR-14 | TC-6 |
| FR-15 | TC-1, TC-6 |
| FR-16 | TC-6 |
| FR-17 | TC-6 |
| FR-18 | TC-6, TC-13 |
| NFR-1 | TC-3, TC-4, TC-6 |
| NFR-4 | TC-3, TC-4 |
| NFR-6 | TC-9 |
| NFR-7 | TC-7, TC-8 |
| NFR-8 | TC-6 |
