---
title: "Review SLO"
status: draft
---

# Specification: Review SLO

## Overview

The review SLO is one overridable setting, `review_slo`, parsed as a duration.
The inbox reads the review scan's stored `ReviewRequest` rows, keeps the ones still awaiting the user's review, and offers each whose `first_seen_at` is older than the SLO.
No table or column is added, and the inbox still stores nothing.

## Architecture

```mermaid
flowchart LR
    S[SettingsReviewScan.vue] -->|PATCH /api/settings review_slo| R[routers/settings.py]
    R --> SS[settings_store]
    SS --> DB[(setting)]
    RR[ReviewRequest rows from the review scan] --> I[inbox.build_review_suggestions]
    DB -->|configured_review_slo| I
    I --> IR[routers/inbox.py]
    IR --> SPA[InboxView.vue]
```

## Data Models

### Setting `review_slo` (existing table)

| Field | Type | Description |
|---|---|---|
| key | varchar | `review_slo` |
| value | varchar | A duration such as `8h` or `1d`; empty or `off` disables it |

Added to `OVERRIDABLE_KEYS` and `env_defaults`; the environment fallback is `AGENTIC_REVIEW_SLO`.
The Settings page override wins over the environment value.

### ReviewRequest (existing table, read only)

| Field | Use |
|---|---|
| `repository`, `number`, `title`, `url` | Identify and link the pull request in the suggestion |
| `source` | Only `requested` counts; `reviewed` is a pull request the user already reviewed |
| `draft` | A draft is not ready for review and is left out |
| `state` | Only `OPEN` (or unread) counts; a stale `MERGED`/`CLOSED` row is left out |
| `first_seen_at` | The start of the wait; it survives across scans |

The wait is `now - first_seen_at`, with a naive stored value read as UTC.
The suggestion is produced when the wait is strictly greater than the SLO.

## API Contracts

| Method | Path | Change |
|---|---|---|
| GET | `/api/settings` | `review_slo` appears in `effective`, `overrides`, and `defaults` |
| PATCH | `/api/settings` | Accepts `review_slo`; a non-empty malformed duration is a 422 naming the field |
| GET | `/api/inbox` | Adds `review_pr_past_slo` suggestions |
| GET | `/api/reviews/scan` | Unchanged; the scan still supplies the rows |

An inbox suggestion for a review has no task:

```json
{
  "id": "review_pr_past_slo:o/r:42",
  "kind": "review_pr_past_slo",
  "reason": "Has awaited your review for 2d 3h; the SLO is 1d.",
  "task_id": null,
  "task_title": "",
  "task_status": "",
  "repository": "o/r",
  "number": 42,
  "title": "Fix the thing",
  "url": "https://github.com/o/r/pull/42",
  "actions": [
    {
      "id": "open:o/r:42",
      "kind": "open_url",
      "label": "Review PR",
      "url": "https://github.com/o/r/pull/42"
    }
  ]
}
```

Shared error codes:

| Status | Code | Description |
|---|---|---|
| 422 | VALIDATION_ERROR | `review_slo` is not a duration and is not blank |

## Web UI

| Component | Change | Requirements |
|---|---|---|
| `SettingsReviewScan.vue` | A **Review SLO** field, saved on blur like the scan cadence, with the same duration grammar and a blank to disable it | FR-1, FR-7 |
| `InboxView.vue` | A **Reviews past SLO** section listed first; a non-task row links its title and its **Review PR** action to the pull request | FR-5, FR-8 |
| `InboxSuggestion` schema | `task_id`, `task_title`, and `task_status` become optional; `repository`, `number`, `title`, and `url` are added | FR-5 |
| `InboxAction` schema | `task_id` becomes optional and `url` is added, carrying the `open_url` target | FR-5 |

The review row is an anchor, not a form button, so it opens GitHub in a new tab and needs no API call.

## Sequences

### An SLO is set

```mermaid
sequenceDiagram
    autonumber
    participant C as SPA
    participant S as settings router
    participant DB as SQLite
    C->>S: PATCH /api/settings {"review_slo": "1d"}
    S->>S: validate the duration
    S->>DB: upsert setting review_slo
    S-->>C: 200 SettingsRead
    C->>C: store.loadInbox on the next visit
```

### The inbox is read

```mermaid
sequenceDiagram
    autonumber
    participant C as SPA
    participant I as inbox router
    participant R as review_scan
    participant DB as SQLite
    C->>I: GET /api/inbox
    I->>R: configured_review_slo(session)
    R->>DB: read setting review_slo
    I->>R: stored_review_requests(session)
    R->>DB: read ReviewRequest rows, minus excluded repositories
    I->>I: build_review_suggestions(rows, slo, now)
    I->>I: merge with task suggestions and sort by kind rank
    I-->>C: 200 InboxReport
```

## Rules

- `review_slo` uses the same duration parser as the scan cadence, so `30m`, `1h`, `1d`, `2w`, `off`, and blank all behave as they do elsewhere.
- A suggestion is offered only when the wait is greater than the SLO; exactly at the SLO does not count.
- `first_seen_at` is not reset by a scan, so the wait survives until the pull request leaves the scan or the row is dropped.
- The suggestion carries no task even when a task links the pull request; linking it to a task is left to the user.
