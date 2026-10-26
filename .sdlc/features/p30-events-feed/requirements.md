---
title: "Events feed"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: Events feed

## Overview
A task's timeline is useful on that task and useless when the question is "what happened across everything".
The events feed merges every task's timeline into one cross-task stream, newest first, where each row carries the task's title and status so it reads on its own.
The stream is filterable by task, event type, actor, client, and a text search, and pages backwards with a cursor so nothing is skipped between pages.
The SPA shows the feed at `/events`, grouped by local day, with each row linked back to its task.
The same timeline events can be delivered to Slack, one event or a recent batch, from the API or the CLI, using the configured Slack recipient.
The operations audit log is deliberately not merged in, because it records the same mutating requests again.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | See recent activity across all tasks in one place, and receive events in Slack instead of watching the app |
| Coding agent | Read `GET /api/events` over HTTP and send events to Slack through the API or `agentic events send-slack` |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall return timeline events from every task as one list from `GET /api/events`, newest first with an id tie-breaker, where each row carries the task's title and status next to the event fields. |
| FR-2 | Must | The system shall filter the feed by `task_id`, event `type`, `actor`, `client`, and a case-insensitive substring `q` matched against the event message and the task title. |
| FR-3 | Must | The system shall page backwards with `before` (the last row's created_at) and `before_id` (its id), and shall bound `limit` between 1 and 500 with a default of 50. |
| FR-4 | Should | The Events page shall group the rows by local day (Today, Yesterday, or a date), link each row back to its task, reload from the server when the actor or client filter changes, debounce the search to the server by 250 ms, and offer a load-older button whenever the last page came back full. |
| FR-5 | Must | The system shall send one event to Slack through `POST /api/events/{id}/slack` and its `/send` and `/send-to-slack` aliases, rendering the task title, type, message, time, and data as the message. |
| FR-6 | Must | The system shall send recent events to Slack through `POST /api/events/slack` and aliases, selecting the events by explicit ids, by a task's latest 50, or the latest 50 overall, and shall return 404 when there is nothing to send and 502 when Slack refuses or fails. |
| FR-7 | Should | The system shall resolve the Slack recipient from, in order: the request payload (user_id, slack_user_id, channel, recipient, to), a People alias lookup for a `login`, the query string, the database settings keys, then the environment settings. |
| FR-8 | Should | The CLI shall send events with `agentic events send-slack [event-id]`, accepting `--user-id`, `--task-id`, and `--text`, using the configured default recipient when the user id is omitted. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Correctness | The feed shall draw only from the timeline tables; the operations audit log shall not be merged, so one action never appears twice. |
| NFR-2 | Must | Correctness | The paging cursor shall compare created_at and id together, so events written in the same instant are never skipped or repeated between pages. |
| NFR-3 | Should | Maintainability | The Slack message rendering shall be a pure function over an event, and delivery shall go through the shared Slack bot-DM sender used by the rest of the app. |

## Constraints

- The feed is read-mostly: the only writes it triggers are Slack sends, which change nothing in the database.
- Slack delivery is synchronous within the request; there is no queue and no retry.
- The CLI has no `events list`; agents read the stream over HTTP.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: The stream carries every task's activity with task context
      Given two tasks with created events and one patch
      When GET /api/events is called with a matching search
      Then rows from both tasks come back newest first
      And each row carries task_title, task_status, client, and actor
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Filters narrow the stream
      Given a task patched by the CLI as an agent
      When the feed is filtered by task_id, then by type updated, then by actor agent and client cli
      Then each response contains only the matching rows
      And a search that matches nothing returns an empty list
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Pages continue without repeating rows
      Given four updates on one task and a page size of 2
      When the second page is requested with before and before_id from the last row
      Then the pages share no ids and continue where the first stopped
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: The page groups by day and pages older events
      Given events from today and yesterday
      When the Events page renders
      Then each day is a group with its own timeline panel and task links
      And clicking load older requests the next page with the last row's cursor
      And a short second page removes the button
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: One event is sent to Slack
      Given an event id and a recipient
      When POST /api/events/{id}/slack is called
      Then the rendered message carries the task title, type, message, time, and data
      And the response reports ok, the event and task ids, the recipient, and the Slack ts
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Recent events are sent as one message
      Given no event selection
      When POST /api/events/slack is called
      Then the latest 50 events are sent as one message and the response counts them

    @FR-6
    Scenario: Nothing to send
      Given a database with no events for the selection
      When the send endpoint is called
      Then the response is 404
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: The recipient falls back through the layers
      Given no recipient in the payload or query and a configured slack_events_user_id
      When an event is sent
      Then the configured database setting is used as the recipient
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: The CLI sends recent events
      Given a running API
      When agentic events send-slack runs with a user id
      Then the API send endpoint is called and the result is printed
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: The audit log does not appear in the feed
      Given mutating requests recorded in the audit log and timeline events for the same actions
      When the feed is read
      Then only timeline events come back
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: Same-instant events are not skipped
      Given two events sharing one created_at
      When pages are walked with before and before_id
      Then each event appears exactly once across the pages
    ```

## Conflicts

None identified yet.

## Open Questions

None.
