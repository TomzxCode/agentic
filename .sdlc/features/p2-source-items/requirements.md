---
title: "Source items, associations, and GitHub import"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: Source items, associations, and GitHub import

## Overview

Work is fed by external context: Slack threads, GitHub issues and pull requests, Google Drive docs, generic URLs, and plain notes.
This feature stores each piece of context as a source item, infers its source from the pasted value, fetches its content on demand, associates items to tasks many-to-many, and supports creating a task directly from a GitHub issue or PR.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Capture context quickly by pasting a link or text; see it on the task |
| Coding agent | Read the associated content to keep context current |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall create an item, inferring its source, kind, and external id from the URL or text when the caller does not supply them. |
| FR-2 | Must | The system shall treat text that is not a URL as a note and store it as content rather than as a link. |
| FR-3 | Must | The system shall deduplicate items by source plus external id, or by URL. |
| FR-4 | Must | The system shall fetch an item's title and content on demand (GitHub via `ghx`, Slack via `slackx`, other URLs via HTTP). |
| FR-5 | Must | The system shall associate and unassociate an item with a task, with an optional note, and record the change in the timeline. |
| FR-6 | Must | The system shall list, read, update, refresh, and delete items. |
| FR-7 | Must | The system shall create a task from a GitHub issue or PR URL, prefilling the title and description and associating the issue. |
| FR-8 | Should | The system shall list a repository's open issues via `ghx` for the import picker. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Reliability | A failed fetch shall never raise to the caller; the item is still stored and the failure logged. |
| NFR-2 | Should | Performance | Fetches and `ghx`/`slackx` calls shall run off the event loop. |
| NFR-3 | Should | Security | Fetched web content shall be truncated (20,000 characters) before storage. |

## Constraints

- Integrations are metadata-only and pull on demand; there are no OAuth flows or webhooks.
- `ghx` and `slackx` must be on `PATH`; when missing, the fetch returns nothing rather than failing.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Infer a Slack thread
      Given the URL https://acme.slack.com/archives/C1/p1700000000
      When the user creates an item with only that URL
      Then the item source is "slack", kind "thread", and the external id is the channel and timestamp

    @FR-1
    Scenario: Infer a GitHub issue
      Given the URL https://github.com/o/r/issues/42
      When the user creates an item with that URL
      Then the item source is "github", kind "issue", external id "o/r#42"
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Plain text is a note
      Given the text "remember to rotate the token"
      When the user creates an item with only that text
      Then the source is "note" and the url is null and the content is the text
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Fetch failure is tolerated
      Given a URL whose fetch fails
      When the user creates an item with fetch enabled
      Then the item is still created
      And no exception reaches the caller
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Create a task from a GitHub issue
      Given a valid GitHub issue URL
      When the user creates a task with that github_url
      Then the title and description are prefilled from the issue
      And the issue is associated as an item
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should items refresh automatically on a schedule, or only on demand?
