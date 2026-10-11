---
title: "Worktrees"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: Worktrees

## Overview

A worktree gives each task an isolated checkout to work in, so parallel tasks do not collide on the working tree.
This feature creates a git worktree for a task from a registered repository (defaulting the branch name), lists a task's worktrees, and removes them from disk and from tracking.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Work on a task in isolation without disturbing the main checkout |
| Coding agent | Run in a dedicated directory for the task |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall create a worktree for a task from a repository, defaulting the branch to `agentic/<slug>-<task-id-prefix>` when none is given. |
| FR-2 | Must | The system shall check out the branch if it exists, otherwise create it from the repository's default branch or an explicit base. |
| FR-3 | Must | The system shall place a worktree at `AGENTIC_WORKTREE_ROOT/<task_id>/<slug-of-branch>`. |
| FR-4 | Must | The system shall list a task's worktrees. |
| FR-5 | Must | The system shall remove a worktree from disk and mark it removed, while keeping its row and recording a timeline event. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Reliability | A failed `git worktree` command shall surface as a 400 with the git error, not a 500. |
| NFR-2 | Should | Reliability | Git commands shall run with timeouts so a hung git process cannot block a request forever. |

## Constraints

- Worktrees require a registered repository and a valid git checkout.
- The database row is kept after removal (soft delete) so history is preserved.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Create a worktree with a default branch
      Given a task and a registered repository
      When the user creates a worktree without a branch
      Then a branch named "agentic/<slug>-<id4>" is created
      And the worktree path is under the worktree root
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Remove a worktree
      Given a task with an active worktree
      When the user removes it
      Then the directory is removed from disk
      And the row status becomes "removed"
      And a "worktree_removed" timeline event is recorded
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Git failure surfaces as a client error
      Given a repository where the branch cannot be created
      When the user creates a worktree
      Then the response is 400 with the git error message
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should context refresh and agent runs default to the newest active worktree (as they do now) or require an explicit choice?
