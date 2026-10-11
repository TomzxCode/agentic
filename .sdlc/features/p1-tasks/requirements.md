---
title: "Task management and timeline"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: Task management and timeline

## Overview

A task is the unit of work in Agentic.
This feature covers creating, listing, searching, viewing, updating, and deleting tasks, associating a task with zero or more repositories, and recording a timeline of every meaningful change so a task's evolution is visible at a glance.
It is the core of the product: items, worktrees, agent runs, and context all hang off a task.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Capture work, find it again, see what changed, edit inline |
| Coding agent | Read a task's current state, summary, and next steps through the API or CLI |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall create a task with a title (or a GitHub issue URL that supplies one), description, status, priority, tags, repository associations, group, and harness. |
| FR-2 | Must | The system shall list tasks newest-first, filtered by status and by a substring match over title, description, and summary. |
| FR-3 | Must | The system shall return a task's detail with its associations, worktrees, most recent runs, and timeline. |
| FR-4 | Must | The system shall update a task's fields and record the changed fields with their before and after values in the timeline. |
| FR-5 | Must | The system shall associate a task with zero or more repositories and record a timeline event when the set changes. |
| FR-6 | Must | The system shall delete a task and all of its child rows in foreign-key order, removing its worktrees from disk first. |
| FR-7 | Must | The system shall write a timeline event for every meaningful task change (created, updated, item added or removed, worktree changes, run start, context changes). |
| FR-8 | Should | The system shall stream task changes to subscribed clients over SSE. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Data integrity | Deleting a task shall not leave orphaned child rows or violate foreign-key constraints. |
| NFR-2 | Should | Performance | Listing and searching a few hundred tasks shall respond in under 200 ms on a local machine. |
| NFR-3 | Should | Maintainability | Deletes that touch parents shall use explicit, ordered delete statements, because SQLite enforces foreign keys and the ORM does not order cascades. |

## Constraints

- Persistence is SQLite through SQLModel; schema changes are applied in place, not by a migration tool.
- No authentication; the app assumes a trusted, single-user environment.
- Deletes must respect `PRAGMA foreign_keys=ON`.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Create a task with a title
      Given an empty task list
      When the user creates a task titled "Fix the flaky ingest test"
      Then the response is 201 with a generated id and status "open"
      And a "created" timeline event is recorded

    @FR-1
    Scenario: Require a title when no GitHub URL is given
      Given no title and no GitHub URL
      When the user creates a task
      Then the response is 400
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Record before and after for an edited field
      Given a task with status "open"
      When the user updates the status to "done"
      Then a timeline event of type "updated" is recorded
      And the event data lists status with "from" open and "to" done
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Delete a task with children
      Given a task with items, worktrees, runs, and timeline events
      When the user deletes the task
      Then the response is 204
      And no child rows reference the deleted task
      And its worktrees are removed from disk
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Deleting a task does not violate foreign keys
      Given a task with a run that has events
      When the task is deleted
      Then agent events are deleted before runs, and runs before the task
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should a task be hard-deleted or archived by default, given archived is already a status?
