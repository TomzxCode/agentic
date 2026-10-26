---
title: "Agent sessions, session links, and managed tools"
status: done
---

# Requirements: Agent sessions, session links, and managed tools

## Overview

A task is worked on across several agent sessions, some started by agentic runs and some started elsewhere, for example in OpenChamber.
This feature records every session a task was worked in (runs record their own; a user attaches the rest), and renders the links that reopen each one in OpenChamber, a terminal, or a resumed command.
Because the ghx and slackx helper CLIs serve both a web UI and the JSON-RPC endpoint the app calls, the server can also run them itself: a tool whose transport is `managed` starts with the API, answers on a fixed loopback port, and stops with the API.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Task author | Reopens any session of a task with one click or one copied command |
| Operator | Decides per tool whether the CLI spawns it, points at a server they run, or lets the API manage it |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall record an agent session against a task (session id, optional harness, label, working directory) and shall list a task's recorded sessions newest first. |
| FR-2 | Must | A recorded session's harness shall default to the task's harness, and an explicit harness id shall be rejected with 404 when no such harness exists. |
| FR-3 | Must | The system shall update a recorded session's label, working directory, and harness, and shall remove the record without touching the underlying agent session; every change shall append a timeline entry and notify live task views. |
| FR-4 | Must | Deleting a task shall delete its recorded sessions, and deleting a harness shall detach its recorded sessions instead of deleting them. |
| FR-5 | Must | The system shall build reopen links for any run or recorded session that has a session id: an OpenChamber URL from the configured base and session path, a terminal URL from the configured template, and a copyable resume command from the harness's resume command template. |
| FR-6 | Must | Link templates shall substitute `{session}`, `{cwd}`, and `{harness}`, and the resume command shall be prefixed with `cd <cwd> &&` when a working directory is known. |
| FR-7 | Should | A link shall appear only when its target is configured, and a run or session without a session id shall carry no links. |
| FR-8 | Should | The CLI shall offer `agentic session list`, `get`, `add`, `update`, and `remove` for a task's sessions. |
| FR-9 | Should | The task page shall show a Sessions panel listing each session's label, harness, session id, working directory, reopen links, and a remove action. |
| FR-10 | Must | For a tool whose transport is `managed`, the server shall start `<tool> serve` bound to loopback (ghx on 8080, slackx on 8280) when the API starts and stop it when the API stops, and shall supply that process's JSON-RPC endpoint (`<serve url>/rpc`, no token) to callers. |
| FR-11 | Must | Each tool's transport shall be resolved per call as the stored Settings value over the environment value, with a blank stored value meaning no opinion, so a change applies without a restart. |
| FR-12 | Must | `AGENTIC_MANAGED_TOOLS` shall manage both tools, while an explicit `rpc` transport for a tool shall keep pointing at the user's own server even when the flag is set. |
| FR-13 | Should | Saving a transport change shall start or stop the tool's serve process immediately, and Settings shall offer a restart control that replaces the running process (409 for a tool this server does not run). |
| FR-14 | Should | The Settings page shall show URL and token fields only for the `rpc` transport, and a managed tool's web UI address as a link (the stored URL if set, else the serve URL) instead of a field. |
| FR-15 | Should | A GitHub or Slack item shall link into the ghx or slackx web UI when the matching server URL is configured. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Security | Managed tool processes shall bind to loopback only, so no token is needed and the endpoint is unreachable off-machine. |
| NFR-2 | Must | Availability | A tool that cannot start shall be logged and skipped without blocking API startup, and a wedged process shall be killed after a 5 s grace period. |
| NFR-3 | Should | Operability | Restarting a managed tool shall replace its process and report whether it came back up. |
| NFR-4 | Must | Data integrity | Recorded sessions shall survive harness deletion and shall be deleted with their task. |
| NFR-5 | Should | Usability | Removing a session record shall never delete the session itself, and the panel shall say so in its confirmation. |

## Constraints

- Links are rendered at read time from the current settings, so changing a template changes the links of past sessions too.
- A recorded session is a pointer; the app does not verify that the session id exists on the harness.
- The ghx and slackx web UI routes are the tools' own; this app only starts, stops, and links them.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: A session is attached to a task
      Given a task
      When a session with an id, a label, and a cwd is attached
      Then the session is recorded and listed newest first for that task
      And the task timeline records "session_added"

    @FR-1
    Scenario: An empty session id is rejected
      Given a task
      When a session with a blank session id is attached
      Then the request fails with 400
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: The harness defaults to the task's
      Given a task with a harness and an attached session with no harness
      When the session is read
      Then its harness is the task's harness
      When a session names a harness that does not exist
      Then the request fails with 404
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: A session record is updated and removed
      Given a recorded session
      When its label and cwd are updated
      Then the change is visible, the timeline records "session_updated", and live task views are notified
      When the session record is removed
      Then only the record is gone, the timeline records "session_removed", and the underlying session is untouched
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Sessions follow task and harness deletion
      Given a recorded session on a harness
      When the task is deleted
      Then the session record is deleted with it
      When the harness is deleted instead
      Then the session record remains with no harness id
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Reopen links are built
      Given an OpenChamber base, a terminal template, and a harness with a resume command
      When a run or recorded session with a session id is read
      Then it carries an "Open in OpenChamber" link, an "Open in terminal" link, and a resume command
      And the resume command reads "cd <cwd> && <command>"
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Templates substitute their placeholders
      Given templates containing {session}, {cwd}, and {harness}
      When links are built for a session
      Then each placeholder is replaced with the session's values
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Unconfigured targets produce no links
      Given no OpenChamber base, terminal template, or resume command
      When a session with a session id is read
      Then it carries no links
      When a run or session without a session id is read
      Then it carries no links either
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: CLI session commands
      Given a running API
      When agentic session list, get, add, update, and remove run
      Then each prints the outcome and the recorded sessions reflect it
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: The task page lists sessions
      Given a task with recorded sessions
      When the task page is opened
      Then the Sessions panel shows each session's label or id, harness chip, cwd, reopen links, and a Remove button
      And removing asks for confirmation first
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: A managed tool runs with the server
      Given ghx's transport is managed
      When the API starts
      Then ghx serve is started on 127.0.0.1:8080
      And callers are given http://127.0.0.1:8080/rpc with no token
      When the API stops
      Then the ghx process is stopped
    ```

    ```gherkin
    @FR-10
    Scenario: Each tool uses its own port
      Given slackx's transport is managed
      When the API starts
      Then slackx serve is started on 127.0.0.1:8280
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: A stored transport wins over the environment
      Given the environment's transport is cli and Settings store rpc or managed
      When the transport is resolved
      Then the stored value wins
      When the stored value is blank
      Then the environment's value applies
    ```

- [ ] **FR-12**

    ```gherkin
    @FR-12
    Scenario: The all-tools flag respects an explicit rpc
      Given AGENTIC_MANAGED_TOOLS is set
      When a tool's transport is cli
      Then that tool is managed
      When a tool's transport is rpc
      Then that tool keeps pointing at the user's own server
    ```

- [ ] **FR-13**

    ```gherkin
    @FR-13
    Scenario: Transport changes apply immediately
      Given a managed tool running
      When the transport is saved as cli
      Then the serve process is stopped without a restart
      When the restart control is used for a managed tool
      Then the process is replaced and the response says whether it came back
      When the restart control is used for a tool this server does not run
      Then the request fails with 409
    ```

- [ ] **FR-14**

    ```gherkin
    @FR-14
    Scenario: The tool settings show the right fields
      Given the Settings page's local tools section
      When a tool's transport is rpc
      Then URL and token fields are shown
      When a tool's transport is managed
      Then its web UI address is a link, falling back to the serve URL when none is stored
    ```

- [ ] **FR-15**

    ```gherkin
    @FR-15
    Scenario: Items link into the tool UIs
      Given a ghx_url and a slackx_url are configured
      When a GitHub issue and a Slack thread item are rendered
      Then each carries a link into the matching tool's web UI at the item's page
      And an item without a parseable GitHub or Slack target carries none
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Managed tools bind loopback only
      Given a tool is started in managed mode
      Then its serve command pins --host 127.0.0.1
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: A missing binary does not block startup
      Given a managed tool whose binary is not installed
      When the API starts
      Then the failure is logged, the API starts, and the tool has no endpoint
      When a managed process ignores termination
      Then it is killed after a 5 s grace period
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: Restart replaces the process
      Given a managed tool is running
      When it is restarted
      Then the old process is stopped, a new one is started, and the outcome is reported
    ```

- [ ] **NFR-4**

    ```gherkin
    @NFR-4
    Scenario: Session records track their owners
      Given recorded sessions on a harness
      When the harness is deleted
      Then the session records remain with no harness id
      When the task is deleted
      Then the session records are deleted with it
    ```

- [ ] **NFR-5**

    ```gherkin
    @NFR-5
    Scenario: Removal never deletes the session
      Given a recorded session
      When Remove is used in the panel
      Then the confirmation says the session itself is untouched
      And declining the confirmation changes nothing
    ```

## Conflicts

None identified.

## Open Questions

None. The implemented code answers every question this document raises.
