---
title: "Source items, associations, and GitHub import"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: Source items, associations, and GitHub import

## Scope

Covers source inference, URL detection, item creation through the API, GitHub issue listing and fetching, and task creation from a GitHub URL.
Out of scope: real network calls to Slack or arbitrary websites.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Infer source from a value | GitHub/Slack/Drive/URL/plain text | correct source, kind, external id |
| TC-2 | URL detection | schemes, bare domains, spaced text | true for URLs, false otherwise |
| TC-3 | Extract owner/repo | https and ssh remotes | correct tuple |
| TC-4 | Parse a `ghx` issue list | sample JSON | normalized issue dicts |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-5 | Create an item through the API | none | source inferred, item stored |
| TC-6 | GitHub issues endpoint | monkeypatched `list_github_issues` | list of issues |
| TC-7 | Single issue endpoint | monkeypatched `fetch_github_issue` | one issue |
| TC-8 | Create a task from a GitHub URL | monkeypatched fetch | title/description prefilled, item associated |
| TC-11 | Mark a Slack thread done and refresh with a newer message | item with a stored `latest_ts` | `done` stays true, `new_since_done` becomes true |
| TC-12 | Mark a thread done before its first fetch | no stored `latest_ts` | first fetch sets the baseline, no new-message flag |
| TC-13 | Reopen a done thread | done item | `done` false, `done_at` cleared, no new-message flag |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-9 | Fetch fails | item still created, no exception |
| TC-10 | `ghx` returns nothing | endpoint returns 502 with a clear detail |

## Test Infrastructure

- `monkeypatch` replaces `services` fetch functions so no real `ghx` call happens.
- `TestClient` for the API; `tmp_path` for git repositories.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-1, TC-5 |
| FR-2 | TC-1, TC-2 |
| FR-3 | TC-5 |
| FR-4 | TC-9 |
| FR-5 | TC-8 |
| FR-6 | TC-5 |
| FR-7 | TC-8 |
| FR-8 | TC-4, TC-6, TC-10 |
| FR-10 | TC-11, TC-12, TC-13 |
| NFR-1 | TC-9 |
