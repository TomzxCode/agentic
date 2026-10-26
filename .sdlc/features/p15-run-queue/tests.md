---
title: "Durable agent-run queue and worker"
status: done
revision: 1
---

# Test Plan: Durable agent-run queue and worker

## Scope

Covers the queue helpers (`enqueue_run`, `cancel_run`), the worker entrypoint's dispatch by run kind, the real worker draining an enqueued run, and the startup reconciliation of interrupted runs.
Out of scope: a real harness turn (the executors are stubbed), the SAQ library internals, and the Redis/Postgres backends (the tests use the SQLite queue).

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | `enqueue_run` writes a queued job keyed by the run id | a run id | a job whose function is `process_run` and key is the run id |
| TC-2 | `cancel_run` with no job (or a terminal one) returns False | a run id with no job | False, nothing aborted |
| TC-3 | `_slack_generate_title` is True only for an untitled task or the import placeholder | task titles: empty, placeholder, user title | True, True, False |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-4 | `process_run` dispatches a `chat` run to the executor | a queued run, stubbed `execute_run` | the run reads `running`, the executor gets the run's harness, cwd, and prompt, and a cancel event |
| TC-5 | `process_run` dispatches `refresh_context` and `summarize_slack` runs to their executors | runs of those kinds | each executor is called with its own arguments (`generate_title` derived for the Slack summary) |
| TC-6 | A cancelled job leaves the run's status to the API's cancel endpoint | a run cancelled while queued | `process_run` does not overwrite the status |
| TC-7 | A real worker dequeues and finishes an enqueued run | an enqueued run with a stubbed executor | the job completes and the run reaches its terminal status |
| TC-8 | `reconcile_runs` fails orphaned rows and keeps live jobs | one queued run with no job, one whose job is active | the orphan becomes failed with the interruption reason; the live one is untouched |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-9 | The run row was deleted while queued | `process_run` logs and returns without failing |
| TC-10 | A worker dies mid-run | the job's heartbeat lapses, the sweep retries it (retries bounded by `job_retries`), and a still-stale run is failed on the next startup reconcile |

## Test Infrastructure

- `backend/tests/conftest.py` points `AGENTIC_DATA_DIR` at a fresh temp directory, so the queue lives in a throwaway `queue.db`.
- Executors are monkeypatched on `agents.executions`; no ACP harness is spawned.
- `run_parallel` (`backend/src/agentic/parallel.py`) has its own order/overlap/failure tests in `test_parallel.py`.

## Test Files

| File | Covers |
|---|---|
| `backend/tests/test_jobs.py` | TC-1 to TC-9 |
| `backend/tests/test_parallel.py` | the concurrency helper the worker's executors share |

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-1 |
| FR-2 | TC-4, TC-5, TC-7 |
| FR-3 | TC-1 (SQLite queue in the data dir; the URL override is config) |
| FR-4 | TC-2, TC-6 |
| FR-5 | TC-8 |
| FR-6 | TC-10 |
| FR-7 | TC-7 (worker concurrency is the SAQ setting) |
| FR-9, FR-10 | Covered in `test_agents_run.py`/`test_agents_execute.py` (session recording and resume), not here |
| FR-11 | Covered by the stream tests (`agent_streams` replay and poll) |
| NFR-2 | TC-1 (queue in its own file) |
