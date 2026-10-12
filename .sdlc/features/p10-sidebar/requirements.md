---
title: "Sidebar"
status: draft
session_link: "http://localhost:10000/?session=ses_ed267ac83ffevHmFcwZ0aUr1Hf"
---

# Requirements: Sidebar

## Overview

The sidebar is the web app's persistent left column.
It is the primary way to see and switch between the tasks in flight without leaving the current view.
This feature specifies the sidebar's task entry list, and in particular that each entry is shown on a single line.
A sidebar entry does not show tags; tag display belongs to the main tasks list, and the tag filter strip remains the way to filter from the sidebar.
This supersedes FEAT-p9 FR-5 for the sidebar entry (see Conflicts).
The sidebar's brand, primary navigation, and mobile drawer behavior stay with the web UI feature (FEAT-p7), which this feature refines rather than replaces.

## Definitions

- **In flight:** a task whose status is `open`, `in_progress`, or `blocked` (that is, not `done` and not `archived`).
- **Entry:** one task row in the sidebar list.
- **Single line:** an entry that lays its content out in one row, with no child element wrapped onto a second row.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Scan and switch between tasks in flight from any view, on a phone or on a desktop |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The sidebar shall list the tasks in flight, and shall apply the active tag filter. |
| FR-2 | Must | Each entry shall render on a single line, in the order status control, title, count of open next steps, and relative age of the last update in the app's `timeAgo` format (for example "5m ago"), and shall not show the task's tags. |
| FR-3 | Must | When the entry's content does not fit the entry width, the title shall truncate with an ellipsis, so the sidebar keeps its width and the status control, step count, and age stay visible. |
| FR-4 | Must | Selecting an entry shall open that task, and the entry for the task whose detail view is open shall be marked active. |
| FR-5 | Must | The sidebar shall render a loading indicator while the first load is pending, a message when the list is empty (distinguishing "no tasks yet", "all caught up", and "no tasks match the active tag filter"), and an error state with a retry action when the load fails. |
| FR-6 | Should | Changing an entry's status from the sidebar shall update the task and drop the entry from the list when the new status is done or archived. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Usability | Every entry shall occupy the same height regardless of its content, so the list scans as an even column. |
| NFR-2 | Must | Accessibility | The icon-only status control shall carry an `aria-label` naming its action, and every entry shall be reachable and activatable from the keyboard. |
| NFR-3 | Should | Usability | At a viewport 320 px wide (where the drawer and the entry's padding leave roughly 230 px of content width), each entry shall stay on one line with no horizontal scrolling. |
| NFR-4 | Should | Maintainability | The single-line layout shall be achieved within the existing `App.vue` entry markup and `styles.css`, with no new component and no new dependency. |

## Constraints

- The sidebar is rendered inline by `App.vue`; entries are `.task-card` elements styled in `styles.css`.
- The app is mobile-first, so the layout is checked at phone widths as well as on a desktop.
- Below 760px the sidebar becomes an off-canvas drawer, toggled from the top bar (specified by FEAT-p7).
- The tag-filter portion of FEAT-p9 FR-5 (the filter strip above the sidebar list) is still `status: draft`; this feature assumes that part stands, while the tag-display portion of FR-5 is superseded for the sidebar entry (see Conflicts).

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Only work in flight is listed
      Given tasks with status open, in_progress, blocked, done, and archived
      When the sidebar is shown
      Then the open, in_progress, and blocked tasks are listed
      And the done and archived tasks are not

    @FR-1
    Scenario: The active tag filter narrows the list
      Given one in-flight task tagged "bug" and one in-flight task tagged "ui"
      And the "bug" tag filter is active
      When the sidebar is shown
      Then only the task tagged "bug" is listed
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: A full entry fits one line
      Given an in-flight task with a short title, two open next steps, and an update 5 minutes ago
      When its entry is shown in the sidebar
      Then the entry shows the status control, the title, a step count of 2, and the age "5m ago"
      And the entry's content is laid out in a single row

    @FR-2
    Scenario: A missing field does not add a line
      Given an in-flight task with no next steps
      When its entry is shown in the sidebar
      Then no step count is shown
      And the entry still occupies a single line

    @FR-2
    Scenario: Tags are not shown
      Given an in-flight task carrying the tags "bug" and "ui"
      When its entry is shown in the sidebar
      Then the entry shows no tag
      And the entry occupies a single line
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: A long title truncates
      Given an in-flight task whose title is longer than the entry is wide
      When its entry is shown in the sidebar
      Then the title is truncated with an ellipsis
      And the status control, step count, and age remain visible
      And no horizontal scrollbar appears in the sidebar
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Selecting an entry opens the task
      Given the sidebar lists an in-flight task
      When the user selects its entry
      Then the task's detail view opens

    @FR-4
    Scenario: The open task is marked
      Given the task detail view is open for a listed task
      When the sidebar is shown
      Then that task's entry carries the active marker
      And the other entries do not
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: The first load shows a spinner
      Given the app has not loaded its tasks yet
      When the sidebar is shown
      Then a loading indicator is shown

    @FR-5
    Scenario: An empty list explains itself
      Given there are no tasks
      When the sidebar is shown
      Then the "no tasks yet" message is shown

    @FR-5
    Scenario: Finished work only
      Given tasks exist but all are done or archived
      When the sidebar is shown
      Then the "all caught up" message is shown

    @FR-5
    Scenario: A tag filter with no match explains itself
      Given in-flight tasks exist but none carry the tag "bug"
      And the "bug" tag filter is active
      When the sidebar is shown
      Then a message says no tasks match the "bug" filter

    @FR-5
    Scenario: A failed load offers a retry
      Given the tasks fail to load
      When the sidebar is shown
      Then an error state with a retry action is shown
      When the user triggers the retry and the load succeeds
      Then the list is shown
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Completing a task removes its entry
      Given the sidebar lists an in-flight task
      When the user sets its status to done from the sidebar
      Then the task's status becomes done
      And its entry is no longer listed

    @FR-6
    Scenario: Archiving a task removes its entry
      Given the sidebar lists an in-flight task
      When the user sets its status to archived from the sidebar
      Then the task's status becomes archived
      And its entry is no longer listed

    @FR-6
    Scenario: The list reverts when the change fails
      Given the sidebar lists an in-flight task
      When the status change fails
      Then the task keeps its previous status
      And its entry stays in the list
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Tags do not affect entry height
      Given one in-flight task carrying many tags and one in-flight task carrying none
      When both entries are shown in the sidebar
      Then both entries are the same height
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: The status control is labelled and the entry is keyboard reachable
      Given an in-flight task in the sidebar
      When the entry is inspected
      Then the status control element has an aria-label naming the status action
      And the title link can be focused with the keyboard
      And activating the focused link opens the task
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: The sidebar fits a phone
      Given a viewport 320 px wide
      When the sidebar is shown
      Then each entry stays on one line
      And no horizontal scrolling is needed to read an entry
    ```

- [ ] **NFR-4**

    ```gherkin
    @NFR-4
    Scenario: No new component or dependency
      Given the single-line layout is implemented
      When `frontend/src/App.vue` and `frontend/package.json` are inspected
      Then no entry component was added under `frontend/src/components`
      And no package was added to `frontend/package.json`
    ```

## Conflicts

FEAT-p9 FR-5 requires the web app to show each task's tags in the task list and to filter by selecting a tag on the row.
FEAT-p10 supersedes that requirement for the sidebar entry: a sidebar entry shows no tags.
Tag display belongs to the main tasks list, and the tag filter strip above the sidebar list remains the way to filter by a tag from the sidebar.
Resolved: FEAT-p9's FR-5 and specification were updated to scope tag display to the main tasks list, and its sidebar test now asserts no tag pills.

## Open Questions

None.
