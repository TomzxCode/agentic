---
title: "Task deadlines"
status: draft
session_link: "http://localhost:10000/?session=ses_ecbf732d0ffed1QhZoN01LtncD"
---

# Requirements: Task deadlines

## Overview

A task can carry a deadline: the date and time by which it should be done.
Today a task has a status, a priority, and tags, but nothing records when it is due, so there is no way to see what needs attention soon.
This feature adds an optional deadline to a task, lets it be set and cleared everywhere a task is edited, and surfaces the tasks whose deadlines are coming up on the tasks page.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Set a deadline on a task, and see which tasks are due soon (or already overdue) at a glance |
| Coding agent | Read and set a task's deadline through the API or CLI |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | A task shall carry an optional deadline (a date and time); creating or updating a task shall set, change, or clear it, and the task representation shall return it. |
| FR-2 | Must | The system shall list the in-flight tasks whose deadline falls within a window of days, soonest first, with overdue deadlines always included. |
| FR-3 | Must | The web app shall let the user set, change, and clear a task's deadline from the task page, and set a deadline when creating a task. |
| FR-4 | Must | The web app shall show a task's deadline state on its row and list the upcoming deadlines on the tasks page, flagging overdue and due-soon tasks and letting the window change. |
| FR-5 | Should | The CLI shall set and clear a task's deadline and list the upcoming deadlines within a window. |
| FR-6 | Should | Setting, changing, or clearing a deadline shall be recorded as a timeline event with the before and after values. |
| FR-7 | Should | A deadline supplied without a timezone shall be treated as UTC. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Data integrity | The deadline shall be a new nullable column on the task table, added in place so an existing database keeps working (SQLModel creates but does not migrate). |
| NFR-2 | Should | Usability | The deadline controls shall stay usable and legible at phone widths, per the mobile-first design. |
| NFR-3 | Should | Consistency | The "coming soon" rule (in-flight only, deadline at or before now plus the window, overdue included) shall be identical in the API endpoint and the web view. |

## Constraints

- Persistence is SQLite through SQLModel; the new column is added by `db._ensure_columns()`.
- Times are stored in UTC; the web app shows them in the reader's local time zone.
- The granularity is a date and time (not a date alone), chosen with the user.
- The web app is designed with mobile in mind, so the deadline surfaces are checked at phone widths.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Set a deadline on create
      Given the new task form
      When the user sets a deadline and creates the task
      Then the created task returns that deadline

    @FR-1
    Scenario: Change and clear a deadline
      Given a task with a deadline
      When the user changes the deadline
      Then the task returns the new deadline
      When the user clears the deadline
      Then the task returns no deadline
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Upcoming deadlines include near and overdue tasks
      Given an overdue task, a task due in two days, a task due in thirty days, and a task with no deadline
      When the upcoming deadlines are requested with a seven-day window
      Then the overdue and two-day tasks are returned, soonest first
      And the thirty-day and deadline-less tasks are not

    @FR-2
    Scenario: A closed task leaves the view
      Given a task due tomorrow with status done
      When the upcoming deadlines are requested
      Then it is not returned
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Edit a deadline from the task page
      Given a task page
      When the user opens the deadline control and picks a date and time
      Then the task saves the new deadline and shows it with its due state
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: See deadlines coming up on the tasks page
      Given in-flight tasks with deadlines near and far away
      When the tasks page is shown
      Then the near deadlines appear under "Upcoming deadlines", soonest first
      And each in-flight row with a deadline shows its due state
      When the user widens the window
      Then tasks further out appear
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Manage deadlines from the CLI
      Given a task
      When the user runs `agentic task create --deadline <when>`
      Then the task carries that deadline
      When the user runs `agentic task deadlines`
      Then the tasks with a deadline coming up are listed, overdue first
      When the user runs `agentic task update <task> --clear-deadline`
      Then the task no longer has a deadline
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Changing a deadline is recorded
      Given a task with no deadline
      When the deadline is set
      Then an "updated" timeline event records deadline with "from" null and "to" the new value
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: A naive deadline is UTC
      Given a client that sends a deadline with no timezone
      When the task is created
      Then the stored deadline is that instant in UTC
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: An existing database gains the column
      Given an existing database without a deadline column
      When the app starts
      Then the task table gains a nullable deadline column
      And existing tasks read as having no deadline
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: Deadline controls fit a phone
      Given a viewport 375 px wide
      When the tasks page and the task page are shown
      Then the deadline control, the upcoming-deadlines section, and the row badges are visible
      And no horizontal scrolling is needed to reach them
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: The same window rule everywhere
      Given an overdue task and a task due in two days
      When the upcoming deadlines are requested through the API and shown in the web app with the same window
      Then both return exactly the same tasks, in the same order
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should there be a reminder/notification when a deadline is reached, or is seeing it in the view enough?
2. Should a deadline be shown on the Gantt page as a marker on the task's bar?
3. Should reminders recur (for example a weekly review task), or is a one-off deadline enough?
