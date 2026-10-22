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
| FR-9 | Should | The system shall return each item's linked task ids and support searching items by a text query over title, url, and content. |
| FR-10 | Should | The system shall let a user mark a Slack thread done, flag a message that arrives after it was marked done while keeping the done state, and let the user reopen it. |
| FR-11 | Should | The system shall accept a path to a local file or directory as an item, store its resolved absolute path and stat metadata as a reference, and read a file preview or directory listing live on request without storing it. A text file is previewed in full, and a Markdown file is rendered as Markdown. |

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

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: List items with their tasks and a search
      Given an item associated with a task
      When the items list is requested with a query matching the item
      Then the item is returned with the task's id in its task_ids
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: A reply arrives after a thread is marked done
      Given a Slack thread whose newest message is at 10:00
      When the user marks it done
      And a refresh sees a new message at 11:00
      Then the thread is still done
      And it is flagged as having new messages since it was done

    @FR-10
    Scenario: Reopen a done thread
      Given a Slack thread marked done
      When the user reopens it
      Then it is no longer done and carries no new-message flag
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: Add a local path as an item
      Given a path to an existing file or directory
      When the user creates an item with that path
      Then the source is "file", the external id is the resolved absolute path, and the kind is "file" or "directory"
      And the stored content is empty

    @FR-11
    Scenario: Read a path item's preview
      Given a path item
      When the user opens its preview, or refreshes it
      Then the API reads the file or directory from disk
      And the item record is left without a content snapshot

    @FR-11
    Scenario: Preview a long Markdown file
      Given a path item for a Markdown file larger than 20,000 characters
      When the user opens the item
      Then the whole file is read
      And it is rendered as Markdown

    @FR-11
    Scenario: Deduplicate a path item
      Given an item already stored for a path
      When the user adds the same path again, by url or by path
      Then the existing item is returned
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should items refresh automatically on a schedule, or only on demand?
