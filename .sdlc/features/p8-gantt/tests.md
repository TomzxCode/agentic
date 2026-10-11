---
title: "Gantt timeline view"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: Gantt timeline view

## Scope

Covers the `/api/gantt` endpoint: which tasks appear, the span fields, marker ordering and types, and the include-done filter.
The rendering is covered by frontend unit tests over the shared chart and its helpers.

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-1 | Active tasks carry ordered markers | a task created then updated | row has status, created_at, updated_at; markers ordered oldest first; includes created and updated |
| TC-2 | Done is hidden unless asked | a task with status done | absent from the default list; present with include_done=true |

## Unit Tests (frontend)

| ID | Description | Expected Outcome |
|---|---|---|
| TC-3 | `gantt.js` fits the domain and resolves a range | the fit includes the data (and now when asked); a reversed range is invalid and falls back to the fit; an unset bound uses the fitted bound |
| TC-4 | `gantt.js` maps marker kinds and lays out ticks | known types map, unknown types fall back; ticks align at the edges; a compact chart uses two ticks |
| TC-5 | `GanttChart` renders the chart | axis, bar, one marker per event, and a legend; compact drops the label column; linking wraps rows; markers are buttons only when clickable and emit `marker-click` |
| TC-6 | `TimelinePanel` draws the task's gantt | the chart renders when there are events, with one marker per event, and is absent when there are none |
| TC-7 | A marker click jumps to its event | clicking a marker scrolls to the matching event row and highlights it |

## Test Infrastructure

- `fastapi.testclient.TestClient` over the app.
- Tasks are created and deleted within each test.
- `vitest` + `@vue/test-utils` for the frontend unit tests, no server.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-1 |
| FR-2 | TC-2 |
| FR-3 | TC-5 |
| FR-5 | TC-5 |
| FR-6 | TC-3 |
| FR-8 | TC-6 |
| FR-9 | TC-7 |
