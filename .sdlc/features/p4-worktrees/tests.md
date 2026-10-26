---
title: "Worktrees"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: Worktrees

## Scope

Covers worktree creation (branch defaulting, base, path), repository resolution from the task, listing, and removal, plus the git helpers in `services/git.py`.
Out of scope: the SPA's WorktreesPanel rendering.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Detect the origin remote | a checkout with and without origin | the remote URL, or None |
| TC-2 | Detect the default branch | origin/HEAD set, then main/master | `origin/HEAD` wins, else main, else master, else None |
| TC-3 | Create a worktree on an existing branch | a branch that already exists | `git worktree add <path> <branch>`, no `-b` |
| TC-4 | Create a worktree with a new branch | a branch that does not exist | `git worktree add -b <branch> <path> [base]` |
| TC-5 | Create fails on a git error | a failing `git worktree add` | RuntimeError with the git stderr |
| TC-6 | Remove a worktree | an existing worktree path | `worktree remove --force` then `prune` |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-7 | Create with no repository_id | a task with one repository | the worktree resolves to the task's repository |
| TC-8 | Create with no repository anywhere | a task without repositories | 400 |
| TC-9 | Create with explicit repository, branch, base | a task, a repository, and a payload | 201, worktree listed under the task, unknown task is 404 |
| TC-10 | Create with an unknown repository_id | `repository_id: "nope"` | 404 |
| TC-11 | Git failure surfaces as a 400 | create_worktree raises | 400 with the git error in the detail |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-12 | Remove a worktree | 204, directory removed via remove_worktree, row marked `removed`, 404 for an unknown id |

## Test Infrastructure

- `monkeypatch` replaces `worktrees_router.create_worktree` / `remove_worktree` so no git command runs in the API tests.
- `test_services_git.py` drives `services.git` against temporary git repositories and a stubbed `shell._git`.
- `TestClient` over the app; `tmp_path` builds `.git`-marked folders.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-3, TC-7, TC-9 |
| FR-2 | TC-3, TC-4, TC-9 |
| FR-3 | TC-9 |
| FR-4 | TC-9 |
| FR-5 | TC-6, TC-12 |
| NFR-1 | TC-5, TC-11 |
| NFR-2 | TC-2 (timeouts on every `shell._git` call) |
