---
title: "Inbox: derived suggestions"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: Inbox: derived suggestions

## Overview

Work leaves loose ends: a task whose pull requests all merged while its status is still open, a merged pull request with no change record, a worktree left behind by a finished task, a review that sat past its service level objective.
The Inbox is a short decision queue of those loose ends, recomputed from the current state on every read.
It stores nothing: a suggestion is derived from tasks, their linked items and changes, their worktrees, the review requests the scan found awaiting the user, and the user's own unreviewed pull requests.
Acting on a suggestion changes that state, so the suggestion disappears on the next read instead of needing to be dismissed.
The SPA shows the suggestions at `/inbox`, grouped into six sections, with the actions each suggestion offers.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | See the few decisions the current state implies, and act on each with one click |
| Coding agent | Read `GET /api/inbox` for the same suggestions and act through the existing endpoints |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall return the suggestions from `GET /api/inbox` ordered by kind rank (review past SLO, poke reviewers, find a reviewer, close finished tasks, record changes, clean up worktrees), keeping the newest task first within each kind. |
| FR-2 | Must | The system shall offer to close an open task (not done or archived) that links at least one GitHub issue or pull request when every linked item is closed or merged, with a `Close task` action that sets the task status to done. |
| FR-3 | Must | The system shall offer to record a change for each merged pull request linked to a task that no change references yet, skipping archived tasks and, when the viewer's GitHub login is known, pull requests the viewer did not author. |
| FR-4 | Must | The system shall offer to remove each active worktree of a done or archived task. |
| FR-5 | Should | The system shall offer to review each pull request the scan found requested from the user that has waited past the configured review SLO, counting the wait from when the scan first saw it and skipping drafts and pull requests no longer open. |
| FR-6 | Should | The system shall offer to poke the reviewers of each of the user's own open pull requests that nobody but the author has reviewed past the configured nudge SLO, counting the wait from when the pull request was opened: a `poke_pr_no_reviews` suggestion lists the requested reviewers GitHub still reports, one row each with its own poke action, and a pull request nobody was asked to review goes in a separate `find_pr_reviewer` suggestion instead, since there is no one to poke. Both offer `Open PR`, the app's PR page. |
| FR-7 | Must | The system shall store nothing about suggestions, so a suggestion disappears as soon as the action it offers (or any other change) removes the state it was derived from. |
| FR-8 | Should | The Inbox page shall group the suggestions into six fixed sections, execute each action kind through the matching endpoint (a reviewer poke included), and reload the inbox after each action. |
| FR-9 | Should | The Inbox page shall disable the action buttons while an action is in flight, and record a change as already accepted and dated to the pull request's merge time, refreshing the item once when its merge time is unknown. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Maintainability | The suggestion rules shall be pure, database-free functions that take already-loaded rows, so they are unit-testable without a database. |
| NFR-2 | Should | Performance | The endpoint shall load each table once and compute in process, and reuse the My PRs page's shared, briefly cached read for the nudge suggestions. |
| NFR-3 | Must | Robustness | A failed GitHub read shall render the inbox without the poke suggestions rather than with stale guesses, and naive stored timestamps shall be read as UTC. |

## Constraints

- Suggestions are computed on read; the inbox has no table, no dismissal state, and no API to mutate it directly.
- Actions reuse the existing endpoints (task update, change create, worktree remove, My PRs poke) rather than inbox-specific ones.
- The close and record-change heuristics only consider GitHub issues and pull requests linked to tasks.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Suggestions are ordered by kind
      Given a done task with an active worktree and an open task with a merged pull request
      When the inbox is read
      Then the close suggestion precedes the record-change suggestion, which precedes the worktree suggestion
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: A task whose linked items are all finished is offered for closing
      Given an open task linked to one merged pull request
      When the inbox is read
      Then a "close_task_finished_items" suggestion names the task with reason "PR o/r#5 is merged."
      And its action sets the task status to done

    @FR-2
    Scenario: A task with no linked GitHub item is left alone
      Given an open task linked only to a note item
      When the inbox is read
      Then no suggestion names the task
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: A merged pull request with no change is offered for recording
      Given an open task linked to a merged pull request and no change row
      When the inbox is read
      Then a "record_change_merged_pr" suggestion offers to create a change

    @FR-3
    Scenario: A recorded change suppresses the offer
      Given the same task with a change whose external ref matches the pull request
      When the inbox is read
      Then only the close suggestion remains

    @FR-3
    Scenario: Another author's pull request is not the viewer's change to record
      Given a configured GitHub login and a merged pull request authored by someone else
      When the inbox is read
      Then the close suggestion stays and the record-change suggestion is hidden
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: A closed task keeps a worktree suggestion until the worktree is removed
      Given a done task with an active worktree
      When the inbox is read
      Then a "remove_worktree_done_task" suggestion offers to remove it
      And a removed worktree produces no suggestion
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: A pull request past the review SLO is suggested
      Given a review SLO of 1 day and a requested review first seen 2 days and 3 hours ago
      When the inbox is read
      Then a "review_pr_past_slo" suggestion reports the wait and the SLO with a "Review PR" link

    @FR-5
    Scenario: Reviewed, draft, and merged pull requests are left alone
      Given requests the scan marked reviewed, a draft, and one merged
      When the inbox is read
      Then none of them produces a review suggestion
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: An unreviewed pull request with requested reviewers lists them to poke
      Given a nudge SLO of 1h 30m and the user's own pull request opened 2 days ago with two requested reviewers
      When the inbox is read
      Then a "poke_pr_no_reviews" suggestion carries the two reviewer logins and offers "Open PR"
      And its row lists one reviewer per requested login, each with a poke action

    @FR-6
    Scenario: An unreviewed pull request nobody was asked to review goes in its own section
      Given a nudge SLO of 1h 30m and the user's own pull request opened 2 days ago with no requested reviewer
      When the inbox is read
      Then a "find_pr_reviewer" suggestion reports that no reviewer is requested and offers only "Open PR"

    @FR-6
    Scenario: No threshold configured means no pokes
      Given no review nudge SLO
      When the inbox is read
      Then no poke suggestion appears
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Acting on a suggestion removes it
      Given an inbox listing a close suggestion for a task
      When the task is closed through the offered action and the inbox is read again
      Then the close suggestion is gone
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: The page groups and executes suggestions
      Given the API returned a close suggestion
      When the Inbox page renders and the user clicks its button
      Then the task update endpoint is called and the page reloads the inbox
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: Recording a change uses the stored merge time
      Given a record-change suggestion whose item already carries merged_at
      When the user clicks "Record change"
      Then the change is created accepted with external_ref set to the pull request URL
      And the item refresh endpoint is not called
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: A failed GitHub read keeps the rest of the inbox
      Given the My PRs read fails
      When the inbox is read
      Then the response still carries the other suggestions and no poke suggestions
    ```

## Conflicts

None identified yet.

## Open Questions

None.
