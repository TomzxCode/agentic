---
title: "Review SLO"
status: draft
---

# Requirements: Review SLO

## Overview

Review requests can sit in the review queue for days without anything drawing attention to them.
The review scan already records when it first saw each pull request awaiting the user's review, but nothing turns that wait into a nudge.
This feature adds a **review SLO**: a duration the user sets, after which a pull request still awaiting their review is offered in the inbox.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Set how long a review may wait, and be told in the inbox when one goes past it |
| Coding agent | Read the SLO setting and the inbox suggestions through the API |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The user shall set a review SLO as a duration (`8h`, `1d`, `2d`), stored like the other app settings; an empty value shall turn the SLO off. |
| FR-2 | Must | A pull request the review scan found with a review requested from the user shall be offered in the inbox once its wait exceeds the SLO. |
| FR-3 | Must | The wait shall be measured from when the scan first saw the pull request awaiting a review, not from when the pull request was opened. |
| FR-4 | Must | Only pull requests still awaiting the user's review shall count: one they already reviewed, a draft, or one no longer open shall not be offered. |
| FR-5 | Must | The inbox suggestion shall name the pull request, state how long it has waited and the SLO, and link to it so the user can review it. |
| FR-6 | Must | The suggestion shall disappear on the next read once the pull request leaves the review queue (reviewed, closed, or dropped by a scan) or once the SLO is raised past its wait or turned off. |
| FR-7 | Must | The web app shall let the user set the SLO on the Review requests settings section and reject a malformed duration. |
| FR-8 | Should | The inbox shall show the review suggestions before the task suggestions, since a review waits on the user rather than on bookkeeping. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Data integrity | The feature shall add no table and no column: it reads the review scan's stored `first_seen_at` and the existing settings store. |
| NFR-2 | Should | Usability | The review suggestion and the SLO field shall stay legible and usable at phone widths. |
| NFR-3 | Should | Consistency | The SLO shall use the same duration grammar as the refresh policies and the review-scan cadence. |

## Constraints

- The review scan is the only source of "awaiting my review"; the SLO does not read the report store.
- Persistence is the existing `setting` table; the SLO is an overridable setting with an `AGENTIC_REVIEW_SLO` environment default.
- The inbox is recomputed on every read and stores nothing.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Set an SLO
      Given the Review requests settings section
      When the user saves "1d" as the review SLO
      Then the setting reads back "1d" as its effective value
      And a blank value turns it off
    ```

- [ ] **FR-2 / FR-3**

    ```gherkin
    @FR-2 @FR-3
    Scenario: A review goes past the SLO
      Given a review SLO of one day
      And a pull request the scan first saw awaiting my review two days ago
      When the inbox is read
      Then the pull request is offered as a review past the SLO
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Only reviews still waiting count
      Given a pull request I already reviewed, a draft, and a merged pull request
      When the inbox is read
      Then none of them is offered as a review past the SLO
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: The suggestion says why it is there
      Given a pull request past the review SLO
      When the inbox shows it
      Then it names the pull request and its repository
      And it states the wait and the SLO
      And it links to the pull request on GitHub
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: The review happens
      Given a pull request offered as past the review SLO
      When the next scan no longer finds it awaiting my review
      Then the suggestion is gone on the next inbox read
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: A malformed SLO is rejected
      Given the Review requests settings section
      When the user saves "soon" as the review SLO
      Then the API rejects it with a validation error naming review_slo
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: Reviews lead the inbox
      Given a task to close and a pull request past the review SLO
      When the inbox is shown
      Then the review suggestion is listed before the task suggestion
    ```

## Conflicts

- The SLO counts only reviews requested from the user, while the review queue also keeps pull requests the user already reviewed until they close. The queue stays a working list; the inbox only nudges on reviews still owed.

## Open Questions

1. Should the SLO be per repository, so a noisy repository can have a longer deadline?
2. Should the review queue itself mark a row past its SLO, not only the inbox?
3. Should a pull request past its SLO be assigned to a task and a review run automatically?
