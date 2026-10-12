---
title: "Factory metrics: autonomy rate and yield"
status: done
revision: 1
session_link: "http://localhost:10000/?session=ses_ed20dd7b7ffeRNOIfPEWqJEfmH"
---

# Requirements: Factory metrics: autonomy rate and yield

## Overview

This feature instruments the change lifecycle and computes the two primary factory metrics from the article "Metrics for a Software Factory": autonomy rate and yield.
It also stores a baseline per metric and reports whether each metric is improving, worsening, or flat relative to that baseline.
Autonomy rate answers "how much of the work reached production without me touching it"; yield answers "how much of what reached production survived".
The two multiply into the rate of trustworthy unattended work, which is the number the factory exists to raise.

The foundation is metric-agnostic: a change is recorded with an id, a start, an end, and a human-intervened flag, and the metric engine derives values from those records.
Autonomy rate and yield are the first two metrics; cost per accepted change, human minutes per accepted change, and queue depth are deliberately out of scope for this iteration.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Know whether autonomy and yield are improving or worsening, per the article's paired OKR |
| Coding agent | Record and resolve the changes it produces so the metrics have data |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall record a change as a unit of factory output, linked to a task, with a title, a change class (feature, bugfix, refactor, chore, docs, test, trivial), a lifecycle status, an optional repository, an optional worktree, an optional external reference, and start/end timestamps (`opened_at`, `verified_at`, `accepted_at`, `closed_at`). |
| FR-2 | Must | The system shall record human interventions against a change (question, correction, manual fix, rerun, approval, other) and mark the change as human-intervened when at least one is recorded, including an approval. |
| FR-3 | Must | The system shall transition a change through its lifecycle (proposed, verified, accepted, rejected, reverted) and stamp the timestamp for the transition (`verified_at` on verify, `accepted_at` on accept, `closed_at` on reject or revert). |
| FR-4 | Must | The system shall compute autonomy rate as the share of accepted changes that had no human intervention. |
| FR-5 | Must | The system shall compute yield as the share of accepted changes that survived the observation window without being reverted. |
| FR-6 | Must | The system shall compute both metrics over a configurable window and exclude changes still inside the observation window from yield. |
| FR-7 | Must | The system shall store a baseline per metric and report the direction of each metric (improving, worsening, flat, no-baseline, no-data) relative to its baseline. |
| FR-8 | Must | The system shall expose changes, interventions, metrics, and baselines over HTTP and through the CLI. |
| FR-9 | Should | The system shall show a task's changes on its page, where they are recorded and moved through their lifecycle, and shall show autonomy rate and yield, their baselines, directions, and the recent changes on a Metrics page in the SPA. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Correctness | The metric formulas shall be pure functions so equal inputs produce equal outputs and can be unit-tested directly. |
| NFR-2 | Should | Performance | Metrics shall be computed in process from SQLite and stay responsive for thousands of changes. |
| NFR-3 | Should | Reliability | Deleting a task or a change shall also delete its interventions so no orphan rows remain. |
| NFR-4 | Should | Usability | The Metrics page shall remain usable and legible at phone widths. |
| NFR-5 | Should | Security | Metrics shall be computed over the whole store, never per person, matching the article's rule against individual measurement. |

## Constraints

- Persistence is SQLite via SQLModel; new tables are created by `create_all` and new columns are added in `db._ensure_columns()`.
- A change always belongs to exactly one task; a task may have zero or more changes.
- The observation window defaults to 14 days and the reporting window defaults to 30 days, both overridable per request.
- Direction is derived from a stored baseline; without a baseline the metric reports `no-baseline`.
- Metric requests may filter by task or change class, but the filter selects a work scope, never an individual person; the store has no per-person dimension (NFR-5).

## Acceptance Criteria

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Accept a change and stamp its time
      Given a change in the proposed state
      When the change is accepted
      Then its status is accepted and its accepted_at timestamp is set
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Compute autonomy rate
      Given two changes accepted inside the reporting window, one with a recorded intervention
      When autonomy rate is computed
      Then it is 0.5
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: A reverted change lowers yield
      Given two changes accepted inside the reporting window and observed past the observation window, one later reverted
      When yield is computed
      Then it is 0.5
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Exclude a change still inside the observation window
      Given one accepted change older than the observation window and one accepted inside it
      When yield is computed
      Then the older change is reflected in the yield and the newer one is reported as pending observation
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Direction against a baseline
      Given an autonomy baseline of 0.2 and a current autonomy rate of 0.5
      When the metric is reported
      Then its direction is improving
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Deterministic computation
      Given the same set of changes, window, and observation window
      When the metric is computed twice
      Then both results are equal
    ```

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Record a change
      Given a task
      When a change is recorded with a title and a change class
      Then it is stored in the proposed state with an opened_at timestamp
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: An intervention marks the change
      Given a change with no interventions
      When an intervention of kind correction is recorded
      Then the change is marked human-intervened with an intervention count of one
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: No baseline
      Given an autonomy rate of 0.5 and no stored baseline
      When the metric is reported
      Then its direction is no-baseline
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: Read metrics over HTTP
      Given recorded accepted changes
      When a client requests the metrics endpoint
      Then the response contains autonomy rate and yield with their counts
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: Record a change from the task page
      Given a task
      When the user records a change on the task's Changes panel
      Then the change appears on the task and counts toward the metrics

    @FR-9
    Scenario: Open the metrics page
      Given the SPA is served
      When the user navigates to the Metrics page
      Then autonomy rate and yield are shown with their direction
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: Deleting a task removes its changes
      Given a task with a change and an intervention
      When the task is deleted
      Then the change and its intervention no longer exist
    ```

- [ ] **NFR-4**

    ```gherkin
    @NFR-4
    Scenario: Metrics page at phone width
      Given a viewport narrower than 760 pixels
      When the Metrics page is shown
      Then the metric cards and the changes table remain legible without horizontal scrolling
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should the system auto-create a change when an agent run starts, or is explicit recording enough for the first iteration?
2. Should a change's class default from the task's tags, or is an explicit class always required?
3. Should yield also count changes rejected at verification, on top of changes reverted after acceptance?
