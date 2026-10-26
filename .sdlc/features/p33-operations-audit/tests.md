---
title: "Operations audit log and request provenance"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: Operations audit log and request provenance

## Scope

Covers provenance resolution and stamping, the operations audit log (API and CLI), failure logging, the debug middleware and endpoints, and the diagnostics probes and their parsers.
Out of scope: real subprocess probes against installed CLIs (monkeypatched), and the task timeline's own content rules.

## Unit Tests

| ID | Description | File |
|---|---|---|
| TC-1 | `resolve` maps declared values (case and whitespace tolerated) and falls back to api/human for missing or unknown ones | test_provenance.py |
| TC-2 | `using` sets and restores the context around a block | test_provenance.py |
| TC-3 | `harness_env` adds `AGENTIC_ACTOR=agent` to the harness environment | test_provenance.py |
| TC-4 | The access log handler routes Uvicorn lines through structlog and replaces the handlers idempotently | test_request_logging.py |
| TC-5 | Probe reports a missing command as not present | test_diagnostics.py |
| TC-6 | A command served by a configured RPC server reports present without a path | test_diagnostics.py |
| TC-7 | Version reads take the first stdout line, fall back to stderr, tolerate no version, close stdin, and report timeouts | test_diagnostics.py |
| TC-8 | `parse_ghx_repositories` reads both ghx row shapes and rows without hit-rate columns | test_diagnostics.py |
| TC-9 | ghx and slackx cache reads report a missing command, a failed listing, and unusable output | test_diagnostics.py |
| TC-10 | Debug request snapshots keep unique, stable ids across reads | test_debug.py |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-11 | Declared headers reach the timeline and the audit log | app TestClient | created event carries cli/agent, updated carries web/human; the operations log lists both writes under their clients |
| TC-12 | Undeclared requests default to api/human | app TestClient | every timeline event reads api and human |
| TC-13 | Reads are never recorded as operations | app TestClient | the log length is unchanged by GETs |
| TC-14 | A failed request logs status and detail with duration; success logs nothing; 5xx logs at error level; validation errors name the field; multi-line details stay one line | standalone FastAPI app with the middleware | structlog capture shows exactly the expected entries with the body passed through |
| TC-15 | `collect_diagnostics` lists runtime, tools, and harnesses and both caches | probes monkeypatched | the report carries every probe position plus the ghx and slackx cache reads |
| TC-16 | The diagnostics endpoint returns the probe results | app TestClient, probes monkeypatched | `GET /api/settings/diagnostics` answers with the collected report |
| TC-17 | `agentic operation list` prints the filtered operations | CLI test harness with a fake client | rows render in text form; filters pass through to the client |
| TC-18 | The CLI client sends the filters to `/api/operations` | fake transport | the request path and query match client/actor/limit |
| TC-19 | The status bar debug bar refreshes, coalesces bursts, tabs, clears, and preserves layout | jsdom mount with mocked performance composable | tab and clear behavior verified without polling |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-20 | An unknown header value such as "desktop" | falls back to api/human |
| TC-21 | The operations write fails (database unavailable) | the request still succeeds; a warning is logged and the row is dropped |
| TC-22 | An error body larger than 8 KB or not JSON | buffering stops or no detail is logged; the response is untouched |
| TC-23 | A harness command that ignores `--version` and starts a server | the probe's closed stdin and timeout kill it; the read completes |
| TC-24 | A request to `/api/debug` itself | it is served and served with headers, but not added to the recent list |

## Test Infrastructure

- `backend/tests/test_provenance.py`, `test_request_logging.py`, and `test_debug.py` use FastAPI `TestClient` apps (the full app for provenance, minimal apps for the middlewares).
- `backend/tests/test_diagnostics.py` monkeypatches `subprocess.run`, `shutil.which`, and the raw CLI runner; structlog's `capture_logs` collects log assertions.
- CLI coverage lives in `cli/tests/test_commands_operations.py` and `cli/tests/test_client.py` with the shared fake client.
- The status bar is covered by `frontend/src/__tests__/statusBar.test.js` under jsdom with the page-load composable mocked.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-1, TC-20 |
| FR-2 | TC-2 |
| FR-3 | TC-11 |
| FR-4 | TC-3 |
| FR-5 | TC-11, TC-12 |
| FR-6 | TC-11, TC-13, TC-21 |
| FR-7 | TC-11, TC-13 |
| FR-8 | TC-17, TC-18 |
| FR-9 | TC-14, TC-22 |
| FR-10 | TC-4 |
| FR-11 | TC-10, TC-24 |
| FR-12 | TC-10 |
| FR-13 | TC-5 to TC-9, TC-15, TC-16, TC-23 |
| FR-14 | TC-19 |
| NFR-1 | TC-21 |
| NFR-3 | TC-10, TC-22 |
| NFR-4 | TC-7, TC-23 |
