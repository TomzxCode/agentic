---
title: "Task management and timeline"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: Task management and timeline

## Scope

Covers task CRUD, change recording, relationship labels, and the many-to-many task-to-repository link.
Out of scope: the SPA's rendering of the task list and detail.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Task lifecycle end to end | create, update, read, delete | 201 / 200 / 200 / 204 |
| TC-2 | Relationship labels in the timeline | set group_id then harness_id | event data carries `from_label`/`to_label` names |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-3 | Timeline records before/after | a task with an update | an "updated" event with per-field from/to |
| TC-4 | Many-to-many task repositories | a task and two repos | both repository_ids returned, change recorded |

## End-to-End Tests

| ID | Description | Steps | Expected Outcome |
|---|---|---|---|
| TC-5 | Task change stream | subscribe to `/stream`, then PATCH | an SSE message with `kind: task` |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-6 | Create without a title or URL | 400 |
| TC-7 | Delete a task with runs and events | no FK violation; children removed in order |

## Test Infrastructure

- `fastapi.testclient.TestClient` over the app.
- `backend/tests/conftest.py` points `AGENTIC_DATA_DIR` at a temp directory before app import.
- `tmp_path` fixtures create real git repositories where a task needs a repository.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-1, TC-6 |
| FR-2 | TC-1 |
| FR-3 | TC-1 |
| FR-4 | TC-3, TC-2 |
| FR-5 | TC-4 |
| FR-6 | TC-1, TC-7 |
| FR-7 | TC-3 |
| FR-8 | TC-5 |
| NFR-1 | TC-7 |
