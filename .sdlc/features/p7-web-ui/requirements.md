---
title: "Web single-page app"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: Web single-page app

## Overview

The web app is the primary interface.
It is a Vue 3 single-page application that the API serves (also installable as a PWA), with a task list, a task detail view (context, agent, items, worktrees, timeline), and a settings view.
It is mobile-first and live-updates from the API's SSE streams.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | A fast, keyboard-friendly, phone-friendly view of tasks and agents |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The app shall provide routes for the task list (`/`), task detail (`/task/:id`), and settings (`/settings`). |
| FR-2 | Must | The app shall install as a PWA with a manifest, icons, and a service worker that never caches `/api` (network-only). |
| FR-3 | Must | The app shall be responsive: below 760px the sidebar becomes an off-canvas drawer toggled by a top-bar button. |
| FR-4 | Must | The app shall provide a command palette (Ctrl/Cmd+K) to navigate and to create a task. |
| FR-5 | Must | The task detail view shall live-update from `/api/tasks/{id}/stream`, and the task list shall refresh on changes. |
| FR-6 | Must | The app shall support inline editing of task fields, a new-task modal with GitHub import, and toast notifications. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Should | Accessibility | Icon-only buttons shall carry `aria-label`s. |
| NFR-2 | Should | Performance | The built SPA shall be served by the same process as the API. |
| NFR-3 | Should | Usability | The layout shall be usable down to phone widths. |

## Constraints

- The SPA is built into `backend/static` and served by FastAPI; there is no separate frontend host in production.
- The frontend has no automated tests.

## Acceptance Criteria

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: API is never cached
      Given the service worker is active
      When the app requests a path under /api
      Then the request is handled network-only
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Mobile drawer
      Given a viewport narrower than 760px
      When the app loads
      Then the sidebar is hidden and a menu button toggles it
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Live update on change
      Given the task detail view is open
      When the task changes on the server
      Then the detail view reloads from the task stream
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should the frontend get an automated test setup (component or end-to-end), given none exists?
