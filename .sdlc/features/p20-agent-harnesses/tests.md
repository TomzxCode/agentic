---
title: "Agent harnesses and model selection"
status: done
---

# Test Plan: Agent harnesses and model selection

## Scope

The harness domain module (seeding, default selection, resolution, availability, default model reading), the warm session pool against a fake spawn, the model selection path in the runner, the harness HTTP endpoints, the Settings page harness CRUD wiring, and the CLI harness commands.
Out of scope: an actual ACP harness process (every harness is faked), the worker's queue mechanics (covered by the agent-run feature), and the model picker's rendering inside the task view (no dedicated component test).

## Unit Tests

Backend, file `backend/tests/test_agents_harnesses.py` (pure domain logic, no HTTP):

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Default model reads a plain key | config file with a string `model` | the model string |
| TC-2 | Default model reads an object model and a template | `{"providerID", "model"}` plus a `{a}/{b}` template | `provider/model` |
| TC-3 | Default model resolves to none when the source cannot answer | missing file, bad JSON, non-dict, unfilled placeholder | `None`, never a guess |
| TC-4 | Availability reports missing and present commands | command absent or present on PATH | `(false, reason)` or `(true, path)` |
| TC-5 | Seeding populates presets with resume commands and a default | empty table | three presets, one default, marker set |
| TC-6 | Seeding picks OpenCode v1 when v2 is absent | `opencode2` not on PATH | `opencode` is default |
| TC-7 | Seeding adds missing presets without overwriting custom edits | edited `opencode` row plus a missing preset | preset inserted, edit untouched |
| TC-8 | An OpenCode default moves to v2 | v1 default, v2 now installed | v2 becomes the single default |
| TC-9 | A default outside the OpenCode family is kept | `pi` is default at first seed | `pi` stays default |
| TC-10 | A default chosen later is never overridden | marker set, user default | user default stays |
| TC-11 | Resume command backfill by id then name | old rows without `resume_command` | filled from `RESUME_DEFAULTS` |
| TC-12 | `get_harness` prefers explicit id, then default flag, then settings name, then first row | various table states | harness in that order |
| TC-13 | `get_harness` raises on an empty table | no rows | `RuntimeError` |

Backend, file `backend/tests/test_agents_run.py` (model selection, faked ACP connection):

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-14 | `_apply_model` selects the configured model | fake conn recording `set_config_option` | called with `("model", session, value)`; a response without options still names the requested model; no model sends nothing |
| TC-15 | `_apply_model` reports a harness that rejects it | conn raises method-not-found | `(None, message)` with the harness's error surfaced |
| TC-16 | `session_model` reads the model config option | option by id, by category, unrelated option, none | the value, or `None` for anything else |
| TC-17 | A run selects the model over ACP, not a CLI flag | harness with model, fake spawn | `set_config_option` called; spawned argv carries no model flag |
| TC-18 | A run reports the model the session already uses | session reports a model, no model requested | run records the reported model |
| TC-19 | Session acquisition creates, resumes, and falls back | resume id present or not, resume failing | resume keeps context; a failed resume starts a new session |
| TC-20 | Model choices flatten a grouped select | nested provider groups | flat `{value, name}` list |
| TC-21 | A run prefers its model override | `requested_model` and harness model differ | the override is applied |
| TC-22 | `model_name` and run recording of the label | choices with a matching value | the harness's label is recorded and emitted |

## Integration Tests

Backend, file `backend/tests/test_agent_api.py` (endpoints through the FastAPI test client):

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-23 | Harness list reports availability and a single default | seeded table | each row has `available` and exactly one default |
| TC-24 | A harness reports the default model its config file names | config file in a temp dir | `default_model` in the response |
| TC-25 | Setting a default demotes the others | two harnesses | PATCH with `is_default` leaves one default |
| TC-26 | Harness CRUD and delete detaches a task | harness used by a task | delete returns 204 and the task keeps running with no harness |
| TC-27 | Models endpoint returns what the harness offers | fake pool injected | choices, current, live, and error passthrough |
| TC-28 | Run create records the requested model | POST with `model` | `requested_model` stored on the run |

Backend, file `backend/tests/test_agents_pool.py` (async unit with a fake spawn):

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-29 | A warm session reads the models the harness offers | fake spawn, fake conn | choices and current model captured at open |
| TC-30 | The pool answers the default harness from the session it holds | held session alive | `live: true` answer |
| TC-31 | A harness the pool does not hold is read on demand and reused | non-default harness, two calls | one short-lived session, second call cached |
| TC-32 | The pool reports a harness that will not start | spawn raises | `error` set, no exception escapes |
| TC-33 | The pool closes a harness that fails after it starts | initialize raises | process closed, no leak |
| TC-34 | The pool closes the process when an open is cancelled | cancel during open | process closed |
| TC-35 | The loop keeps a session up for the default harness | background loop with fake DB | session held, reopened on fingerprint change, backoff on failure |
| TC-36 | The fingerprint changes with command, args, model, and env | each field mutated | fingerprint changes |

Frontend and CLI:

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-37 | The Settings page wires harness create and update | `frontend/src/__tests__/settingsView.test.js` | the API mocks receive the form values |
| TC-38 | CLI harness commands | `cli/tests/test_commands_smoke.py` | `harness list`, `create`, `update`, `delete` render and call the client |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-39 | A config file that cannot answer | missing file, missing key, unfilled placeholder, malformed source all give no default model, no error raised (the 1 MB size guard itself is not exercised by a test) |
| TC-40 | A harness without a model option (method not found) | transcript warning, run continues with the harness default |
| TC-41 | A session whose resume fails | a new session is started and the run proceeds |
| TC-42 | A cancelled pool open | the spawned process is still closed |
| TC-43 | An empty harness table | `get_harness` raises instead of returning `None` |

## Test Infrastructure

- `backend/tests/conftest.py` sets `AGENTIC_DATA_DIR` to a fresh temp dir per process and `AGENTIC_WARM_HARNESS_SESSION=0`, so no test spawns a harness pool.
- `test_agents_pool.py` and `test_agents_run.py` inject fake spawn/connection objects (`FakeSpawn`, `FakeConn`, `FakeProcess`) instead of ACP processes.
- `test_agents_harnesses.py` writes throwaway config files with `tmp_path` and monkeypatches `shutil.which` for availability and default preference.
- The API tests use the FastAPI test client against a temp data dir and inject a fake pool where the models endpoint is exercised.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-5, TC-7, TC-11 |
| FR-2 | TC-5, TC-6, TC-8, TC-9, TC-10 |
| FR-3 | TC-4, TC-23, TC-24, TC-26, TC-38 |
| FR-4 | TC-25 |
| FR-5 | TC-26 |
| FR-6 | TC-14, TC-17 |
| FR-7 | TC-14, TC-21 |
| FR-8 | TC-15, TC-40 |
| FR-9 | TC-16, TC-18, TC-22 |
| FR-10 | TC-27, TC-29, TC-30, TC-31, TC-32 |
| FR-11 | TC-33, TC-34, TC-35, TC-36, TC-43 |
| FR-12 | TC-1, TC-2, TC-3, TC-24, TC-39 |
| FR-13 | TC-37 |
| FR-14 | TC-38 |
| NFR-1 | TC-3, TC-39 |
| NFR-2 | TC-32, TC-35 |
| NFR-3 | TC-15, TC-40 |
| NFR-4 | TC-17 (env merged in `harness_env`) |
| NFR-5 | Test infrastructure (conftest) |
