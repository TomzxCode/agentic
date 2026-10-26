---
title: "Colleague decisions page"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: Colleague decisions page

## Scope

The report parser, discovery, and aggregation in `backend/src/agentic/decisions_store.py`, the `GET /api/decisions` endpoint, the pure helpers in `frontend/src/decisions.js`, and the `DecisionsView.vue` rendering and filters.
Out of scope: the `extract-colleague-decisions` skill that writes the reports.

## Unit Tests

Covered by `backend/tests/test_decisions.py` (store, tmp_path reports) and the helpers half of `frontend/src/__tests__/decisions.test.js`.

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | A report's every section is parsed | the fixture report | day, headline, four decisions in bucket order, cleaned text, permalink forms, supporters, opponents, not-heard names, cross-cutting note |
| TC-2 | The author is dropped from their own support list | "Supported by: Alice Smith, Bob Jones" in Alice's section | supported_by is Bob Jones only |
| TC-3 | Both layouts are discovered, dotfiles skipped, oldest first | dated reports, an ad-hoc file, a dotfile | days sorted ascending, ad-hoc included, dotfile excluded |
| TC-4 | The payload aggregates and deduplicates | a dated report plus an ad-hoc repeat | counts 4/2/2/1, range set, newest-first ordering, not-heard reduced to Erin, cross-cutting kept per report |
| TC-5 | The payload bounds the days | since and until around one report | before since empty, until includes, unbounded includes |
| TC-6 (frontend) | filterDecisions matches search, dates, and buckets | three decisions | each filter narrows as expected, empty bucket selection means all |
| TC-7 (frontend) | decisionCounts totals people and both sides | three decisions | total 3, people 2, supporters 1, opponents 1, per-bucket counts |
| TC-8 (frontend) | groupDecisions orders groups busiest first | three decisions | author, supporter, and opponent groupings with sorted items |
| TC-9 (frontend) | decisionMatrix builds diagonal, pct, and received | three decisions | Alice 50% supported, diagonal 2, Bob's cell 1 at 50%, oppose mode flips the field |
| TC-10 (frontend) | cellDecisions lists a cell's decisions | diagonal and off-diagonal cells | both of Alice's, then only the Deferred one |
| TC-11 (frontend) | shiftDays, pctColor, and nameSlug | dates and percentages | shifted ISO date, hue 0 at 0% and 120 at 100%, stable slug |

## Integration Tests

Covered by `backend/tests/test_decisions.py` (TestClient) and the view half of `frontend/src/__tests__/decisions.test.js`.

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-12 | The endpoint aggregates a configured notes tree | `notes_dir` set to tmp_path with one report | root path, generated_at, reports 1, 4 decisions with parsed fields |
| TC-13 | The endpoint reports a missing root | `notes_dir` pointing at a nonexistent path | root null, reports 0, decisions empty, range null |
| TC-14 | The page lists groups, headlines, and shared sections | payload mocked | author groups with cards, headline, root line, Erin, cross-cutting note |
| TC-15 | The page narrows by search and status chips | payload mocked | one card for the search, one for the Committed chip |
| TC-16 | The page switches to the supporters view | payload mocked | one group headed by the supporter |
| TC-17 | The matrix renders and a cell click lists its decisions | payload mocked | matrix rows, diagonal click opens the detail with both decisions |
| TC-18 | The page restores a remembered tab and ignores an unknown one | localStorage seeded | supporters restored, unknown falls back to By author |
| TC-19 | The page explains a missing notes directory | root null in the payload | the AGENTIC_NOTES_DIR hint is shown |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-20 | A path with no parseable date | the file stem becomes the day (parser fallback, TC-1 fixtures cover the dated path) |
| TC-21 | An unreadable report file | discover_reports skips it and returns the rest (NFR-3, exercised by the store's OSError path) |
| TC-22 | A report naming a person only under Not heard from who later supports a decision | the person leaves the not-heard list (TC-4: Carol is heard, only Erin remains) |

## Test Infrastructure

- Backend: reports are written into a pytest `tmp_path` in the skill's layout; `notes_dir` is monkeypatched per test.
- Frontend: Vitest with `api.decisions.list` mocked; the helper half imports the pure module directly.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-3 |
| FR-2 | TC-1, TC-12 |
| FR-3 | TC-2, TC-1 |
| FR-4 | TC-4, TC-5 |
| FR-5 | TC-12, TC-13 |
| FR-6 | TC-14, TC-16 |
| FR-7 | TC-6, TC-15 |
| FR-8 | TC-9, TC-10, TC-17, TC-18 |
| NFR-1 | TC-12, TC-13 (read-only endpoint and store) |
| NFR-2 | TC-1 to TC-5 run without FastAPI |
| NFR-3 | TC-3, TC-20, TC-21 |
