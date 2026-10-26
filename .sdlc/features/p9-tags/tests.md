---
title: "Task tags"
status: done
session_link: "http://localhost:10000/?session=ses_ed2936849ffePjqvp9kEDOH0mX"
---

# Test Plan: Task tags

## Scope

Covers tag normalization on write, tag filtering on the task list, tag enumeration with counts, the timeline event on a tag change, bulk tag editing, and the CLI and web UI surfaces.
Performance (NFR-4) is not asserted by a test; the phone-width check (NFR-3) is verified by hand.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | `crud.normalize_tags` trims, drops empties, de-duplicates, preserves order | `["bug", " bug ", "", "ui", "bug"]` | `["bug", "ui"]` |
| TC-2 | CLI client sends repeatable `tag` params and reads `/api/tags` | `list_tasks(tags=["bug", "ui"])`, `list_tags()` | query `tag=bug&tag=ui`; `GET /api/tags` parsed to `{name, count}` rows |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-3 | Tags are normalized on create, filtered (single and multi, AND), and enumerated with counts | tasks tagged `["bug","ui"]`, `["bug"]`, `["infra"]` | stored tags normalized; `?tag=` filters to tasks carrying every tag; `/api/tags` reports counts sorted by count desc then name |
| TC-4 | A tag change is recorded on the timeline | a task with tags `["bug"]` | `PATCH` to `["bug","urgent"]` writes an `updated` event whose `changes.tags` carries `from` and `to` |
| TC-5 | Bulk update edits status and tags across tasks | two tagged tasks | `POST /api/tasks/bulk` with `add_tags`/`remove_tags` updates each task and reports updated/missing |

## Unit Tests (frontend)

| ID | Description | Expected Outcome |
|---|---|---|
| TC-6 | `TagInput` adds on Enter/comma, removes the last on Backspace, ignores empty and duplicate entries | the model updates chip by chip; suggestions come from the store's tags |
| TC-7 | Task rows show tag chips that filter on click | clicking a chip sets `store.tagFilter`; the active chip is highlighted |
| TC-8 | The tag filter row narrows the loaded list client-side | only tasks carrying the selected tag stay visible; clearing restores the list |
| TC-9 | The command palette offers one entry per tag and a clear action while a filter is active | picking an entry sets the filter; "Clear tag filter" resets it |

## Test Infrastructure

- `fastapi.testclient.TestClient` over the app; tasks are created and deleted within each test (`backend/tests/test_api.py`).
- CLI client tests use a stub HTTP client recording the request (`cli/tests/test_client.py`).
- Frontend tests run with Vitest and jsdom (`make test-frontend`), stubbing fetch and mounting with `@vue/test-utils`.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-1, TC-3 |
| FR-2 | TC-2, TC-3 |
| FR-3 | TC-3 |
| FR-4 | TC-6 |
| FR-5 | TC-7, TC-8, TC-9 |
| FR-6 | TC-6 |
| FR-7 | TC-2 |
| FR-8 | TC-4 |
| NFR-1 | TC-3 (no separate table; tags live on the task row) |
| NFR-2 | TC-2, TC-3 (same predicate behind API and CLI) |
| NFR-4 | (not asserted; in-process filtering at local scale) |
