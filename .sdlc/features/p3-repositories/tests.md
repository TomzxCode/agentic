---
title: "Repositories, groups, and directory picker"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: Repositories, groups, and directory picker

## Scope

Covers the directory picker (listing, hidden folders, navigation, root confinement, bulk add) and repository group lifecycle and its effect on the context prompt.
Out of scope: the SPA's picker component.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Group membership in the context prompt | a task in a group | prompt lists the group's repositories |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-2 | Group lifecycle and task link | a task and a group | group created, task linked, detaching on delete |
| TC-3 | List directories with git flags | a root with a git checkout | entries sorted, is_git correct |
| TC-4 | Include hidden folders | hidden dir present | appears when `hidden=true` |
| TC-5 | Navigate into and back out | nested dirs | parent/child traversal correct |
| TC-6 | Bulk add per-path errors | one git, one non-git path | added list and errors list populated |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-7 | Browse outside the root | 403 |
| TC-8 | Register a non-git path | 400 |

## Test Infrastructure

- `browse_root` fixture builds a temp tree with a git checkout and hidden directory.
- `TestClient` and `tmp_path` for repository and group endpoints.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-8 |
| FR-2 | TC-6 |
| FR-3 | TC-6 |
| FR-4 | TC-2 |
| FR-5 | TC-2 |
| FR-6 | TC-3, TC-4, TC-5, TC-7 |
| NFR-1 | TC-7 |
| NFR-2 | TC-6 |
| NFR-3 | TC-3, TC-4 |
