---
title: "Gantt timeline view"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: Gantt timeline view

## Overview

The Gantt view shows tasks in flight as rows on a shared time axis, each drawn as a bar from its creation to its last update, with one marker per timeline event.
It makes progress and activity visible together: a row's bar shows how long a task has been alive, and the markers show what happened along the way.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | See at a glance which tasks are in flight, for how long, and what has happened on each |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall return tasks oldest-first, each with its span (`created_at`, `updated_at`) and one marker per timeline event ordered oldest-first. |
| FR-2 | Must | The system shall exclude tasks with status done or archived unless `include_done` is requested. |
| FR-3 | Must | The view shall draw a bar per task from creation to last update, with a marker per timeline event, coloured by event type. |
| FR-4 | Must | The view shall show a time axis with ticks and a "now" line, a legend of marker kinds, an include-done toggle, a refresh action, and an error state with retry. |
| FR-5 | Must | Each row shall link to its task detail. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Should | Maintainability | The chart shall be rendered with plain CSS from the existing data, with no charting dependency. |
| NFR-2 | Should | Usability | Closed tasks shall be hidden by default so the view stays focused on work in flight. |

## Constraints

- The chart reuses `TimelineEvent` rows as markers; there is no new persistent data.
- The visible window always includes the current time so in-flight work reaches the right edge.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Markers are ordered and typed
      Given a task that was created and then updated
      When the gantt endpoint is read
      Then the task's markers are ordered oldest first
      And they include a "created" and an "updated" marker
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Hide done tasks
      Given a task with status done
      When the gantt endpoint is read without include_done
      Then the task is absent
      And it is present when include_done is true
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should the Gantt view be live (SSE) like the task detail, or stay refresh-on-demand?
