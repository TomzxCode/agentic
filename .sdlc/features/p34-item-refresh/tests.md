---
title: "Tiered item refresh"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: Tiered item refresh

## Scope

Covers the pure policy module, the due pass and force refresh endpoints, the fetch application rules shared with the single-item refresh, the settings validation, preview, and status endpoints, the background tick, and the Settings Refresh section.
Out of scope: the item model, task associations, and the single-item endpoint's contract details (p2-source-items), and real slackx/ghx subprocesses (fetches are monkeypatched).

## Unit Tests

| ID | Description | File |
|---|---|---|
| TC-1 | `parse_policy` reads bands and the fallback and reports enabled | test_refresh.py |
| TC-2 | Empty text parses to a disabled policy | test_refresh.py |
| TC-3 | A `*=never` fallback stops refresh past the last band | test_refresh.py |
| TC-4 | Malformed policies raise `PolicyError` (out-of-order ages, missing `=`, bad interval, repeated fallback) | test_refresh.py |
| TC-5 | `interval_for_age` selects the band and falls back past the last, or none without a fallback | test_refresh.py |
| TC-6 | `is_due` uses the band, the last fetch, an always-due unfetched item, and a never-due past-band item | test_refresh.py |
| TC-7 | A naive fetch time is treated as UTC | test_refresh.py |
| TC-8 | `parse_duration` reads single units, fractions, and combinations (`1h30m`, `1d4h`, `2w3d`, spaces), and rejects junk (`1h-30m`, `90`, `m`, `0m`) | test_refresh.py |
| TC-9 | `item_start` prefers GitHub `created_at`, then the Slack thread timestamp, then the recorded time | test_refresh.py |
| TC-10 | `policies_from_settings` maps the two settings keys per source and defaults to empty | test_refresh.py |
| TC-11 | `describe_policy` reports the parsed bands for the preview | test_refresh.py |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-12 | Single-item refresh keeps a custom title, rederives an auto one, merges content, and 404s a missing item | app TestClient, fetch monkeypatched | title rules and merge behavior verified through `POST /api/items/{id}/refresh` |
| TC-13 | A refresh-due pass with a failing fetch records the failure and the source status | slack policy set, fetch monkeypatched to error | the item entry carries the error, `fetched_at` stays unset, and the slack status shows the failure |
| TC-14 | A refresh-due pass refreshes exactly the due items and skips them on an immediate second pass | github policy set, fetch monkeypatched | first report refreshes the due item, second reports zero due |
| TC-15 | A refresh-due pass without any policy is a no-op | no policies set | zero checked and refreshed |
| TC-16 | Force refresh ignores the policy and records a manual run | github items, fetch monkeypatched | all URL-bearing items refresh; the status shows origin manual; an unknown source 404s |
| TC-17 | The policy preview endpoint parses and rejects | app TestClient | a valid policy returns its tiers and fallback; an out-of-order one returns `valid: false` with the error |
| TC-18 | The refresh status endpoint reports runs and the 24h sum, including a legacy last-run row | runs recorded directly in settings | per-source counts, origins, and the summed 24h refreshed value |
| TC-19 | The background tick runs the pass and records the outcome | policies set, `main._refresh_due_once` invoked | the status shows a background-origin run; no policy text short-circuits to no work |
| TC-20 | The Settings Refresh section previews, saves, and force refreshes | jsdom mount with mocked API | debounced preview calls, save on blur, force-refresh button per source, and the status line render |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-21 | A fetch fails for one item in a multi-item pass | that item's entry carries the error, others still refresh, and the pass completes |
| TC-22 | A policy with a `never` interval in a band | items in that band are never due |
| TC-23 | A Slack thread marked done before its first fetch | the first fetch sets the done baseline instead of flagging every message as new |
| TC-24 | A file item refreshed after a path change | the reference updates and no content snapshot is kept |
| TC-25 | A listing identical to the stored state | nothing is written and the changed count is zero |

## Test Infrastructure

- `backend/tests/test_refresh.py` exercises the pure module with a fixed `NOW` and `SimpleNamespace` stand-ins for items, no database.
- `backend/tests/test_items_api.py` monkeypatches `fetch_source` (router and `items_refresh._safe_fetch` paths) and inspects `Setting` rows for the recorded statuses.
- `backend/tests/test_settings_api.py` covers the preview, status, and background-tick behaviors, including the legacy status migration.
- `frontend/src/__tests__/settingsView.test.js` mounts the Settings page including the Refresh section with a mocked `api`.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-1, TC-2, TC-3 |
| FR-2 | TC-4 |
| FR-3 | TC-9 |
| FR-4 | TC-5, TC-6, TC-7, TC-22 |
| FR-5 | TC-10 |
| FR-6 | TC-19 |
| FR-7 | TC-13, TC-14, TC-15, TC-16 |
| FR-8 | TC-16 (same endpoints; the CLI command is a thin client covered by the CLI client tests) |
| FR-9 | TC-12, TC-21, TC-23, TC-24 |
| FR-10 | TC-13, TC-18 |
| FR-11 | TC-17, TC-20 |
| FR-12 | TC-25 |
| NFR-1 | TC-1 to TC-11 |
| NFR-2 | TC-13, TC-14 (pool fetches behind the monkeypatched `fetch_source`) |
| NFR-3 | TC-21 |
| NFR-4 | TC-13 |
| NFR-6 | TC-15, TC-19 |
