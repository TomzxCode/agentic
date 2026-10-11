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
| FR-4 | Must | The view shall show a time axis with ticks and a "now" line (subject to FR-7), a legend of marker kinds, an include-done toggle, a refresh action, and an error state with retry. |
| FR-5 | Must | Each row shall link to its task detail. |
| FR-6 | Must | The view shall let the user set the visible start and end of the time axis through two date-time fields, defaulting each unset bound and every refresh to a window fitted to the data, with a fit action that resets the window, and shall mark the range invalid when the end is not after the start. |
| FR-7 | Should | The view shall draw the "now" line only when the current time falls inside the visible window. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Should | Maintainability | The chart shall be rendered with plain CSS from the existing data, with no charting dependency. |
| NFR-2 | Should | Usability | Closed tasks shall be hidden by default so the view stays focused on work in flight. |

## Constraints

- The chart reuses `TimelineEvent` rows as markers; there is no new persistent data.
- The fitted window always includes the current time so in-flight work reaches the right edge; a window the user sets may exclude it, in which case the "now" line is hidden.
- The visible start and end are transient view state, not persisted.

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

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Set the visible window
      Given the gantt view is shown with a window fitted to the data
      When the user sets an end that is after the start
      Then the axis spans exactly that start and end
      And task bars and markers outside it are clipped

    @FR-6
    Scenario: Reset the window
      Given the user has set a custom window
      When the user activates fit
      Then the axis spans a window fitted to the data and including now

    @FR-6
    Scenario: One bound left unset
      Given the user sets only the start
      Then the axis spans from that start to the fitted end

    @FR-6
    Scenario: Refit until the user edits
      Given the user has not edited either field
      When the view reloads with new activity
      Then the axis refits to include the new activity

    @FR-6
    Scenario: Reject a reversed window
      Given the user sets an end that is not after the start
      Then the view reports the range as invalid
      And shows the fitted window instead
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Hide now outside the window
      Given the user sets a window that ends before the current time
      Then the "now" line and its legend entry are not drawn
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should the Gantt view be live (SSE) like the task detail, or stay refresh-on-demand?
