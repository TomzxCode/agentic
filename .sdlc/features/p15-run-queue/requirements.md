---
title: "Durable agent-run queue and worker"
status: done
session_link: "http://localhost:10000/?session=ses_ecf740bfcffeTbPo9DIeiSPyDH"
---

# Requirements: Durable agent-run queue and worker

## Overview

Agent runs used to be in-process asyncio tasks, so an API restart dropped every run and left its row `running`.
This feature moves runs onto a job queue (SAQ) processed by a separate worker process, so a run survives an API restart and a worker crash can be retried.
The default backend is SQLite, keeping the app single-binary and local-first.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Start a run, restart the app, and still have the run finish |
| Coding agent | Pick up a queued run as a self-contained job |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall persist each agent run as a job on a queue instead of running it as an in-process task. |
| FR-2 | Must | A worker process (`agentic-server worker`) shall dequeue jobs and execute the run (chat, context refresh, or Slack summary). |
| FR-3 | Must | The default queue backend shall be SQLite in the data directory, needing no external service; `AGENTIC_QUEUE_URL` shall override it with a `sqlite://`, `redis://`, or `postgres://` URL. |
| FR-4 | Must | Cancelling a run shall abort its job: a still-queued job is aborted before it starts, and an active turn is cancelled. |
| FR-5 | Must | On API startup the system shall fail queued/running runs whose job is absent or already terminal, so a dropped run never hangs visibly. |
| FR-6 | Should | A run whose worker died shall be retried once its heartbeat lapses. |
| FR-7 | Should | A worker shall process several runs concurrently, configurable with `AGENTIC_WORKER_CONCURRENCY`. |
| FR-8 | Should | The worker and the API shall be startable independently, sharing the same queue. |
| FR-9 | Must | The system shall record a run's harness session id as soon as the session exists, not only when the turn ends, so an interrupted run leaves a resumable handle. |
| FR-10 | Must | A retried run shall resume the session it recorded instead of starting a new one, and shall fall back to a new session when the recorded one cannot be resumed. |
| FR-11 | Must | The SSE streams (run transcript and task changes) shall reflect writes made by the worker in another process, not only events raised by the API process. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Operability | The default deployment shall need no service beyond the app's own data directory. |
| NFR-2 | Must | Data integrity | The queue shall live in its own SQLite file, so the application schema is unchanged. |
| NFR-3 | Should | Reliability | A killed worker shall not leave a run running forever. |

## Constraints

- SAQ is pinned to the `tomzxforks/saq` fork, `dev` branch, `saq[sqlite]` extra.
- The queue and the application database are separate SQLite files.
- Single-user, local-first; no authentication.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: A run is enqueued, not started in-process
      Given a task
      When the user starts a run
      Then the run row is created as "queued"
      And a job keyed by the run id exists on the queue
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: A worker executes a queued run
      Given a queued run
      When a worker processes the queue
      Then the run reaches a terminal status
      And the task is updated by the run's executor
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: The default queue needs no external service
      Given no AGENTIC_QUEUE_URL
      Then the queue uses <data_dir>/queue.db
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Cancelling a queued run
      Given a queued run that no worker has started
      When the user cancels it
      Then the job is aborted
      And the run's status is "cancelled"
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: A run with no job is failed on startup
      Given a run left "running" with no active job
      When the API starts
      Then the run is failed with an interruption reason
      And a run whose job is still active is left alone
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: A dead worker's run is retried
      Given a job whose worker stopped heartbeating
      When a worker sweeps the queue
      Then the job is retried (or aborted once retries are exhausted)
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: The session is recorded before the turn finishes
      Given a running agent turn
      When a session has been created
      Then the run's session id is stored
      And a crash leaves that handle behind
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: A retried run resumes its session
      Given an interrupted run with a recorded session id
      When the job is retried
      Then the same session is resumed and the turn continues
      And if the session cannot be resumed a new one is started
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should the worker also run inside the API process for a zero-extra-process dev setup, given SAQ's worker installs signal handlers?
2. Should agent runs use retries beyond the single recovery attempt?
