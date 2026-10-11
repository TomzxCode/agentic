---
title: "Command-line interface"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: Command-line interface

## Scope

Covers output formatting, the client's request shaping, error handling, and the backend command's command surface.
Out of scope: invoking the CLI against a live server end to end.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | JSON output is parseable and ignores text | data plus text, json format | the data is emitted as JSON |
| TC-2 | Text output preserves brackets | text with [open] | brackets preserved |
| TC-3 | Create drops None and posts JSON | partial create args | only set fields sent |
| TC-4 | List passes filters | status and q | query params set |
| TC-5 | Associate an inline item | item dict | POST body shaped correctly |
| TC-6 | Delete returns None on 204 | a 204 response | None |
| TC-7 | Error raises with detail | a 4xx response | ApiError with the detail |
| TC-8 | Client has no server command | — | server lives only on the backend CLI |
| TC-9 | Backend CLI owns serve and info | — | commands registered |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-10 | Empty result set | "(none)" in text mode |

## Test Infrastructure

- `respx`/`TestClient`-style monkeypatching of `httpx` for client tests.
- Direct calls to command functions for output tests.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-8, TC-9 |
| FR-2 | TC-1, TC-2 |
| FR-4 | TC-9 |
| FR-6 | TC-7 |
| NFR-1 | TC-1, TC-2 |
