---
title: "Create a task from a Slack thread"
status: done
session_link: "http://localhost:10000/?session=ses_ecf740bfcffeTbPo9DIeiSPyDH"
---

# Test Plan: Create a task from a Slack thread

## Scope

Covers the create-from-Slack path on the API (fetch, associate, dispatch), the agent executor that writes the title and summary, the CLI flag, and the web new-task form.
Out of scope: the live `slackx` fetch and a real ACP harness turn, which the tests stub.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | `extract_summary_json` reads a title and summary | `{"title": "T", "summary": "S"}` | `{"title": "T", "summary": "S"}` |
| TC-2 | `extract_summary_json` tolerates prose and fences | text with a fenced JSON block | the parsed object |
| TC-3 | `extract_summary_json` is lenient about keys | `{"summary": "only"}`, `{"title": "", "summary": " "}`, `"no json"` | summary-only parses; an empty object and no-JSON are `None` |
| TC-4 | `build_summary_prompt` includes the thread | a short conversation | prompt contains the text and the field names |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-5 | Create from a Slack URL associates the item and dispatches the run | a stubbed item fetch and captured dispatch | 201; item linked; a `summarize_slack` run whose prompt contains the thread; `item_added` and `summary_requested` timeline events; placeholder title |
| TC-6 | `generate_title` is passed for the title policy | create with and without a title | the flag is `True` when no title was given, `False` when one was |
| TC-7 | The executor writes the agent's title and summary | a message event with valid JSON | task title, summary, and `context_updated_at` set; `summary_updated` timeline event |
| TC-8 | The executor keeps a user title when told to | `generate_title=False` | title unchanged, summary written |
| TC-14 | The executor keeps the placeholder title on a summary-only reply | a message with `{"summary": "..."}` | title unchanged, summary written, `summary_updated` |
| TC-17 | Startup reconciliation fails stale runs | a queued and a running run | both become failed with the interruption reason; a succeeded run is untouched |

## End-to-End Tests

| ID | Description | Steps | Expected Outcome |
|---|---|---|---|
| TC-9 | Create from the web modal | open the modal, paste a Slack URL into the import field, click Create | `tasks.create` called with the `slack_url`; navigates to the task |
| TC-16 | Paste a GitHub URL into the same field | open the modal, paste a GitHub issue URL | the debounced preview fetches the issue and prefills the title |
| TC-18 | Retry the summary from the API | a task with a Slack thread | a second `summarize_slack` run with the thread in its prompt |
| TC-20 | Retry from the Context panel | a task with a Slack association | the panel offers **Name & summarize** and calls `refreshSummary`; the action is hidden without a Slack thread |
| TC-10 | Create from the CLI | `task create --slack-url <url>` | the request body carries `slack_url` |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-11 | The agent reply is unparseable | the task keeps its placeholder title; a `summary_failed` timeline event is recorded; the task is not deleted |
| TC-12 | The agent falls back to a thought when it sent no message | the summary is still written |
| TC-13 | No title, `github_url`, or `slack_url` on create | 400 |
| TC-15 | The thread could not be gathered (no `slackx` output) | the task is created with a placeholder title; no run is dispatched; a `summary_failed` timeline event records the fetch failure |
| TC-19 | Retry without a Slack thread | 400 |

## Test Infrastructure

- `fastapi.testclient.TestClient` over the app.
- `backend/tests/conftest.py` points `AGENTIC_DATA_DIR` at a temp directory before app import.
- `monkeypatch` stubs `tasks._upsert_item` (no `slackx`), `agents_router._dispatch` (no process spawn), and `agents.execute_run` (no ACP turn).
- Frontend tests mount `App.vue` with a mocked `api` and stubbed child components.

## Test Files

| File | Covers |
|---|---|
| `backend/tests/test_slack_import.py` | TC-1 to TC-6, TC-13, TC-15, TC-18, TC-19 |
| `backend/tests/test_agents_context.py` | TC-7, TC-8, TC-11, TC-12, TC-14 |
| `backend/tests/test_jobs.py` | TC-17 |
| `cli/tests/test_commands_tasks.py` | TC-10 |
| `frontend/src/__tests__/appShell.test.js` | TC-9, TC-16 |
| `frontend/src/__tests__/contextPanel.test.js` | TC-20 |

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-5, TC-13, TC-15 |
| FR-2 | TC-4, TC-5 |
| FR-3 | TC-6, TC-7, TC-8, TC-14 |
| FR-4 | TC-5 (dispatch), TC-7 (write-back) |
| FR-5 | TC-9, TC-16 |
| FR-6 | TC-10 |
| FR-7 | TC-11, TC-12, TC-15 |
| FR-8 | TC-5, TC-7, TC-11, TC-15 |
| FR-9 | TC-17 |
| FR-10 | TC-18, TC-19, TC-20 |
| NFR-1 | TC-5 (item fetch stubbed at the same seam the Items page uses) |
| NFR-2 | TC-5 (no new table; the stub writes a `SourceItem`) |
| NFR-3 | TC-5 (non-empty placeholder title) |
| NFR-4 | Not automated (manual phone-width check of the modal) |
