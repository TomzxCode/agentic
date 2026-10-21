---
title: "Waiting on a person and snoozing a task"
status: draft
session_link: "http://localhost:10000/?session=ses_ea7d0aac4ffeV3TsloMQSksTqm"
---

# Requirements: Waiting on a person and snoozing a task

## Overview

Most stalls are other people: a task sits in progress while waiting for a reply, a review, or an approval, and `blocked` says neither who it waits on nor when to check back.
A task can also need to leave the focus stack for a while without being done or removed.
This feature adds two deferrals to a task: a **waiting-on** link to a person with an optional follow-up date, and a **snooze** until a date.
Both park the task off the focus stack and bring it back automatically when the date passes.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Say who a task waits on and when to check back, and park a task until a date, without losing its place in the stack |
| Coding agent | Read and set a task's waiting person, follow-up date, and snooze through the API or CLI |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | A task shall carry an optional waiting-on person and an optional follow-up date; creating or updating a task shall set, change, or clear them, and the task representation shall return them (with the person's name). |
| FR-2 | Must | A task shall carry an optional snooze date; setting it shall not change the task's status or mark it done. |
| FR-3 | Must | A task shall be **parked** (off the focus stack) while its snooze date is in the future, or while it waits on a person with no follow-up date or a follow-up date in the future. |
| FR-4 | Must | A parked task shall rejoin the focus stack automatically once its snooze or follow-up date passes, restoring the entry it left so its sessions and execution count survive the deferral. |
| FR-5 | Must | A task that was popped or removed from the stack shall not rejoin it; only a parking may be undone automatically. |
| FR-6 | Must | Setting a waiting-on person on an open or in-progress task shall mark it blocked; clearing the person shall clear the follow-up date and reopen a blocked task. An explicit status in the same request shall win. |
| FR-7 | Must | Pushing a parked task onto the stack shall be an explicit "work on it now": it clears the snooze and waiting fields and reopens a blocked task. |
| FR-8 | Must | The web app shall let the user set and clear the waiting person, the follow-up date, and the snooze from the task page, and shall show the waiting, check-back, and snooze state on task rows and stack rows. |
| FR-9 | Should | The CLI shall set and clear the waiting person, the follow-up date, and the snooze. |
| FR-10 | Should | Setting, changing, or clearing any of the three fields shall be recorded as a timeline event with the before and after values, resolving the person to a name. |
| FR-11 | Should | Deleting a person shall clear the tasks waiting on them (and their follow-up dates); merging a person into another shall move the wait to the target. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Data integrity | The three task fields and the stack entry's reason shall be nullable columns added in place, so an existing database keeps working (SQLModel creates but does not migrate). |
| NFR-2 | Should | Usability | The waiting and snooze controls shall stay usable and legible at phone widths, per the mobile-first design. |
| NFR-3 | Should | Consistency | The parking rule (snooze in the future, or waiting with no follow-up or a future follow-up) shall be identical on the server and in the web app. |
| NFR-4 | Should | Consistency | A deferral date with no timezone shall be treated as UTC, like a deadline. |

## Constraints

- Persistence is SQLite through SQLModel; the new columns are added by `db._ensure_columns()`.
- Times are stored in UTC; the web app shows them in the reader's local time zone.
- The stack is materialized from in-flight tasks on every read, so parking and unparking happen inside that sync rather than through a background job.
- The web app is designed with mobile in mind, so the new properties are checked at phone widths.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Wait on a person with a check-back date
      Given a task
      When the user sets the waiting person and a follow-up date
      Then the task returns both, and the waiting person's name

    @FR-1
    Scenario: Clear the wait
      Given a task waiting on a person with a follow-up date
      When the user clears the waiting person
      Then the task returns no person and no follow-up date
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Snooze a task
      Given an open task on the focus stack
      When the user snoozes it until tomorrow
      Then the task still reads as open
      And it is no longer on the focus stack
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Waiting with and without a check-back date
      Given a task waiting on a person with no follow-up date
      Then it is off the focus stack
      When a follow-up date in the future is set
      Then it stays off the focus stack
      When the follow-up date is moved to the past
      Then it is back on the focus stack
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: A deferral ends
      Given a snoozed task whose snooze date has passed
      When the focus stack is read
      Then the task is on it, at the position it would join as a new task
      And its previous sessions and execution count are preserved
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: A popped task stays gone
      Given a task popped off the stack
      When the focus stack is read again
      Then the task is not on it
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Waiting blocks the task
      Given an in-progress task
      When the user sets a waiting person
      Then the task is blocked
      When the user clears the waiting person
      Then the task is open again

    @FR-6
    Scenario: An explicit status wins
      Given an open task
      When a request sets both a waiting person and status done
      Then the task is done
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Pushing a snoozed task brings it back now
      Given a snoozed, blocked task waiting on a person
      When the user pushes it onto the stack
      Then it is current, no longer snoozed, no longer waiting, and open
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: See the deferral on the task page and rows
      Given a task waiting on Ada with a check-back date, and a snoozed task
      When the task page and the task list are shown
      Then the task page offers the waiting person and a check-back date, plus a snooze control
      And the waiting task's row reads "Waiting on Ada" with the check-back date
      And the snoozed task's row reads "Snoozed until <date>"
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: Defer from the CLI
      Given a task
      When the user runs `agentic task update <task> --waiting-on <person> --follow-up <when>`
      Then the task waits on that person until that date
      When the user runs `agentic task update <task> --snooze <when>`
      Then the task is snoozed until that date
      When the user runs `agentic task update <task> --clear-waiting --clear-snooze`
      Then the task waits on no one and is not snoozed
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: A wait is recorded on the timeline
      Given a task
      When the waiting person is set
      Then an "updated" timeline event records the field with the person's name
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: The person goes away
      Given a task waiting on a person with a follow-up date
      When the person is deleted
      Then the task waits on no one and has no follow-up date
      When the person is merged into another instead
      Then the task waits on the remaining person
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: An existing database gains the columns
      Given an existing database without the new columns
      When the app starts
      Then the task table gains the three nullable columns and the stack entry table gains its reason
      And existing tasks read as waiting on no one and not snoozed
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: Deferral controls fit a phone
      Given a viewport 375 px wide
      When the task page and the task list are shown
      Then the waiting person, check-back date, and snooze controls are visible
      And no horizontal scrolling is needed to reach them
    ```

- [ ] **NFR-3 / NFR-4**

    ```gherkin
    @NFR-3 @NFR-4
    Scenario: The same parking rule everywhere
      Given a task snoozed until tomorrow and a task waiting with no follow-up
      When the focus stack is read through the API and shown in the web app
      Then neither task appears on the stack in either place
      And a deferral date with no timezone is stored as that instant in UTC
    ```

## Conflicts

- Waiting marks a task blocked, while snoozing deliberately leaves the status alone: a snooze is "not now", not "stuck". The two are kept distinct so the blocked filter still means something.

## Open Questions

1. Should a due follow-up raise an inbox suggestion (a nudge to check back), or is the task reappearing on the stack enough?
2. Should the stack show parked tasks in a separate collapsible section, rather than only on the tasks page?
3. Should a snooze repeat (every Monday), or is a one-off date enough?
