---
title: "Command-line interface"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: Command-line interface

## Overview

Two commands make the app drivable without a browser.
`agentic` is a scriptable client that talks to a running API over HTTP, so people and agents can create and maintain tasks, items, links, worktrees, runs, and context.
`agentic-server` runs and inspects the backend itself.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Drive the app from a shell and script it |
| Coding agent | Create and maintain content through a stable HTTP client |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The `agentic` command shall expose resources for task, item, link, repository, worktree, run, context, harness, settings, and health. |
| FR-2 | Must | The CLI shall output JSON when stdout is not a terminal or when `--format json` is given, and human-readable text otherwise. |
| FR-3 | Must | The CLI shall accept `--api-url` (or `AGENTIC_API_URL`) and `--timeout`, defaulting to `http://127.0.0.1:8600`. |
| FR-4 | Must | The `agentic-server` command shall serve the API (with `--host`, `--port`, `--reload`) and report configuration and harness availability via `info`. |
| FR-5 | Must | The CLI shall stream a run's events live (`run stream`) and block until a run finishes (`run wait`). |
| FR-6 | Must | The CLI shall report API errors as a one-line message on stderr with a non-zero exit code, and 130 on interrupt. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Should | Usability | Output shall not be wrapped or have markup interpreted, so piped JSON stays valid and bracketed text stays literal. |
| NFR-2 | Should | Maintainability | The client shall be a thin layer over the HTTP API, not touch the database. |
| NFR-3 | Should | Usability | Command groups shall be discoverable from `agentic --help`. |

## Constraints

- The client requires a running API; it does not start one.
- The `agentic` and `agentic-server` commands come from two separate packages (`agentic-cli` and `agentic`).

## Acceptance Criteria

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: JSON when piped
      Given stdout is not a terminal
      When a command runs
      Then the output is valid JSON
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: API error handling
      Given the API returns an error
      When a command runs
      Then a one-line error is printed to stderr
      And the exit code is non-zero
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Bracketed text stays literal
      Given text containing [open]
      When the CLI renders it
      Then the brackets are preserved verbatim
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should the CLI gain a `--wait` flag on `run create`, or keep wait as a separate command?
