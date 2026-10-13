---
title: "Agent runs and context refresh"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: Agent runs and context refresh

## Scope

Covers harness seeding and availability, context-JSON extraction, the context prompt, and session-link building.
Out of scope: spawning a real harness process (integration with opencode/pi), which is not exercised in the test suite.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Extract clean JSON | a bare JSON object | parsed summary and next steps |
| TC-2 | Extract JSON from prose | text around the object | parsed object |
| TC-3 | Extract JSON from a code fence | fenced json | parsed object |
| TC-4 | Repair truncated JSON | a cut-off payload | parsed object |
| TC-5 | Ignore braces in thoughts when JSON is present | thought text with braces | the JSON object is used |
| TC-6 | Return none without a summary | JSON lacking summary | None |
| TC-7 | Session links without config | session id, no config | empty or command-only links |
| TC-8 | OpenChamber and terminal links | configured base and template | both links built with placeholders filled |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-9 | Harnesses are seeded | fresh database | opencode2, opencode, and pi present, exactly one marked default |
| TC-10 | Context prompt includes a group | task with a group | prompt lists the group's repositories |
| TC-11 | Backend CLI reports harness availability | fresh database | info prints harnesses |
| TC-13 | Model applied over ACP | harness with a model | `session/set_config_option("model")` is called and no `--model` flag is passed; a rejecting harness emits a warning event and the run continues |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-12 | Agent reply has no JSON | "context_refresh_failed" timeline event |

## Test Infrastructure

- `monkeypatch` for harness listing where needed.
- `TestClient` and a fresh temp database per test.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-9, TC-11 |
| FR-2 | TC-9, TC-13 |
| FR-4 | TC-1, TC-2, TC-3, TC-4, TC-5, TC-6 |
| FR-6 | TC-1, TC-10, TC-12 |
| FR-7 | TC-7, TC-8 |
