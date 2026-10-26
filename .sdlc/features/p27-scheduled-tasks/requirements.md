---
title: "Scheduled shell tasks"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: Scheduled shell tasks

## Overview

A scheduled task holds a shell command and a 5-field cron expression, and the app runs it for the user on that cadence.
The scheduler lives in the API process: it wakes every `AGENTIC_SCHEDULED_TASK_TICK` seconds, finds the enabled tasks whose next occurrence has passed, advances the occurrence, and runs the command in the background.
Every execution is recorded as a run with its status, exit code, and the combined output, so a backup or a report leaves its result readable in the app instead of in a log nobody opens.
The Schedules page edits tasks with a live preview of the next runs, and the CLI gives agents the same create, edit, run, and history surface.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Run recurring scripts from the app and read each run's output later |
| Coding agent | Create, pause, and inspect scheduled tasks through the CLI |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall store a scheduled task with a name, a shell command, an optional working directory, a 5-field cron expression, an optional IANA timezone, and an enabled flag. |
| FR-2 | Must | The system shall refuse a task with a blank name or command, and a schedule that does not have exactly 5 fields or is not a valid cron expression, with 400 and a message naming the problem. |
| FR-3 | Must | The system shall compute next_run_at as the first occurrence of the cron expression after now in the task's timezone, stored as UTC, using the server's local timezone when none is set and collapsing the server zone's UTC aliases for display. |
| FR-4 | Must | The system shall clear next_run_at when a task is disabled and recompute it when the task is enabled or its schedule or timezone changes, keeping the pending occurrence when only the name, command, or working directory changes. |
| FR-5 | Must | The system shall tick on a timer (default 30 seconds), start every enabled task whose next_run_at has passed in the background, and skip a task that is already running. |
| FR-6 | Must | The system shall advance next_run_at before the command starts, so a slow or overrunning command is never started twice for the same occurrence. |
| FR-7 | Must | The system shall run the command through the shell so pipes, redirects, and `&&` work as written, capture combined stdout and stderr truncated to the last 20,000 characters, and stop the command after `AGENTIC_SCHEDULED_TASK_TIMEOUT` seconds (default 3600, 0 disables the timeout), recording the timeout as a failure. |
| FR-8 | Must | The system shall record every execution as a run row created in status running and finalized as succeeded on exit code 0 and failed otherwise, including a failed start (for example a missing working directory, recorded with no exit code and a message). |
| FR-9 | Must | The system shall start a run immediately from an endpoint, in the background, returning the run row. |
| FR-10 | Must | The system shall expose run history: one task's runs newest first (default 20, at most 200), every task's runs newest first with the task's name and command (default 100, at most 500), and one run's read by id. |
| FR-11 | Should | The system shall report each task's last status and last exit code on list and read, and order the list with enabled tasks first, soonest next run first. |
| FR-12 | Should | The system shall validate a cron expression and return its next occurrences (1 to 20, default 5) in a timezone from a preview endpoint, refusing an unknown zone or a bad expression with 400. |
| FR-13 | Must | The system shall delete a task together with its run history, and answer 404 for unknown task or run ids on every operation. |
| FR-14 | Must | The system shall mark runs left `running` by a previous process as failed at startup, appending an "Interrupted" note to their output and stamping ended_at. |
| FR-15 | Should | The web UI shall provide a Schedules page with a new-task form and per-row edit forms (each keeping its own draft, with a browser-computed "next 5 runs" preview that updates while typing), pause and enable, run now, delete after confirmation, per-row run history with output, an executions tab across all tasks, and silent refreshes (every 15 seconds, faster while runs are active). |
| FR-16 | Should | The CLI shall provide `agentic schedule` commands to list, get, create, update, delete, run, and show run history. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Should | Reliability | A run shall start within one scheduler tick of its scheduled minute, and the API returns at once because runs execute in the background. |
| NFR-2 | Must | Robustness | Commands shall run as asyncio subprocesses off the event loop, with strong references keeping background tasks alive until they finish. |
| NFR-3 | Should | Correctness | A cron expression shall be evaluated in a named IANA zone, so 09:00 stays 09:00 across daylight-saving changes. |
| NFR-4 | Should | Operability | The tick interval and command timeout shall be configurable through `AGENTIC_SCHEDULED_TASK_TICK` and `AGENTIC_SCHEDULED_TASK_TIMEOUT`. |
| NFR-5 | Should | Usability | The in-browser preview shall be instant and update as the user types, with `/api/schedules/preview` as the exact server-side answer computed by the same cron engine. |

## Constraints

- The scheduler runs inside the API process, so nothing fires while `agentic-server` is stopped.
- A run is not durable: a restart loses the in-flight command, and reconciliation records that as a failure.
- Run history is kept until the task is deleted; there is no per-run pruning.
- A scheduled task is the app's own periodic work, kept apart from a `Task` (a unit of tracked work) and from agent runs.
- Deletes use explicit ordered statements: the runs first, then the task.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Create a scheduled task
      When a task is created with name "hello", command "echo hi", and schedule "*/5 * * * *"
      Then the response is 201 with next_run_at set and the server's timezone resolved
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: A bad schedule is refused
      When a task is created with schedule "nope"
      Then the response is 400

    @FR-2
    Scenario: Blank name or command is refused
      When a task is created with a blank name or a blank command
      Then the response is 400
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: The timezone decides when 09:00 fires
      Given a task with schedule "0 9 * * *" and timezone "Asia/Tokyo"
      When it is created
      Then next_run_at is 00:00 UTC

    @FR-3
    Scenario: An unknown zone is refused
      When a task is created with timezone "Mars/Base"
      Then the response is 400
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Pausing clears the next run
      Given an enabled task
      When it is disabled
      Then next_run_at is null and enabling it again computes a new one
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: The scheduler runs due tasks once
      Given a due enabled task, a disabled task, and a future task, all due-looking
      When one tick runs
      Then exactly the enabled due task started and the list shows only its succeeded run
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: A second tick does not refire
      Given a task whose run just started
      When the next tick runs
      Then no new run row was created because next_run_at moved into the future
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Output is captured
      When a task runs "echo hi"
      Then the run settles succeeded with exit code 0 and "hi" in its output
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: A failing command is recorded
      When a task runs "exit 3"
      Then the run settles failed with exit code 3

    @FR-8
    Scenario: A missing working directory is recorded
      When a task with cwd "/no/such/directory" runs
      Then the run settles failed with no exit code and a message naming the directory
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: Run now
      When POST /api/schedules/{id}/run is called
      Then the response is 201 with a run id and the run settles on its own
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: History endpoints
      Given a task with a finished run
      When its runs, the cross-task executions list, and the single run are read
      Then each returns the run, and the executions row carries the task's name and command
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: The list shows the last outcome
      Given a task whose newest run succeeded
      When the task list is read
      Then the task's last_status is "succeeded"
    ```

- [ ] **FR-12**

    ```gherkin
    @FR-12
    Scenario: Preview the next runs
      When /api/schedules/preview is queried with "0 9 * * *", timezone "Asia/Tokyo", and count 3
      Then the response lists three runs at 00:00 UTC and names the zone
      And an unknown zone or a bad expression answers 400
    ```

- [ ] **FR-13**

    ```gherkin
    @FR-13
    Scenario: Delete removes history too
      Given a task with runs
      When the task is deleted
      Then the response is 204, the task list is empty, and the run rows are gone
    ```

- [ ] **FR-14**

    ```gherkin
    @FR-14
    Scenario: A restart marks a lost run failed
      Given a run row left in status running by a previous process
      When reconciliation runs
      Then the run is failed, its output carries the "Interrupted" note, and ended_at is stamped
    ```

- [ ] **FR-15**

    ```gherkin
    @FR-15
    Scenario: The form previews while typing
      When a valid cron expression and zone are typed into the form
      Then the next 5 runs are listed in that zone without a server request
      And each row's edit form keeps its own draft when another form opens
    ```

- [ ] **FR-16**

    ```gherkin
    @FR-16
    Scenario: Create and run from the CLI
      When `agentic schedule create --name backup --schedule "0 3 * * *" --command "make backup"` runs, then `agentic schedule run <id>`
      Then the CLI reports the created task and the started run
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: Wall-clock time survives a DST change
      Given the server zone is Europe/Paris and the day before the spring-forward
      When the next occurrence of "0 9 * * *" is computed from 2026-03-28 09:00 UTC
      Then it is 2026-03-29 07:00 UTC, which is 09:00 in Paris on the later offset
    ```

- [ ] **NFR-5**

    ```gherkin
    @NFR-5
    Scenario: The preview endpoint agrees with the scheduler
      Given any valid expression
      When the preview endpoint returns the next runs
      Then each run matches what `compute_next_run` would fire
    ```

## Conflicts

None identified.

## Open Questions

None.
