---
title: "Create a task from a Slack thread"
status: draft
session_link: "http://localhost:10000/?session=ses_ecf740bfcffeTbPo9DIeiSPyDH"
---

# Requirements: Create a task from a Slack thread

## Overview

A task is usually created from a title the user types, or imported from a GitHub issue or PR.
A discussion that lives in Slack has no such title, and copying its gist by hand is tedious.
This feature lets the user paste a Slack thread URL to create a task: the app gathers the conversation with `slackx`, associates it as a source item, and delegates to an agent to name the task and summarize the discussion.
It mirrors the GitHub import (`TaskCreate.github_url`) but adds the agent step, because a Slack thread has no ready-made title or body.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Turn a Slack discussion into a tracked task without writing the title or summary by hand |
| Coding agent | Be handed the thread and asked for a title and a summary in a machine-readable form |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall accept a `slack_url` when a task is created; when given, it shall fetch the thread with `slackx` and associate it as a `slack` source item. |
| FR-2 | Must | The system shall delegate to an agent run that reads the gathered thread and returns a title and a summary of the discussion. |
| FR-3 | Must | The system shall write the agent's title onto the task when the user supplied no title, and write the agent's summary as the task's summary; a user-supplied title is kept and only the summary is written. |
| FR-4 | Must | The delegation shall be asynchronous: the create request shall return without waiting for the agent, and the task shall update when the run finishes, announced over SSE like a context refresh. |
| FR-5 | Must | The web app's new-task form shall accept a pasted GitHub issue/PR URL or Slack thread URL in a single import field and create the task from it, detecting the source. |
| FR-6 | Should | The CLI shall accept `agentic task create --slack-url` and forward it to the API. |
| FR-7 | Should | A fetch or parse failure shall not fail task creation; the run shall record the failure on the task's timeline. |
| FR-8 | Should | The task's timeline shall record both the request for a title and summary and the outcome. |
| FR-9 | Must | The system shall mark agent runs left `queued` or `running` by a previous process as failed on startup, so a dropped run never hangs visibly forever. |
| FR-10 | Should | The system shall let a task imported from Slack re-dispatch its naming and summarizing run, so a failed or interrupted import can be retried without recreating the task. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Integration | Slack fetching shall reuse the existing `slackx` item fetch; no new dependency or CLI is introduced. |
| NFR-2 | Must | Data integrity | The feature shall reuse existing `Task` and `AgentRun` rows; no new table or column is introduced. |
| NFR-3 | Should | Consistency | A task created from a Slack URL shall always carry a non-empty title, even before the agent run finishes. |
| NFR-4 | Should | Usability | The Slack URL field shall stay usable and legible at phone widths, per the project's mobile-first design. |

## Constraints

- Persistence is SQLite through SQLModel; the `Task.title` and `Task.summary` columns already exist, so no schema change is required.
- The ACP harness abstraction is unchanged; the delegation is a normal `AgentRun` with a new `kind`.
- `slackx` must be installed and authenticated for the fetch to succeed; its absence is not fatal to task creation.
- No authentication; the app assumes a trusted, single-user environment.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Create a task from a Slack URL
      Given a valid Slack thread URL
      When the user creates a task with that slack_url
      Then the thread is fetched and associated as a slack source item on the task

    @FR-1
    Scenario: A non-Slack URL is not treated as a Slack thread
      Given no github_url and no slack_url
      When the user creates a task with no title
      Then the response is 400
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Delegate naming and summarizing to an agent
      Given a task created from a Slack URL
      When the create response is returned
      Then a summarize_slack agent run exists for the task
      And its prompt contains the gathered conversation
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: The agent names an untitled task and summarizes it
      Given a task created from a Slack URL with no title
      When the agent replies with {"title": "Fix ingest", "summary": "They agreed to fix it."}
      Then the task's title is "Fix ingest"
      And the task's summary is "They agreed to fix it."

    @FR-3
    Scenario: A user-supplied title is kept
      Given a task created from a Slack URL with the title "My title"
      When the agent replies with a different title and a summary
      Then the task's title stays "My title"
      And the task's summary is the agent's summary
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Creation does not wait for the agent
      Given a harness that takes a long time to answer
      When the user creates a task from a Slack URL
      Then the response is 201 with a placeholder title
      And the title and summary are written when the run finishes
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Create from the web UI
      Given the new-task form
      When the user pastes a Slack thread URL into the import field and creates the task
      Then the task is created with that slack_url
      And the form is enabled on a Slack URL alone

    @FR-5
    Scenario: Import a GitHub issue from the same field
      Given the new-task form
      When the user pastes a GitHub issue URL into the import field
      Then the title and description are prefilled from the issue
      And the task is created with that github_url
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Create from the CLI
      Given a Slack thread URL
      When the user runs `agentic task create --slack-url <url>`
      Then the request body carries slack_url and a task is created
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: An unparseable reply is recorded, not fatal
      Given a task created from a Slack URL
      When the agent reply has no usable JSON
      Then the task still exists with its placeholder title
      And a summary_failed timeline event is recorded
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: A run dropped by a restart is marked failed
      Given a run left in the running state by a previous server process
      When the server starts
      Then the run is failed with the reason "Interrupted by a server restart"
      And it is not left running
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: Retry the naming and summarizing run
      Given a task with an associated Slack thread
      When the user retries the naming and summarizing
      Then a new summarize_slack run is dispatched with the thread
      And a task without a Slack thread is rejected with 400
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: A Slack task always has a title
      Given the fetched thread has no usable title
      When the task is created from its Slack URL
      Then the task carries the placeholder title until the agent names it
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should a later context refresh replace a summary written by this import, or should the import only fill it when empty?
2. Should the agent also infer a description or next steps, or is a title plus summary enough?
3. Should re-pasting an already-imported Slack URL refresh the summary, or leave the existing task untouched?
