---
title: "PR reviewer-feedback triage"
status: done
---

# Requirements: PR reviewer-feedback triage

## Overview

Reviewers leave a dozen comments on the pull requests the user authored, and the `handle-pr-reviewer-feedback` skill analyzes each one into a Markdown file under the user-global `~/.sdlc` store.
Those files carry the analysis, a recommended action, a suggested reply, and a suggested change, but nothing turns them into decisions.
This feature gives the app a triage queue over those files and records an implement, decline, or defer decision back into each file's frontmatter, which is the same contract the skill's executor consumes to carry the decisions out.
The app never touches GitHub: the decision, not this feature, queues the follow-up work.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Read every analyzed reviewer comment in one place and decide implement, decline, or defer without opening each thread |
| Coding agent | Read the triage queue through the API and find decided-but-not-executed items to carry out |
| Feedback skill and executor | Have decisions written in the frontmatter keys it already consumes |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall discover every reviewer-feedback analysis file matching `{owner}/{repo}/pull-requests/{number}/feedback/{id}.md` under the user-global store, skipping dotfiles and files without usable YAML frontmatter. |
| FR-2 | Must | Each item shall expose the frontmatter fields (feedback_id, kind, repo, pr, author, created_at, head_commit, analyzed_at, recommendation, confidence, session_link), the decision keys (decision, decided_at, executed_at), and the body's title and named sections, with timestamps normalized to ISO-8601 UTC. |
| FR-3 | Must | An item's status shall be its recorded decision, or pending when none is recorded; the presence of the analysis file itself means the comment is analyzed. |
| FR-4 | Must | An item's run state shall be executed when `executed_at` is set, awaiting when a decision exists without `executed_at`, and none otherwise, so decided-but-not-executed names exactly the work the executor still owes. |
| FR-5 | Must | The queue shall list undecided items first, grouped by repository and pull request, oldest comment first within a pull request. |
| FR-6 | Must | The listing shall overlay each item's pull request state (open or closed) from ghx through the shared metadata cache, leaving it unknown when the lookup fails or the store key has no owner; `refresh` bypasses the cache. |
| FR-7 | Must | Recording a decision shall write `decision` and `decided_at` into the file's frontmatter and leave `executed_at` alone, keeping the item in the awaiting state the executor consumes. |
| FR-8 | Must | Re-recording the same decision shall keep an existing `executed_at`; a changed decision or a reset shall drop a stale `executed_at` so the new decision is run. |
| FR-9 | Must | The decision endpoint shall accept only implement, decline, defer, or null as a reset; an unknown feedback id answers 404, and a file without frontmatter or one that cannot be re-read answers 422. |
| FR-10 | Must | The listing shall report counts of pending, implement, decline, defer, and awaiting-run items, and name the store root it scanned, or none when the store is missing. |
| FR-11 | Should | The web app shall show one card per item at `/feedback` with recommendation, confidence, kind, PR state, decision, and run-state pills, the sections with the first one open, a thread link, and a copyable suggested reply. |
| FR-12 | Should | The view shall filter by search, PR state, repository, author, status, recommendation, and execution state, group and sort the cards, and narrow the list to a group picked in the sidebar, with grouping and sorting remembered on the device. |
| FR-13 | Must | Frontmatter writes shall replace the file atomically, so a crash cannot leave it truncated. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Maintainability | The store module stays file-only (no FastAPI imports), and the router maps its errors to HTTP responses. |
| NFR-2 | Must | Data integrity | A decision lives in the analysis file itself, so the app and the skill's executor read one source of truth that sits outside any git repository. |
| NFR-3 | Must | Security | The app records decisions only and changes nothing on GitHub; the analysis files sit outside the served web tree. |
| NFR-4 | Should | Performance | PR state lookups reuse the shared ghx metadata cache across the feedback queue and the review queue. |

## Constraints

- The store is the user-global `AGENTIC_SDLC_DIR` tree the feedback skill writes; the app never creates, renames, or deletes analysis files.
- Decisions are exactly implement, decline, defer, or none; the skill's recommendation vocabulary (implement, reject, clarify, no-action) is advisory and separate from the decision.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Analysis files become queue items
      Given two analysis files for different pull requests and one editor temp file
      When the queue is read
      Then the two files are items and the dotfile is not
      When a file has no YAML frontmatter
      Then it is not an item and the rest of the queue is unaffected
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: An item carries the whole analysis
      Given an analysis file with frontmatter and Comment, Analysis, and Suggested reply sections
      When the item is read
      Then it carries the frontmatter fields, the title, and the sections in order
      And an unquoted decided_at reads back as an ISO-8601 UTC timestamp
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Pending until decided
      Given an analysis file with no decision key
      When the item is read
      Then its status is pending
      When the file exists at all
      Then the comment counts as analyzed
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: The run state tracks execution
      Given an item with a decision and no executed_at
      When it is read
      Then its run state is awaiting
      When executed_at is set
      Then its run state is executed
      And an item with no decision has run state none
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Undecided first
      Given decided and undecided items across two repositories
      When the queue is read
      Then the undecided items lead, grouped by repository and pull request, oldest comment first
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Live PR state
      Given an item whose pull request ghx reports as closed
      When the queue is read
      Then the item shows closed
      When the store key has no owner or ghx cannot be read
      Then the state is unknown and the item still renders
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: A decision is recorded
      Given a pending item
      When implement is recorded
      Then the file's frontmatter reads decision: implement with a decided_at
      And executed_at is still absent, leaving the item awaiting
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: Changing a decision requeues the work
      Given an executed item
      When a different decision is recorded
      Then the stale executed_at is dropped and decided_at is restamped
      When the same decision is recorded again
      Then the executed_at survives
      When the decision is reset to none
      Then decision, decided_at, and executed_at are all gone
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: Bad requests are rejected
      Given the decision endpoint
      When a decision outside implement, decline, or defer is sent
      Then the API rejects it with a validation error
      When an unknown feedback id is addressed
      Then the API answers 404
      When the file has no frontmatter
      Then the API answers 422
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: Counts and root
      Given pending, decided, and awaiting items
      When the queue is read
      Then the counts report each status and the awaiting-run total
      And the root names the scanned directory, or is empty when it does not exist
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: A card shows the decision surface
      Given an item with a recommendation, confidence, and sections
      When the feedback page renders
      Then the card shows the pills, the sections with Comment first, the thread link, and a copyable reply
      And pressing Implement records the decision on the card at once
    ```

- [ ] **FR-12**

    ```gherkin
    @FR-12
    Scenario: Narrowing the list
      Given items in several states and repositories
      When the status filter is set to pending and the search names one author
      Then only that author's pending items are listed
      And the grouping and sorting choices survive leaving the page
    ```

- [ ] **FR-13**

    ```gherkin
    @FR-13
    Scenario: A crash cannot truncate a file
      Given a decision write
      When it lands
      Then the file was written beside itself and replaced, never rewritten in place
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Store and router split
      Given the feedback store module
      When it is imported
      Then it pulls in no web framework, and the router alone raises HTTP errors
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: One source of truth
      Given a decision recorded by the app
      When the executor reads the same file
      Then it finds the same decision keys without any app-side database row
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: Nothing is posted to GitHub
      Given any triage action
      When it completes
      Then the only writes are decisions into local analysis files
    ```

- [ ] **NFR-4**

    ```gherkin
    @NFR-4
    Scenario: Shared cache
      Given a queue read right after the review queue fetched the same pull request
      When the feedback queue reads its PR states
      Then the cached ghx result is reused without a new lookup
    ```

## Conflicts

None identified.

## Open Questions

1. Two writers (the app and the executor) can touch one file at once and the last write wins; should decision writes take a lock or should the executor only own `executed_at`?
