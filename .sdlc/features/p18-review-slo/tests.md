---
title: "Review SLO"
status: done
revision: 1
---

# Test Plan: Review SLO

## Scope

Covers the `review_slo` setting (storage, validation, environment default), the inbox's review suggestions (`build_review_suggestions`), and the settings field and inbox section in the SPA.
Out of scope: the review scan itself, which owns `ReviewRequest` rows and is specified in `p22-review-queue`; the reviewer-nudge suggestion (`poke_pr_no_reviews`), specified in `p28-inbox`.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | `configured_review_slo` parses the setting with the shared duration grammar | `8h`, `1d`, `off`, blank, missing | the parsed timedelta, or None when off |
| TC-2 | `build_review_suggestions` filters and times the suggestions | `ReviewRequest` rows past and within the SLO, a reviewed one, a draft, a closed one | only `requested`, non-draft, open rows whose `ready_for_review_at` wait (or `first_seen_at` when absent) strictly exceeds the SLO |
| TC-3 | The suggestion payload | a request past the SLO | id and kind `review_pr_past_slo:<repo>:<n>`, the wait and SLO in the reason, repository, number, title, url, and the `Review PR` `open_url` action, with no task |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-4 | A pull request past the SLO is suggested; one within it is not; unset disables | stored `ReviewRequest` rows with fixed first-seen times | the matching suggestions only |
| TC-5 | The suggestion disappears when the row leaves the scan | a row the scan no longer stores | no suggestion on the next inbox read |
| TC-6 | `PATCH /api/settings` validates the SLO | `review_slo: "soon"` | 422 naming `review_slo`; `8h` reads back in effective, overrides, and defaults |
| TC-7 | The inbox endpoint flags a review past the SLO | `review_slo` set, a stored request past it | the endpoint returns the `review_pr_past_slo` suggestion, and clearing the setting removes it |
| TC-8 | Reviews lead the inbox | a review suggestion and task suggestions | the review sorts before the task suggestions (`KIND_RANK`) |
| TC-13 | The queue flags a row past the SLO, and only that row | `review_slo` set, scan rows past and within it, one dated by `ready_for_review_at` and one by `first_seen_at`, plus a reviewed, a draft, and a merged one | both past open requested rows carry `slo_wait_seconds` and `slo_seconds`; the rest carry null |
| TC-15 | The wait counts from the ready for review event | first seen an hour ago but ready for review two days ago, and the reverse | the first is suggested, the second is not |

## End-to-End Tests

| ID | Description | Steps | Expected Outcome |
|---|---|---|---|
| TC-9 | Save the SLO from the settings section | mount `SettingsReviewScan`, type `2d`, blur | `settings.update` called with `{review_slo: "2d"}` |
| TC-10 | The inbox section | mount `InboxView` with a past-SLO suggestion | the "Reviews past SLO" section lists it, with the title and action linking to the pull request |
| TC-14 | The queue highlight, edge tooltip, and header count | mount `ReviewsView` with one highlighted row and one plain | the row is tinted and carries one colored edge with no badge, the edge's tooltip states the wait and SLO, and the header counts it |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-11 | A stored `first_seen_at` without a timezone | read as UTC before comparing |
| TC-12 | A request with an empty url or title | the suggestion falls back to `PR <repo>#<n>` and the constructed GitHub url |

## Test Infrastructure

- `backend/tests/conftest.py` provides the TestClient with a temp data directory; review rows are written directly, so no scan runs.
- Frontend tests mount the components with a mocked `api`.

## Test Files

| File | Covers |
|---|---|
| `backend/tests/test_review_scan.py` | TC-1 (and the scan that owns `first_seen_at`) |
| `backend/tests/test_inbox.py` | TC-2 to TC-5, TC-7, TC-8, TC-11, TC-12, TC-15 |
| `backend/tests/test_review_queue.py` | TC-13 |
| `backend/tests/test_review_scan.py` | TC-13, TC-15 (the timeline read that supplies `ready_for_review_at`) |
| `backend/tests/test_settings_api.py` | TC-6 |
| `frontend/src/__tests__/settingsReviewScan.test.js` | TC-9 |
| `frontend/src/__tests__/inbox.test.js` | TC-10 |
| `frontend/src/__tests__/reviewQueue.test.js` | TC-14 |

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-1, TC-6, TC-9 |
| FR-2 | TC-4 |
| FR-3 | TC-2, TC-8, TC-15 (ready-for-review wait, with the first-seen fallback) |
| FR-4 | TC-2 |
| FR-5 | TC-3, TC-10 |
| FR-6 | TC-5, TC-7 |
| FR-7 | TC-6, TC-9 |
| FR-8 | TC-8 |
| FR-9 | TC-13, TC-14 |
| NFR-1 | TC-4 (no new table; the scan's existing row gains the ready-for-review time) |
| NFR-2 | Not automated (manual phone-width check) |
| NFR-3 | TC-1 (the shared duration parser) |
