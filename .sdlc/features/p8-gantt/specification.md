---
title: "Gantt timeline view"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Specification: Gantt timeline view

## Overview

The Gantt view is served by `routers/gantt.py` as `GET /api/gantt`, returning `GanttTask` rows built from `Task` plus its `TimelineEvent` markers.
`frontend/src/views/GanttView.vue` renders the rows as a hand-rolled CSS chart: a shared time domain, tick gridlines, a bar per task, a marker per event, and a legend.

## Architecture

```mermaid
flowchart LR
    V[GanttView.vue] --> A[api.js]
    A --> R[routers/gantt.py]
    R --> DB[(Task + TimelineEvent)]
```

## Data Models

### GanttTask (response-only)

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | string | PK | Task id |
| title | string | not null | Task title |
| status | TaskStatus | not null | Lifecycle status |
| priority | int | not null | 0 to 3 |
| created_at | datetime | not null | Span start |
| updated_at | datetime | not null | Span end |
| markers | list[TimelineRead] | default [] | One per timeline event, oldest first |

No table is added; the view is derived from `task` and `timelineevent`.

## API Contracts

The normative contract is in [`api.yaml`](api.yaml) once written; the table below is the summary.

| Method | Path | Purpose |
|---|---|---|
| GET | /api/gantt | Tasks with spans and timeline markers (query: include_done) |

## Sequences

### Load the gantt

```mermaid
sequenceDiagram
    autonumber
    participant V as GanttView
    participant R as gantt router
    participant DB as SQLite
    V->>R: GET /api/gantt?include_done=false
    R->>DB: select tasks order by created_at
    loop each task
        R->>DB: select timelineevent order by created_at
    end
    R-->>V: list[GanttTask]
```

## Technical Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Data source | Existing `Task` and `TimelineEvent` rows | No new persistence; markers are already recorded |
| Closed filter | `done` and `archived` hidden unless asked | Keeps the default view on work in flight |
| Rendering | Plain CSS positioning over a fixed data domain | No charting library; the shape is simple |

## Risks and Unknowns

1. One timeline query runs per task (N+1); acceptable for the local dataset, but it would need batching on a large task count.
2. The domain is computed client-side and always includes now, so far-future events would compress the visible range.

## Out of Scope

- Editing a task from the chart.
- Live (SSE) updates of the chart.
