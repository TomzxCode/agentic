---
title: "Task tags"
status: done
session_link: "http://localhost:10000/?session=ses_ed2936849ffePjqvp9kEDOH0mX"
---

# Requirements: Task tags

## Overview

Tags are short free-form labels that a task carries so related work can be grouped without changing its status or the repository it belongs to.
Tasks already store a `tags` list, but nothing lets the user query by tag, see which tags exist, or edit them in the app.
This feature makes tagging usable end to end: tags are normalized on write, tasks can be filtered by one or more tags over the API, CLI, and web UI, and the set of tags in use can be enumerated.
It is the foundation for tag-driven views (for example a board or a lane per tag) that are out of scope here.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Label a task, find every task with that label, and see a task's labels at a glance |
| Coding agent | Read and set a task's tags through the API or CLI, and filter tasks by tag |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall accept a list of tags when a task is created or updated, and normalize it on write by trimming each label, dropping empty ones, and removing duplicates while preserving order. |
| FR-2 | Must | The system shall filter the task list by one or more tags, returning only tasks that carry every requested tag. |
| FR-3 | Must | The system shall expose the set of tags in use, each with the number of tasks that carry it, ordered by count descending and then case-insensitively by name. |
| FR-4 | Must | The web app shall let the user add and remove tags on a task and show the task's tags. |
| FR-5 | Must | The web app shall let the user filter the main tasks list by a tag and show each task's tags in that list; the sidebar entry shows no tags, as governed by FEAT-p10. |
| FR-6 | Must | The web app shall let the user set tags when creating a task. |
| FR-7 | Should | The CLI shall list tasks filtered by tag (repeatable, all must match) and list the tags in use with their counts. |
| FR-8 | Should | Changing a task's tags shall be recorded as a timeline event with the before and after values. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Data integrity | Tags shall be stored in the existing `task.tags` JSON column, so no new table or column is introduced and existing databases keep working. |
| NFR-2 | Should | Consistency | The tag filter's semantics (all requested tags must be present, exact trimmed match) shall be identical across the API, the CLI, and the web UI. |
| NFR-3 | Should | Usability | Tag controls shall stay usable and legible at phone widths, per the project's mobile-first design. |
| NFR-4 | Should | Performance | Listing a few hundred tasks filtered by a tag shall respond in under 200 ms on a local machine. |

## Constraints

- Persistence is SQLite through SQLModel; the `task.tags` column already exists, so no schema migration is required.
- No authentication; the app assumes a trusted, single-user environment.
- Tags are case-sensitive; only surrounding whitespace is normalized away.
- The web app is designed with mobile in mind, so tag UI is checked at phone widths.
- The sidebar entry does not show tags; its layout is governed by FEAT-p10. The tag filter strip above the sidebar list stays here.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Normalize tags on create
      Given a new task with tags ["bug", " bug ", "", "ui"]
      When the task is created
      Then its stored tags are ["bug", "ui"]

    @FR-1
    Scenario: Normalize has no effect on an already clean list
      Given a new task with tags ["bug", "ui"]
      When the task is created
      Then its stored tags are ["bug", "ui"]
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Filter by a single tag
      Given one task tagged ["bug"], one tagged ["bug", "ui"], and one tagged ["infra"]
      When the task list is requested with tag "bug"
      Then the two tasks carrying "bug" are returned
      And the task tagged "infra" is not

    @FR-2
    Scenario: Several tags narrow the result
      Given one task tagged ["bug"] and one tagged ["bug", "ui"]
      When the task list is requested with tags "bug" and "ui"
      Then only the task tagged ["bug", "ui"] is returned

    @FR-2
    Scenario: An unknown tag matches nothing
      Given tasks exist but none carry the tag "nope"
      When the task list is requested with tag "nope"
      Then the result is empty
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Tag counts reflect the tasks that carry them
      Given two tasks tagged "bug" and one task tagged "infra"
      When the tag list is requested
      Then "bug" is listed with count 2
      And "infra" is listed with count 1
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: Changing tags is recorded
      Given a task tagged "bug"
      When the user changes its tags to "bug" and "urgent"
      Then an "updated" timeline event records tags with "from" ["bug"] and "to" ["bug", "urgent"]
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Add and remove a tag on a task
      Given a task with no tags
      When the user adds the tag "bug"
      Then the task's tags are ["bug"]
      When the user removes the tag "bug"
      Then the task's tags are []

    @FR-4
    Scenario: Ignore an empty or duplicate entry
      Given a task already tagged "bug"
      When the user submits an empty value and then "bug" again
      Then the task's tags remain ["bug"]
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Filter the list by tag
      Given tasks tagged "bug" and "ui"
      When the user selects the "bug" filter
      Then only the tasks tagged "bug" are shown
      And a filtered count is shown for the selected tag
      When the user clears the filter
      Then every task is shown again

    @FR-5
    Scenario: Show a task's tags in the list
      Given a task tagged "bug" and "ui"
      When its row is shown in the main tasks list
      Then it shows both tags
      And selecting a tag on the row filters the list by it

    @FR-5
    Scenario: Filter from the command palette
      Given tasks tagged "bug" and "ui"
      When the user opens the command palette and picks "Filter by tag: bug"
      Then only the tasks tagged "bug" are shown
      And the palette offers a "Clear tag filter" action
      When the user picks "Clear tag filter"
      Then every task is shown again
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Set tags when creating a task
      Given the new task form
      When the user enters the tag "bug" and creates the task
      Then the created task carries the tag "bug"
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Filter from the CLI
      Given tasks tagged "bug" and "ui"
      When the user runs `agentic task list --tag bug`
      Then only tasks tagged "bug" are listed

    @FR-7
    Scenario: List tags from the CLI
      Given two tasks tagged "bug"
      When the user runs `agentic tag list`
      Then "bug" is listed with count 2
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: The same filter everywhere
      Given a task tagged "bug" and another tagged "Bug"
      When a filter for "bug" is applied through the API, the CLI, and the web UI
      Then all three return exactly the task tagged "bug"
    ```

- [ ] **NFR-4**

    ```gherkin
    @NFR-4
    Scenario: Tag filtering stays fast locally
      Given 300 tasks
      When the task list is requested filtered by a tag
      Then the response is returned in under 200 ms
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Tags live on the task row
      Given an existing database
      When a task is created with tags
      Then the task detail returns those tags
      And the tag list is derived from the tasks
      And no separate tag table is created
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: Tag controls fit a phone
      Given a viewport 375 px wide
      When the task detail and the new-task form are shown
      Then the tag chips and the tag entry field are visible
      And no horizontal scrolling is needed to reach them
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should tags be case-insensitive (so "Bug" and "bug" are one tag), or stay case-sensitive as implemented?
2. Should there be a way to rename or delete a tag across every task at once, or is per-task editing enough?
3. Should there be a limit on the number of tags per task?
