---
title: "Tiered item refresh"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: Tiered item refresh

## Overview

Slack threads and GitHub issues and pull requests change at different rates over their lives: a just-opened one may see activity within the hour, while one from last month is effectively settled.
A refresh policy is a list of age bands, each pairing an upper age with a refresh interval, plus an optional fallback (`1d=1h,7d=6h,30d=1d,*=7d`), so fresh items refresh sooner and settled items rarely or never.
`refresh.py` holds the pure policy language (parsing, band selection, the due calculation, and the item's true age from its upstream start), `routers/items_refresh.py` runs the policy-driven fetch pass and the per-source force refresh (sharing `_apply_fetch` with the single-item refresh), a background loop in `main.py` ticks the pass, and the Settings page's Refresh section edits the policies with a live preview and a per-source force button.
The boundary with p2-source-items holds: p2 covers the items and associations themselves and the on-demand single-item fetch; p34 covers the background tiered refresh policy pass, its per-source policies, and the settings and status surfaces around it.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Keep Slack threads and GitHub issues current without re-fetching settled items by hand |
| Agent | Run a refresh pass or set a policy through the CLI and API without the web UI |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall parse a refresh policy from `age=interval` bands with an optional single `*` fallback, accepting durations in seconds, minutes, hours, days, and weeks, singly or combined (`1h30m`), the words `never`/`none`/`off`/`-` as "stop refreshing", and empty text as disabled |
| FR-2 | Must | The system shall reject malformed policies with a `PolicyError`: a missing `=`, an unknown or lone value, a non-increasing age sequence, a repeated fallback, or a zero total duration |
| FR-3 | Must | The system shall compute an item's true age from its upstream start: the GitHub `created_at` metadata, else the Slack thread timestamp in the URL, else the time the item was recorded |
| FR-4 | Must | The system shall decide due items per policy: the interval comes from the first band the item's age fits, the fallback applies past the last band, an item never fetched is due, a naive `fetched_at` is treated as UTC, and a none interval is never due |
| FR-5 | Must | The system shall map each refreshable source (`slack`, `github`) to its settings key (`slack_refresh_policy`, `github_refresh_policy`) and skip a source with no policy or a malformed one |
| FR-6 | Must | A background loop shall run the due pass every `AGENTIC_ITEM_REFRESH_TICK` seconds (a tick of 0 disables it) in a worker thread with its own session, recording each source's outcome with origin `background` |
| FR-7 | Must | `POST /api/items/refresh-due` shall run one pass immediately with origin `manual`, and `POST /api/items/refresh-source/{source}` shall re-fetch every item of that source now ignoring the policy (404 for an unknown source, origin `manual`) |
| FR-8 | Must | The CLI shall expose `agentic item refresh-due` and `agentic item refresh-source <source>` for the same passes |
| FR-9 | Must | Applying a fetch shall merge the fetched title (unless a person set a custom one), content, and metadata, keep file items as references without stored content, baseline a Slack thread marked done before its first fetch, leave `fetched_at` alone on a failed fetch so the policy retries, and link the fetched people |
| FR-10 | Must | Each pass shall record one outcome per source (last run time, refreshed and failed counts, the last error, the origin, and the 24-hour refreshed sum) readable at `GET /api/settings/refresh-status` |
| FR-11 | Must | The Settings page's Refresh section shall edit both policies with a debounced live preview from the server's parser, save on blur (422 on a malformed policy from the settings PATCH), and offer a per-source force refresh with a last-run status line |
| FR-12 | Should | A repository listing sync shall merge the listing's state fields onto the stored items it names, so an item is never staler than the repository view that shows it, without touching item bodies or people |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Testability | Policy parsing and the due calculation are pure functions over plain values, tested without a database or a clock |
| NFR-2 | Must | Performance | Fetch passes talk to slackx, ghx, or the network, so items fetch together on a pool thread and the background pass runs in a worker thread with its own session, never on the event loop |
| NFR-3 | Must | Reliability | A pass is best effort per item: one item's failure (a missing or erroring CLI) is recorded in that item's entry and the source's outcome without stopping the others |
| NFR-4 | Must | Correctness | A failed fetch does not advance `fetched_at`, so the item reads as unfetched and the policy retries it instead of treating the miss as fresh |
| NFR-5 | Must | Consistency | The settings preview uses the same server-side parser as the runner, so what the UI shows and what the loop does cannot disagree |
| NFR-6 | Should | Operability | An empty policy disables a source entirely and the tick of 0 disables the loop, so the feature can be switched off without removing data |

## Constraints

- Only `slack` and `github` sources refresh automatically; notes and files have nothing upstream to fetch (files fetch on demand only).
- The pass fetches at most the items whose policy says they are due; force refresh ignores the policy but still records a manual run.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: A policy parses into bands and a fallback
      Given the text "1d=1h,7d=6h,30d=1d,*=7d"
      When the policy is parsed
      Then it has three tiers with those ages and intervals plus a weekly fallback
      And it reports as enabled
    ```

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Never and empty stop the refresh
      Given the text "1d=1h,*=never" and the text ""
      When each is parsed
      Then the first is enabled with no fallback interval
      And the second has no tiers and no fallback and reports as disabled
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Malformed policies raise
      Given "7d=1h,1d=2h", "1d", "1d=soon", "*=1h,*=2h", or "1d=1h,1d=2h"
      When each is parsed
      Then a PolicyError names the problem
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Age comes from the upstream start
      Given a GitHub item recorded 90 days ago with created_at from 2020, a Slack thread URL with a timestamp, and an item with neither
      When each item's start is computed
      Then the GitHub item ages from 2020, the Slack item from its thread timestamp, and the last from its recorded time
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Due selection by band and last fetch
      Given a policy "1d=1h,30d=1d" and an item two hours old
      When the due check runs with no fetch time, a fetch 30 minutes ago, a fetch 2 hours ago, and an age past the last band
      Then the results are due, not due, due, and never due respectively
      And a naive fetch time is treated as UTC
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Policies come from settings by source
      Given effective settings holding both policy keys
      When the per-source policies are pulled
      Then slack and github each carry their text, and missing keys read as empty
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: The background tick runs a pass
      Given a slack policy set and a due item
      When the background tick fires
      Then the item refreshes and the slack status records the run with origin background
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Manual and forced passes
      Given a github policy and items due and not due
      When POST /api/items/refresh-due runs
      Then only due items refresh and the origin is manual
      When POST /api/items/refresh-source/github runs
      Then every github item with a URL refreshes regardless of the policy, and an unknown source returns 404
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: CLI passes
      Given a running API
      When agentic item refresh-due and agentic item refresh-source github run
      Then the same reports print as the API returns
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: A fetch merges without clobbering
      Given an item with a custom title and a fetch returning a new title, content, and metadata
      When the fetch is applied
      Then the custom title stays, the content and metadata merge, and fetched_at advances
      And a failed fetch keeps the old fetched_at while still merging what it returned
      And a file item keeps a reference with no stored content
      And a thread marked done before its first fetch takes that fetch's latest message as its baseline
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: Per-source status
      Given a completed pass with successes, failures, and an origin
      When GET /api/settings/refresh-status is read
      Then each active source reports its last run time, refreshed and failed counts, last error, origin, and the refreshed-24h sum
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: The settings section previews and saves
      Given the Refresh section open
      When a policy is typed
      Then a debounced preview shows the parsed bands from the server's parser, or the error for a malformed one
      And leaving the field saves it, and a malformed policy saved through PATCH /api/settings is rejected with 422
    ```

- [ ] **FR-12**

    ```gherkin
    @FR-12
    Scenario: The listing sync keeps items fresh for display
      Given a ghx listing whose PR state is newer than the stored item's
      When the repository sync merges it
      Then the stored item's state metadata and non-custom title update and the changed count reflects it
      And an identical listing writes nothing
    ```

## Conflicts

None identified yet.

## Open Questions

1. Whether a policy's bands should be allowed to overlap sources differently (per-repository policies rather than one GitHub-wide policy) is a product call the code cannot answer.
