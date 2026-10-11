---
title: "Gantt timeline view"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: Gantt timeline view

## Scope

Covers the `/api/gantt` endpoint: which tasks appear, the span fields, marker ordering and types, and the include-done filter.
Out of scope: the `GanttView.vue` rendering.

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-1 | Active tasks carry ordered markers | a task created then updated | row has status, created_at, updated_at; markers ordered oldest first; includes created and updated |
| TC-2 | Done is hidden unless asked | a task with status done | absent from the default list; present with include_done=true |

## Test Infrastructure

- `fastapi.testclient.TestClient` over the app.
- Tasks are created and deleted within each test.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-1 |
| FR-2 | TC-2 |
