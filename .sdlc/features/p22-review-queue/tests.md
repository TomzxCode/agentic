---
title: "Pull-request review queue"
status: done
---

# Test Plan: Pull-request review queue

## Scope

The store read, the ghx enrichment, the background scan, and the findings, on the backend and in the SPA.
The review skills themselves and their report format are out of scope; tests build store fixtures that follow the documented layout instead of running any skill.

## Backend tests

| File | Coverage |
|---|---|
| `backend/tests/test_review_scan.py` (12 tests) | Cadence parsing including the off spellings, the due check, repository policy resolution, the two searches merged with requested winning and excluded authors dropped, one failing search tolerated, both searches failing returns None, replace-set storage preserving `first_seen_at`, a failed scan keeping the stored set, the scan skipped when the cadence is off, the scan endpoints and the queue union, the per-repository policy PATCH, and a manual scan recording a gh failure |
| `backend/tests/test_review_queue.py` (20 tests) | Store collection with markers and the view cache, the view cache's review line reading as a review decision, in-progress markers shown and ignored for other commits, a running step with no report yet, a marker matched against ghx's newer head, staleness of a step behind the newest commit, `reviewed_at` as the newest report, a commitless alias still reporting its verdict, the bare repository layout, the chain gating in `determine_stale_steps`, the red/yellow/green readiness signal, the queue endpoint, the tracked-item merge, task ids riding along (and absent when the item has no tasks), the task-scoped queue (populated and empty), live fields from ghx, and concurrent lookups |
| `backend/tests/test_reviews.py` (8 tests) | Directory resolution with different owner casing, the bare-repo fallback, listing reports newest first with skill and commit tags, report-name splitting, path-traversal rejection, truncation of a large report, and the item reviews endpoints |
| `backend/tests/test_review_findings.py` (10 tests) | Severity ordering across state files, entries without a severity skipped, an empty list without a review directory, tolerant reading of an invalid YAML file, the findings endpoint, a recorded decision read back, a line-preserving single-entry write, decision replacement, an all-or-nothing batch with a missing finding, and the decisions endpoint |

## Frontend tests

| File | Coverage |
|---|---|
| `frontend/src/__tests__/reviewQueue.test.js` (42 cases) | The ReviewsView page: empty states, rows grouped by repository with their step state, running-step spinners, person and repository links, scan-found and already-reviewed and already-approved marks, opening a report from a step cell, and the import action |
| `frontend/src/__tests__/reviews.test.js` (44 cases) | The queue helpers: grouping report files by commit, review labels, marker stripping, verdict labels and tones, and the filter and sorting helpers the view composes |
| `frontend/src/__tests__/taskReviewPanel.test.js` (12 cases) | The task's PR panel: rows for linked pull requests, the stored fallback when GitHub cannot be read, opening step reports, the findings list inline, sending findings to an agent, and keeping the agent panel when the queue cannot be read |
| `frontend/src/__tests__/reviewFindings.test.js` (7 cases) | Finding identity keys, severity grouping, the default selection rule (open must and should, recorded decisions winning), and prompt building |
| `frontend/src/__tests__/shareFindingsModal.test.js` (5 cases) | Reading findings and sending them, importing a task first, the no-findings message, recording skip on uncheck, and select-all recording include |
| `frontend/src/__tests__/settingsReviewScan.test.js` (2 cases) | Saving the review SLO and the review nudge SLO on blur |

## Edge Cases and Failure Scenarios

| Scenario | Expected behavior | Covered by |
|---|---|---|
| gh missing or unauthenticated | Error recorded, stored set untouched | `test_review_scan.py` |
| One of the two searches fails | The other search's results still store | `test_review_scan.py` |
| In-progress marker for an older commit | Ignored | `test_review_queue.py` |
| Report alias without a commit | Verdict credited, no commit | `test_review_queue.py` |
| ghx unavailable | Queue renders from store snapshots | `test_review_queue.py`, `test_taskReviewPanel.test.js` |
| Report path escaping the directory | 404 | `test_reviews.py` |
| Report over 1 MB | Truncated with a flag | `test_reviews.py` |
| State file that is not valid YAML | Read tolerantly, findings kept | `test_review_findings.py` |
| Decision batch with one unknown finding | 404, nothing written | `test_review_findings.py` |
| Store directory under a differently cased owner or repo | Still resolved | `test_reviews.py`, `test_review_queue.py` |

## Test Infrastructure

- `backend/tests/conftest.py` points `AGENTIC_DATA_DIR` at a fresh temp dir per process; the review tests monkeypatch `settings.sdlc_dir` to a fixture store built under `tmp_path`.
- Scan tests stub `shell._run_cli` for `gh search prs` and use the `session` fixture for the database; enrichment tests stub `fetch_github_issue` (ghx).
- Frontend tests mount the components with stubbed `api` modules and the shared test setup (`src/test-setup.js`).

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | `test_review_scan.py`: search merge, requested priority, author filter |
| FR-2 | `test_review_scan.py`: cadence parsing, due check, off skip |
| FR-3 | `test_review_scan.py`: replace-set storage, first_seen_at kept |
| FR-4 | `test_review_scan.py`: failing scan keeps set, one failing search tolerated, both failing |
| FR-5 | `test_review_scan.py`: include_repository, policy PATCH |
| FR-6 | `test_review_scan.py`: stored set minus excluded repositories |
| FR-7 | `test_review_scan.py`: scan endpoints, failure recorded |
| FR-8 | `test_review_scan.py`: policy PATCH; settings validation is exercised through the settings router |
| FR-9 | `test_review_queue.py`: bare layout, collection; `test_reviews.py`: casing, fallback |
| FR-10 | `test_review_queue.py`: markers and view cache, alias verdict, reviewed_at |
| FR-11 | `test_review_queue.py`: marker shown, other commit ignored, no report yet, newer head |
| FR-12 | `test_review_queue.py`: stale step, chain gating |
| FR-13 | `test_review_queue.py`: readiness signal, endpoint status fields |
| FR-14 | `test_review_queue.py`: ghx fields overlay |
| FR-15 | `test_review_queue.py`: tracked-item merge, task ids, no tasks |
| FR-16 | `test_review_scan.py`: queue union; `reviewQueue.test.js`: scan-found mark |
| FR-17 | `test_reviews.py`: read, traversal, truncation; `test_review_queue.py`: task-scoped endpoint |
| FR-18 | `test_review_queue.py`: lookups run together, cache reuse in enrichment |
| FR-19 | `test_review_findings.py`: ordering, severity filter, empty, tolerant read, endpoint |
| FR-20 | `test_review_findings.py`: single-entry write, replacement, all-or-nothing, decisions endpoint |
| FR-21 | `reviewQueue.test.js`, `reviews.test.js` |
| FR-22 | `reviewFindings.test.js`, `shareFindingsModal.test.js`, `taskReviewPanel.test.js` |
| FR-23 | `settingsReviewScan.test.js` |
| NFR-1 | `test_review_queue.py`: concurrent lookups, cache behavior |
| NFR-2 | `test_review_queue.py`: ghx failure fallback; `test_review_scan.py`: failed scan |
| NFR-3 | `test_reviews.py`: traversal rejection |
| NFR-4 | `test_review_scan.py`: first_seen_at preserved across scans |
