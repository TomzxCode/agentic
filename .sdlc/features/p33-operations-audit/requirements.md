---
title: "Operations audit log and request provenance"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: Operations audit log and request provenance

## Overview

Every request to the API can declare who is behind it through two headers: `x-agentic-client` names the client (`web`, `cli`, or `api`) and `x-agentic-actor` names who drives it (`human` or `agent`).
The provenance middleware keeps those values in a contextvar for the request so handlers stamp the records they write (the task timeline in particular), and it writes each mutating `/api` request to the `Operation` table, the cross-cutting audit log of how work entered the system.
Around that sit the operational observability surfaces: failed requests log their reason through structlog (`RequestErrorMiddleware`), each request's timing and database query counts ride back as debug headers and a small in-memory ring buffer (`DebugMiddleware`), the Settings page's Diagnostics section probes the external commands and caches the app depends on, and the status bar's debug bar shows the web UI its own API, database, and helper-CLI traffic.
There is no SPA page for the operations log; it is read through the HTTP API and the CLI.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | See which client and whether a person or an agent performed each mutating operation, without digging through logs |
| Agent-driven workflow | Have its writes carry `actor: agent` in the timeline and the audit log, so human and machine work stay distinguishable |
| Operator | Know why a failed request failed and whether a missing helper CLI or cache is the cause |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall resolve the `x-agentic-client` and `x-agentic-actor` headers onto the `web`/`cli`/`api` and `human`/`agent` enums, trimming and lowercasing values, and fall back to `api`/`human` for missing or unknown values |
| FR-2 | Must | The system shall keep the resolved provenance in a request-scoped contextvar readable by handlers, with a `using()` override for internal writes |
| FR-3 | Must | The system shall stamp every task timeline event it writes with the request's client and actor |
| FR-4 | Must | The harness environment shall set `AGENTIC_ACTOR=agent` so CLI calls made by a coding agent report `actor: agent` |
| FR-5 | Must | The web UI shall send `X-Agentic-Client: web` and `X-Agentic-Actor: human` on every request, and the CLI shall send `X-Agentic-Client: cli` plus the actor its environment declares |
| FR-6 | Must | The system shall record one `Operation` row (method, path, status code, client, actor, created_at) for every mutating `/api` request (POST, PUT, PATCH, DELETE) and never record reads |
| FR-7 | Must | `GET /api/operations` shall list recorded operations newest first with optional `client` and `actor` filters and a `limit` clamped to 1 through 500 (default 100) |
| FR-8 | Should | The CLI shall expose `agentic operation list` with `--client`, `--actor`, and `--limit` reading the same log |
| FR-9 | Must | `RequestErrorMiddleware` shall log a failed request's method, path, status, duration, and the `detail` from the JSON error body, at error level for 5xx and warning otherwise, with the response body passed through untouched |
| FR-10 | Must | Uvicorn's access log shall be routed through the application's structlog logger in every server process |
| FR-11 | Must | `DebugMiddleware` shall add `x-debug-duration-ms`, `x-debug-db-queries`, and `x-debug-db-time-ms` response headers and keep the last 20 requests with their SQL snippets and helper-CLI calls, excluding `/api/debug` reads from the list |
| FR-12 | Must | `GET /api/debug/requests` shall return the recent request snapshots and `GET /api/debug/cli` (with its aliases) the recent helper-CLI calls |
| FR-13 | Must | The Settings page's Diagnostics section shall probe the Python runtime, git, ghx, gh, slackx, and every configured harness for presence, path, and version, and list the ghx and slackx local caches, via `GET /api/settings/diagnostics` |
| FR-14 | Must | The status bar's debug bar shall aggregate API calls, database queries, and helper-CLI calls with tabs, a text filter, clear actions, and header-derived per-call database stats, polling `GET /api/debug/requests` for server-side snapshots |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Reliability | Recording an operation must never fail the request that produced it; a write error is logged as a warning and dropped |
| NFR-2 | Must | Privacy | The audit row carries only method, path, status, client, and actor; no request bodies, query strings, or person identifiers |
| NFR-3 | Must | Bounded resources | The operations read clamps its limit, the debug ring buffers cap at 20 entries, error bodies stop buffering at 8 KB, and logged details truncate at 500 characters on one line |
| NFR-4 | Must | Availability | Diagnostics probes never hold the Settings page: version probes time out at 5 seconds, cache listings at 30, stdin is closed so a server-style harness cannot hang, and all probes run together in parallel |
| NFR-5 | Should | Consistency | Every log line the server emits for requests goes through structlog, so failures share one format with the rest of the app |
| NFR-6 | Should | Usability | Status bar debug preferences persist in localStorage per the per-device UI convention, and the debug endpoints are excluded from the debug list to avoid self-feedback |

## Constraints

- The middleware stack order in `main.py` is CORS, then `RequestErrorMiddleware`, then `ProvenanceMiddleware`, then `DebugMiddleware`.
- Provenance values come from the caller rather than being guessed; an undeclared request is `api`/`human`.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Header values resolve with fallbacks
      Given headers "CLI" and "HUMAN" with surrounding spaces
      When the provenance is resolved
      Then they map to cli and human
      And missing or unknown values fall back to api and human
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Context is set and restored
      Given the default context of api and human
      When a handler enters the using override with cli and agent
      Then the context reads cli and agent inside the block and api and human after it
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Declared provenance reaches the timeline
      Given a task created with client cli and actor agent, then patched with client web and actor human
      When the timeline is read
      Then the created event carries cli and agent and the updated event carries web and human
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: The harness environment declares the agent
      Given a harness with its own environment variables
      When the harness process environment is built
      Then it additionally carries AGENTIC_ACTOR=agent
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Clients declare themselves
      Given a request from the web UI and a request from the CLI run by a person
      When the requests arrive at the middleware
      Then they carry web/human and cli/human headers respectively
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Only mutating requests are recorded
      Given a POST to /api/tasks and two GETs
      When the operations log is read
      Then the POST appears once with its method, path, status, client, and actor
      And the count is unchanged by the GETs
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Filtered, bounded listing
      Given operations from several clients and actors
      When GET /api/operations is called with client web and actor agent
      Then only matching rows return, newest first, at most the clamped limit
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: The CLI lists operations
      Given a running API
      When agentic operation list runs with client and actor filters
      Then the same filtered rows print newest first in text or JSON form
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: A failed request logs its reason
      Given a handler raising a 400 with a text detail
      When the request fails
      Then a "request failed" entry records method, path, status 400, duration, and the detail
      And a 5xx logs at error level while a 4xx logs at warning level
      And a validation error names the field and a multi-line detail stays one line
      And a successful request logs nothing
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: Access lines go through structlog
      Given the server configured its request logging
      When an access record is emitted
      Then it appears as a structlog event and uvicorn keeps exactly one handler with propagation off
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: Debug headers and ring buffer
      Given any API request
      When the response starts
      Then it carries the duration, query count, and query time headers
      And the request snapshot joins the last-20 list with its SQL snippets and CLI calls
      And a request to /api/debug itself is not added to the list
    ```

- [ ] **FR-12**

    ```gherkin
    @FR-12
    Scenario: Debug reads
      Given recent requests and helper-CLI calls
      When GET /api/debug/requests and GET /api/debug/cli are called
      Then they return the snapshots newest first with stable per-request ids
    ```

- [ ] **FR-13**

    ```gherkin
    @FR-13
    Scenario: Diagnostics probes
      Given a machine with some helper CLIs installed and harnesses configured
      When GET /api/settings/diagnostics is called
      Then every runtime, tool, and harness is listed with present, path, and version
      And the ghx cache lists its repositories with hit rates and the slackx cache lists its counts
      And a missing command reports present=false instead of failing the read
    ```

- [ ] **FR-14**

    ```gherkin
    @FR-14
    Scenario: The debug bar reflects live traffic
      Given the web UI issuing API calls that return debug headers
      When the status bar is expanded
      Then it shows call counts, total durations, database query counts and time, and the per-call details
      And each tab can be cleared and the list filtered without polling
    ```

## Conflicts

None identified yet.

## Open Questions

1. The SPA defines `api.operations.list` but no view consumes it; whether the operations log should get a page in the web UI is a product call the code cannot answer.
2. The retention of `Operation` rows is unbounded; whether an automatic trim is wanted once the log grows is undecidable from the code.
