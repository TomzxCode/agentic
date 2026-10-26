---
title: "Web single-page app"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: Web single-page app

## Scope

Covers the SPA's shell and its wiring: routing, the mobile drawer, the command palette, the focus hints, the new-task modal, toasts, the reactive store, and the `api.js` client with its two SSE stream helpers.
Per-view behavior is covered by the view-specific plans of the features that own those views (gantt, tags, people, metrics, and so on).
The service worker and the PWA install flow are not covered by automated tests; they are verified by hand in a browser.

## Unit Tests (frontend)

| ID | Description | Expected Outcome |
|---|---|---|
| TC-1 | `api.js` request helper handles methods, query params, and errors | requests hit the right URL and method; a non-2xx raises with the API's message |
| TC-2 | `api.js` SSE helpers (`openRunStream`, `openTaskStream`) open the stream, dispatch events, and close on teardown | the EventSource is created for the right URL, the callback receives each event, and unmount closes the source |
| TC-3 | `store.js` reactive state and actions | filters (`status`, `tag`, `person`, group-by) toggle correctly, tags load, toasts queue |
| TC-4 | Command palette builds and runs its items | Ctrl/Cmd+K opens it, items mix actions and tasks, Enter navigates or runs, "This task" items appear on a task page |
| TC-5 | Focus-hint mode (`f` key) | hints render over `.main` controls, a letter keypress focuses the control, Esc exits |

## Integration Tests (frontend, jsdom)

| ID | Description | Expected Outcome |
|---|---|---|
| TC-6 | App shell renders top bar, sidebar, and router view | nav renders, tasks list loads through the store, the new-task modal opens and submits |
| TC-7 | Mobile drawer below 760px | the menu button toggles the off-canvas sidebar; navigation closes it |
| TC-8 | Live update on a task page | a task stream event re-reads the task and re-renders the view |

## Test Infrastructure

- Vitest with jsdom, `pool: 'vmThreads'` (`frontend/vitest.config.js`); shared stubs (ResizeObserver) in `src/test-setup.js`.
- Components mount with `@vue/test-utils`; `RouterLink` is stubbed through mount options, never `vi.stubGlobal('location', ...)`.
- Fetch is stubbed per test; streams are stubbed as EventSource doubles in `api_more.test.js`.
- Run with `make test-frontend` (or `make coverage-frontend` for coverage).

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-2 | (manual browser verification; service worker is not unit-tested) |
| FR-3 | TC-7 |
| FR-4 | TC-4 |
| FR-5 | TC-2, TC-8 |
| FR-6 | TC-1, TC-3, TC-6 |
| FR-7 | TC-5 |
| NFR-1 | asserted inline in view tests (icon-only buttons carry `aria-label`) |
