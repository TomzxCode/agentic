---
title: "Task dependencies and the dependency graph"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: Task dependencies and the dependency graph

## Scope

Covers the dependency endpoints (link, read, unlink), the acyclicity and duplicate rules, the timeline and deletion behaviour, the graph endpoint, and the frontend view and layout logic.
Out of scope: real browser interaction with Vue Flow; the graph drawing is verified through the layout function and the mounted view's calls to the API.

## Unit Tests

| ID | Description | File |
|---|---|---|
| TC-1 | `layoutGraph` places a chain in successive columns and a task past all its predecessors by longest path | frontend `graph.test.js` |
| TC-2 | Independent nodes stack in the same column; undrawn edges are dropped; the canvas is sized to fit | frontend `graph.test.js` |
| TC-3 | `edgePath` runs from the source's right edge to the target's left edge | frontend `graph.test.js` |
| TC-4 | `wrapTitle` keeps short titles on one line, wraps long ones, caps at three lines, and handles an empty title | frontend `graph.test.js` |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-5 | Link with relation after, read from both sides | two tasks | A lists B under after; B lists A under before |
| TC-6 | Link with relation before | two tasks | B lists A under before |
| TC-7 | Duplicate link | edge A -> B already stored | still exactly one edge, no error |
| TC-8 | Read a task's neighbours | edges A -> B -> C | B's read carries A before and C after as full tasks |
| TC-9 | Unlink from either side, then unlink again | edge A -> B | 204 and the edge gone; the second unlink answers 404 |
| TC-10 | Timeline entries on both tasks | linked tasks | dependency_added on each; dependency_removed on unlink paths |
| TC-11 | Deleting a task drops its links | edge A -> B | B survives with no dangling before link |
| TC-12 | Graph returns nodes and edges | edge A -> B | nodes carry both tasks and the edge names the pair |
| TC-13 | Graph hides done tasks and their edges | edge to a done task | done task and any edge naming it are absent without include_done |
| TC-14 | DependencyGraphView | monkeypatched API | a node per task and an edge per link, an empty state, and a reload that includes done when toggled |
| TC-15 | DependenciesSelect | monkeypatched API | before and after chips listed, unlink reloads, linking before posts relation "before", candidates exclude self and linked tasks |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-16 | A task linked to itself | 400, nothing stored |
| TC-17 | A link that closes a cycle (A -> B -> C, then C -> A) | 400 with a cycle message, and the existing edges unchanged |
| TC-18 | Unlink a pair with no edge | 404 |
| TC-19 | Link to an unknown related task | 404 |

## Test Infrastructure

- `TestClient` over the FastAPI app; tasks created through `POST /api/tasks` and cleaned up by deletion.
- Frontend Vitest suites stub `api.js` and mount `DependencyGraphView` and `DependenciesSelect`; `graph.test.js` exercises the pure layout helpers directly.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-5, TC-6 |
| FR-2 | TC-16, TC-17 |
| FR-3 | TC-7 |
| FR-4 | TC-8 |
| FR-5 | TC-9, TC-18 |
| FR-6 | TC-10 |
| FR-7 | TC-11 |
| FR-8 | TC-12, TC-13 |
| FR-9 | TC-15 |
| FR-10 | TC-1, TC-14, TC-15 |
| NFR-1 | TC-17 |
| NFR-2 | TC-1, TC-2, TC-3, TC-4 |
| NFR-4 | TC-13 |
