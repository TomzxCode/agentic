---
title: "Agent runs and context refresh"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: Agent runs and context refresh

## Overview

This feature drives coding agents and keeps a task's context current.
It manages harnesses (any ACP-compatible agent), runs a prompt in a working directory with a live, persisted transcript, supports cancellation, refreshes a task's summary and next steps by asking an agent to summarize, and builds links to reopen the resulting session.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Ask an agent to work on a task and watch it happen; come back to a current summary |
| Coding agent | Run in the right directory with the task's context |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall seed default harnesses (`opencode2`, `opencode`, `pi`), adding any missing preset on startup without overwriting existing rows, report whether each is on `PATH`, and mark one as the default (installed `opencode2` when present, else `opencode`). |
| FR-2 | Must | The system shall create, update, and delete harnesses (command, args, env, model, resume command, default flag), keeping at most one default and letting the default be changed from the web UI. |
| FR-3 | Must | The system shall create an agent run, resolving the working directory from an explicit path, a worktree, the newest active worktree, the first task repository, or the worktree root, in that order. |
| FR-4 | Must | The system shall run the harness over ACP, normalize each update into an agent event, persist it, and stream it over SSE. |
| FR-5 | Must | The system shall cancel a running agent run. |
| FR-6 | Must | The system shall refresh a task's context by building a prompt from the task and its items, running it, parsing a JSON `{summary, next_steps}` object, and storing the result. |
| FR-7 | Must | The system shall build session links for a run that produced a session: an OpenChamber URL, a terminal URL, and a copyable resume command. |
| FR-8 | Must | The system shall read and update session-link settings, where stored overrides win over environment defaults. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Reliability | A failed run shall be marked failed and publish an error event rather than crash the server. |
| NFR-2 | Must | Reliability | The harness process shall be terminated after a prompt turn completes, because it otherwise stays alive until stdin closes. |
| NFR-3 | Should | Performance | Blocking calls shall run off the event loop so streaming stays responsive. |
| NFR-4 | Should | Security | Permission requests shall be auto-approved by default, which is safe only on a trusted single-user machine. |

## Constraints

- Only updates of type `message` are parsed for context; `thought` chunks are used only if the agent said nothing, because consolidating tool output is unreliable.
- The harness must be reachable over ACP on `PATH`.
- Runs are in-process; restarting the API drops in-flight runs.

## Acceptance Criteria

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Resolve the working directory
      Given a task with an active worktree
      When the user starts a run without a cwd
      Then the run uses the newest active worktree path
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Change the default harness
      Given several harnesses
      When the user marks one as the default
      Then that harness is the only one marked default
      And a run that does not pick a harness uses it
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Parse a truncated context payload
      Given an agent reply with a JSON object cut off before its closing braces
      When the context refresh parses the reply
      Then the summary and next steps are still extracted
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Build session links
      Given a run with a session id and an OpenChamber base URL configured
      When the run is read
      Then it includes an OpenChamber link, and a resume command when the harness has one
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: Terminate the harness after a turn
      Given a run whose prompt turn completed
      When the run finishes
      Then the harness process is terminated within the wait timeout
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should permission requests become interactive instead of auto-approved?
2. Should context refresh run automatically after a run completes?
