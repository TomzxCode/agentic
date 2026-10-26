---
title: "Focus stack and launcher"
status: done
revision: 1
---

# Requirements: Focus stack and launcher

## Overview

The focus stack gives the sole user one ordered queue of the work in flight, with the task being worked on right now at the top.
A task list sorted by recency does not say what to do next, and a context switch loses the place.
The stack is materialized from the tasks instead of being maintained by hand: every open, in-progress, or blocked task joins it, and a task that waits on a person or is snoozed stays off it until its date passes and then returns on its own.
Each stretch of time a task spends at the top is recorded as a session, so the page can show how many times and how long each task has been current without storing counters.
Popping or removing an entry soft-deletes it, so the stack keeps a history of what was worked on.
A native tray companion adds what a browser cannot provide: a global hotkey that opens the stack page from anywhere and a Mark Done action that pops the current task.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Know what to work on next, drive the queue by keyboard and drag, and see how long each task has held the focus |
| Coding agent | Read and mutate the stack over HTTP and the CLI so agent sessions work the same queue |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall materialize the stack from the tasks: every task with status open, in_progress, or blocked that is not parked and has never had a stack entry joins the stack at the bottom on the next stack read, keeping the existing order. |
| FR-2 | Must | The system shall keep the active entries ordered by position, with position 0 as the current task (is_current true) and every other entry queued (is_current false). |
| FR-3 | Must | The system shall add a task to the stack by title (a new task) or task_id (an existing task) at position top, next, or last, where top makes it current, next inserts after the current task (or makes it current on an empty stack), and last appends. |
| FR-4 | Must | The system shall reject a push of a task already on the stack (409), an unknown task_id (404), and a push with neither a non-blank title nor a task_id (400). |
| FR-5 | Must | The system shall, on pop, mark the current task done, soft-delete its entry with reason popped, promote the next entry, and return an empty list when the stack is empty. |
| FR-6 | Must | The system shall remove any active entry by soft-deleting it with reason removed while leaving its task's status unchanged, and shall report 404 for an unknown entry. |
| FR-7 | Must | The system shall reorder an entry to a target position (clamped to the valid range) and promote an entry by moving it to position 0, re-deriving the current flag in both cases. |
| FR-8 | Must | The system shall open a task session when an entry becomes current and close it when the entry stops being current, and shall derive started_at, last_current, duration, and execution_count from the sessions without storing them. |
| FR-9 | Must | The system shall keep popped and removed entries with their deleted_at and deleted_reason, list that history most recently removed first, and exclude parked entries from it. |
| FR-10 | Must | The system shall park a task whose snoozed_until is in the future, or that waits on a person with a future or absent follow-up date, by dropping its entry with reason parked, and shall restore that entry with its sessions intact when the deferral ends. |
| FR-11 | Should | The system shall clear a task's snooze, wait, and follow-up date when it is pushed, reopening a task parked by a wait, and shall reuse the parked entry so sessions and the execution count survive the deferral. |
| FR-12 | Should | The system shall edit the task behind an entry (its title and description) through the entry, ignoring a blank title. |
| FR-13 | Must | The system shall drop an entry whose task has left the in-flight statuses on the next stack read, and shall delete a task's stack entries and sessions when the task is deleted. |
| FR-14 | Must | The system shall expose the stack over HTTP (list, history, current, push, pop, reorder, promote, update, remove). |
| FR-15 | Must | The CLI shall expose the stack as `agentic stack` commands (list, current, history, push, pop, promote, reorder, edit, remove) and shall fail a push that has neither a title nor a task id. |
| FR-16 | Should | The SPA shall provide a Stack page at /stack that lists the queue with the current task first, adds from the input (Enter to the top, Shift+Enter after the current task), filters as you type, and edits a row's title and description in place. |
| FR-17 | Should | The Stack page shall reorder by keyboard (arrow keys, Home or /) and by dragging (mouse anywhere on a row, touch or pen only from the handle, disabled while a filter is set), and shall show status and priority pickers, a deadline badge, a duration that ticks each second for the current task, a history panel, and a shortcut help panel. |
| FR-18 | Should | The launcher (`agentic-stack`) shall show a tray icon with the current task title and a stack depth badge, refresh it every 30 seconds, open the stack page from its menu or the global hotkey, and pop the current task from its menu. |
| FR-19 | Should | The launcher shall read its configuration from the environment (AGENTIC_API_URL, AGENTIC_STACK_URL, AGENTIC_STACK_HOTKEY, AGENTIC_STACK_OPEN), fall back to the default hotkey when the spec is invalid, and on macOS run the hotkey listener in a subprocess that exits when the parent exits, prompting for Accessibility and Input Monitoring on first run. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Correctness | Execution count and duration shall be derived from task sessions only, so no stored counter can drift. |
| NFR-2 | Should | Performance | Assembling a stack response shall batch its reads (one query for the tasks, one for the sessions of all entries), and a sync that changes nothing shall write nothing. |
| NFR-3 | Should | Reliability | Stack history shall survive removals; entries shall be hard-deleted only with their task, in explicit foreign-key-safe order. |
| NFR-4 | Should | Correctness | Datetimes shall be UTC, and a naive datetime read back from SQLite shall be treated as UTC. |
| NFR-5 | Should | Usability | Page keyboard shortcuts shall ignore modifier combinations so Cmd and Ctrl shortcuts still reach the browser, and touch dragging shall start only from the row handle so the list can scroll. |
| NFR-6 | Should | Reliability | The launcher shall survive API errors, hotkey callback errors, and a lost hotkey subprocess without crashing the tray. |

## Constraints

- Persistence is SQLite via SQLModel; the `stackentry` and `tasksession` tables are created by `create_all`.
- The stack lives in the backend; the SPA, the CLI, and the launcher are clients of the same HTTP API.
- A task has at most one active stack entry; it keeps one soft-deleted entry per removal.
- The launcher talks to the API over localhost (default `http://127.0.0.1:8600`) with the CLI's provenance headers.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: An in-flight task joins the stack automatically
      Given the tasks "Open", "In progress", "Blocked", "Done", and "Archived" exist
      When the stack is read
      Then the stack holds exactly the open, in-progress, and blocked tasks
      And a new open task appears at the bottom on the next read
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Position 0 is current
      Given a stack with three entries
      When the stack is read
      Then the entry at position 0 has is_current true
      And the entries at positions 1 and 2 have is_current false
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Push positions
      Given a stack whose current task is "first"
      When "next" is pushed with position next and "last" with position last
      Then the order is "first", "next", "last"
      When "top" is pushed with position top
      Then "top" is at position 0 and is the current task
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Push validation
      Given a task that is already on the stack
      When that task is pushed by id
      Then the response is 409
      When an unknown task id is pushed
      Then the response is 404
      When a blank title is pushed without a task id
      Then the response is 400
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Pop completes the current task and promotes the next
      Given a stack with "a" current and "b" queued
      When the stack is popped
      Then "a" has status done and appears in the history
      And "b" is at position 0 and is current
      When the stack is popped twice more
      Then the response is an empty list both times
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Remove keeps the task
      Given a queued entry for the open task "a"
      When the entry is removed
      Then the stack holds only "b" and "a" still has status open
      And the entry appears in the history
      When an unknown entry id is removed
      Then the response is 404
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Reorder and promote
      Given a stack with "c", "b", "a" from the top
      When the last entry is moved to position 1
      Then the order is "c", "a", "b" with positions 0, 1, 2
      When entry "b" is promoted
      Then "b" is at position 0 and is current
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: Sessions count the focus stints
      Given entry "b" was pushed, lost the focus, and was promoted again
      When the stack is read
      Then "b" reports execution_count 2 and a duration of at least 0
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: History keeps removed work
      Given one popped entry and one removed entry
      When the history is read
      Then both entries are listed, most recently removed first
      And a parked entry is not in the history
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: A snoozed task parks and returns
      Given an open task on the stack
      When it is snoozed until tomorrow
      Then it leaves the stack without joining the removal history
      When the snooze date moves into the past
      Then the task is on the stack again
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: Pushing a parked task clears the deferral
      Given a task waiting on a person with no follow-up date
      When the task is pushed by id
      Then its wait and follow-up date are cleared and its status is open
      And it is on the stack
    ```

- [ ] **FR-12**

    ```gherkin
    @FR-12
    Scenario: Edit through the entry
      Given the current entry
      When its title is patched to "after" and its description to "note"
      Then the task behind it carries the new title and description
      When the title is patched to a blank string
      Then the title is unchanged
    ```

- [ ] **FR-13**

    ```gherkin
    @FR-13
    Scenario: A finished task leaves the stack
      Given an open task on the stack
      When the task's status is set to done
      Then the next stack read no longer lists it
      When the task is deleted
      Then its stack entries and sessions are gone
    ```

- [ ] **FR-14**

    ```gherkin
    @FR-14
    Scenario: The HTTP surface answers
      Given a running API
      When each stack endpoint is called
      Then each returns the documented response, with 201 on push and 204 on delete
    ```

- [ ] **FR-15**

    ```gherkin
    @FR-15
    Scenario: The CLI works the stack
      Given the CLI pointed at a running API
      When list, current, history, push, pop, promote, reorder, edit, and remove are run
      Then each prints the resulting stack or a confirmation
      When push is run with neither a title nor a task id
      Then it prints an error to stderr and exits with status 1
    ```

- [ ] **FR-16**

    ```gherkin
    @FR-16
    Scenario: Add and edit from the page
      Given the Stack page with two entries
      When a title is typed and Enter is pressed
      Then the task is pushed with position top
      When a title is typed and Shift+Enter is pressed
      Then the task is pushed with position next
      When a row's title is edited in place
      Then the entry is patched with the new title
    ```

- [ ] **FR-17**

    ```gherkin
    @FR-17
    Scenario: Keyboard and drag reordering
      Given the Stack page with two entries and the second row selected
      When ArrowLeft is pressed
      Then reorder is called with the entry id and position 0
      When the first row is dragged with a mouse past the second row's midpoint
      Then reorder is called with position 1
      When the row body is dragged with a touch pointer
      Then no reorder call is made
      When a filter is set and a row is dragged
      Then no reorder call is made
    ```

- [ ] **FR-18**

    ```gherkin
    @FR-18
    Scenario: The tray mirrors the stack
      Given the launcher running against a stack with a current task
      When the tray refreshes
      Then the tooltip shows the current task title and the badge shows the stack depth
      When Mark Done is chosen
      Then the pop endpoint is called and the tray updates
    ```

- [ ] **FR-19**

    ```gherkin
    @FR-19
    Scenario: Hotkey configuration
      Given AGENTIC_STACK_HOTKEY set to a valid spec
      When the launcher starts
      Then the menu shows the configured hotkey label
      When AGENTIC_STACK_HOTKEY is invalid
      Then the launcher warns and uses ctrl+shift+t
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Stats come from sessions
      Given an entry with recorded sessions
      When the entry is read after each focus change
      Then execution_count equals the number of sessions and duration equals their summed time
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: A no-change sync writes nothing
      Given a materialized stack
      When the stack is read twice with no task changes in between
      Then the second read performs no stack writes
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: Removals keep history
      Given a removed entry for a task that stays open
      When the entry is read
      Then its row still exists with deleted_at set
    ```

- [ ] **NFR-4**

    ```gherkin
    @NFR-4
    Scenario: Naive datetimes are UTC
      Given a snooze and a follow-up saved without a timezone
      When the task is read back
      Then the timestamps are unchanged and are compared as UTC
    ```

- [ ] **NFR-5**

    ```gherkin
    @NFR-5
    Scenario: Browser shortcuts survive
      Given the Stack page focused
      When a key press carries a Cmd or Ctrl modifier
      Then the page does not act on it
    ```

- [ ] **NFR-6**

    ```gherkin
    @NFR-6
    Scenario: The tray survives errors
      Given the launcher running with the API down
      When a refresh or a Mark Done fails
      Then the tray stays alive and retries on the next poll
    ```

## Conflicts

None identified.

## Open Questions

None.
The behavior was taken from the shipped code, the CLI, the launcher, and the documentation pages.
