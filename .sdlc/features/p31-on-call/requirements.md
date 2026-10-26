---
title: "On-call view"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: On-call view

## Overview
Being on call means watching a Slack channel for questions, answering the ones that need an answer, and remembering which threads are done.
The on-call view turns that loop into three steps: it scans a configured Slack channel through `slackx`, groups the messages into threads with a prepared reply for each, and lets the user send the reply, mark the thread resolved, or turn a thread into a task.
A rotation window (start and end times) and a scan frequency bound when the scanning runs, and the channel and rotation configuration persist in the app's settings so the page resumes where it left off.
Marking a thread resolved stores one Slack item keyed by a canonical external id, so resolution survives renames of the configured channel and shows up again if the thread sees new activity.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Answer a help channel from one page, with a draft reply ready per thread and a clear resolved state |
| Coding agent | Read the scan, reply, and resolve endpoints directly over HTTP |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall scan a channel with `POST /api/on-call/scan` by running `slackx conversations get <channel> --json --last <lookback> --with-thread-message --fetch` (60 second timeout) and returning the messages grouped into threads: a root with title, text, author, replies, a combined context, and reply count. |
| FR-2 | Should | The scan's lookback shall cover the rotation window from `rotation_starts_at` to now (formatted like `1d4h`), fall back to one day without a configured start, and return an inactive empty payload when the rotation has not started yet. |
| FR-3 | Must | Each scan shall match every thread to a stored Slack item by the canonical external id `<channel id>:<dotless ts>`, healing items stored under older ids or non-permalink URLs, and shall report per thread: the linked task id, resolved state, resolved-through watermark, whether there is new activity past that watermark, and refreshed Slack and slackx permalinks, while refreshing the stored transcript and title. |
| FR-4 | Must | The system shall send a reply with `POST /api/on-call/reply` by posting the text to the channel, or into the thread when `thread_ts` is given, through Slack `chat.postMessage` using the bot token from database settings or `SLACK_TOKEN`, with an optional `SLACK_COOKIE`, and shall reject a missing channel, text, or token with 400 and a Slack failure with 502. |
| FR-5 | Must | The system shall store resolution with `POST /api/on-call/resolve`: it creates the thread's Slack item (source slack, kind thread) when missing, keys it by the resolved channel id when the config names a `#channel`, and sets or clears `done_at` and `done_message_ts` (watermark defaulting to the latest given ts, else the thread ts). |
| FR-6 | Should | The On-call page shall persist the channel, scan frequency (default 5 minutes), and rotation start and end to settings (`on_call_channel`, `on_call_config`), restore them on mount, and scan on a timer while the rotation is active, showing the rotation as waiting, running, stopped, or ended. |
| FR-7 | Should | The page shall prepare a draft reply per thread (defaulting to "Thanks for the update, I'll take a look."), reset a draft only when the thread sees new activity and the draft was not edited, and offer send reply, resolve or reopen, and create task (a Slack item plus an open task plus the association) per thread. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Data integrity | A thread shall map to exactly one Slack item; resolution and scans must find and heal items stored under earlier external id or URL forms instead of creating duplicates. |
| NFR-2 | Should | Performance | The blocking slackx subprocess and Slack HTTP call shall run in sync route handlers, so the event loop stays responsive while they run. |
| NFR-3 | Should | Robustness | Per-thread bookkeeping failures during a scan (item lookup, transcript refresh) shall not fail the scan; the threads still come back. |

## Constraints

- Channel access depends on the `slackx` CLI being installed and configured; a missing `slackx` is a 502.
- Replying uses a Slack user or bot token directly (`SLACK_TOKEN`, database `slack_bot_token`, optional `SLACK_COOKIE`), not the People directory.
- The configuration lives in the settings store (`on_call_channel`, `on_call_config`), not in a dedicated table.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: A scan groups replies under their thread root
      Given a channel with one root message and one thread reply
      When POST /api/on-call/scan runs
      Then one thread comes back with the reply nested, a reply count of 1, and a combined context
      And each thread carries its Slack permalink and, when configured, a slackx permalink
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: The rotation has not started
      Given a rotation_starts_at in the future
      When the scan runs
      Then the response is empty with inactive true

    @FR-2
    Scenario: The lookback covers the rotation so far
      Given a rotation that started 2 days and 3 hours ago
      When the scan runs
      Then slackx is asked for --last 2d3h
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: A resolved thread with a newer reply shows new activity
      Given a thread resolved through its root ts and a reply with a later ts
      When the scan runs
      Then the thread reports resolved true and has_new_activity true
      And the stored item's transcript and fetched time are refreshed
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: A reply is posted into its thread
      Given a configured token, a channel, text, and a thread ts
      When POST /api/on-call/reply is called
      Then Slack chat.postMessage receives the channel, text, and thread_ts
      And the response reports ok with the message ts

    @FR-4
    Scenario: Missing configuration is a 400
      Given no token configured
      When the reply endpoint is called
      Then the response is 400
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Resolving creates one item under the canonical id
      Given a channel id and thread ts never resolved before
      When POST /api/on-call/resolve is called twice
      Then one Slack item exists with external id "<channel>:<dotless ts>" and done true
      And done_message_ts records the watermark

    @FR-5
    Scenario: A named channel is keyed by its id
      Given the config says "#help-ml-infrastructure"
      When the thread is resolved
      Then the item's external id and permalink use the resolved channel id
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Configuration survives a reload
      Given a channel, frequency, and rotation window entered on the page
      When the page is reloaded
      Then the values are restored from the settings
      And the scan timer runs while the rotation is active and stops when it ends
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Creating a task from a thread
      Given a scanned thread with a permalink
      When create task is clicked
      Then a Slack item and an open task are created and associated
      And the thread shows its new task id
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Legacy items are healed, not duplicated
      Given an item stored under the bare thread ts or the configured "#name" channel
      When the thread is resolved or scanned
      Then the same item is found, its external id and URL are rewritten to the canonical forms, and no second item is created
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: Item bookkeeping fails without failing the scan
      Given an item lookup that raises for one thread
      When the scan runs
      Then the threads are still returned and the other threads keep their task and resolved fields
    ```

## Conflicts

None identified yet.

## Open Questions

1. `GET /api/on-call` exists and returns an empty thread list; nothing calls it, so its purpose (a placeholder or a future list endpoint) is unclear from the code.

## Manual-Review Items

1. The On-call page probes several plausible API namespace and method names before each call (`onCall.scan`, `oncall.reply`, and so on); the behavior works against the current `api.js`, but this defensive probing is worth a deliberate review.
2. No documentation page exists under `docs/` for the on-call view; the docs pipeline phases are therefore marked not started.
