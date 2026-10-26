---
title: "PR reviewer-feedback triage"
status: done
---

# Test Plan: PR reviewer-feedback triage

## Scope

The analysis-file parsing, the decision write, the queue endpoints, and the feedback page.
The skill that produces the files and the executor that consumes the decisions are out of scope; tests build fixture files in the documented format.

## Backend tests

| File | Coverage |
|---|---|
| `backend/tests/test_feedback.py` (8 tests) | Parsing frontmatter and sections into an item, skipping a file without frontmatter, undecided-first ordering with dotfiles skipped, recording a decision and clearing the execution marker on a change, rejecting a write into a file without frontmatter, the list endpoint, the decision endpoint, and the missing-root response |

Specifically:

- `test_parse_feedback_reads_frontmatter_and_sections` covers FR-2: fields, title, sections, and timestamp normalization.
- `test_parse_feedback_skips_a_file_without_frontmatter` covers FR-1's skip rule.
- `test_discover_puts_undecided_first_and_skips_dotfiles` covers FR-5 and the dotfile rule.
- `test_write_decision_records_and_clears_the_execution_marker` covers FR-7 and FR-8: a new decision keeps `executed_at` absent, a changed decision drops a stale one, a reset clears everything.
- `test_write_decision_rejects_a_file_without_frontmatter` covers FR-9's 422 path.
- `test_list_feedback_endpoint` and `test_set_decision_endpoint` cover the API surface, counts, and the derived status and run state (FR-3, FR-4, FR-6, FR-10).
- `test_list_feedback_reports_a_missing_root` covers FR-10's empty-root case.

## Frontend tests

| File | Coverage |
|---|---|
| `frontend/src/__tests__/feedback.test.js` (10 cases) | The helpers and the view: section ordering with named ones first, the thread link extraction, grouping by recommendation and by pull request with PR-linked headings, counts including awaiting-run, the rendered list with recommendation and sections, recording a decision and reflecting it on the card, resetting a decision to null, the closed-PR filter under the active default, the search filter, and the empty state |

## Edge Cases and Failure Scenarios

| Scenario | Expected behavior | Covered by |
|---|---|---|
| File without YAML frontmatter | Skipped as an item; a decision write into it answers 422 | `test_feedback.py` |
| Editor temp file (dotfile) in the feedback directory | Never listed | `test_feedback.py` |
| Unquoted frontmatter timestamp | Read back as ISO-8601 UTC | `test_feedback.py` |
| Re-recording the same decision | `executed_at` survives | `test_feedback.py` |
| Changed decision after execution | `executed_at` dropped, item awaiting again | `test_feedback.py` |
| Unknown feedback id | 404 | `test_feedback.py` |
| Store directory missing | Empty list, null root | `test_feedback.py` |
| ghx unavailable or store key without an owner | PR state unknown, item still rendered | `feedback.test.js` (state filter and card rendering) |

## Test Infrastructure

- `backend/tests/test_feedback.py` builds fixture analysis files under `tmp_path` and monkeypatches the settings store root; endpoint tests use the API client fixtures.
- `frontend/src/__tests__/feedback.test.js` stubs the `api.feedback` module and mounts `FeedbackView` with the shared test setup (`src/test-setup.js`).

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | `test_parse_feedback_skips_a_file_without_frontmatter`, `test_discover_puts_undecided_first_and_skips_dotfiles` |
| FR-2 | `test_parse_feedback_reads_frontmatter_and_sections` |
| FR-3 | `test_list_feedback_endpoint` (pending status), `feedback.test.js` decision flows |
| FR-4 | `test_list_feedback_endpoint` (run states), `test_write_decision_records_and_clears_the_execution_marker` |
| FR-5 | `test_discover_puts_undecided_first_and_skips_dotfiles` |
| FR-6 | `test_list_feedback_endpoint`, `feedback.test.js` PR-state filter |
| FR-7 | `test_write_decision_records_and_clears_the_execution_marker`, `test_set_decision_endpoint` |
| FR-8 | `test_write_decision_records_and_clears_the_execution_marker` |
| FR-9 | `test_set_decision_endpoint` (404), `test_write_decision_rejects_a_file_without_frontmatter` (422), schema validation for the decision literal |
| FR-10 | `test_list_feedback_endpoint`, `test_list_feedback_reports_a_missing_root` |
| FR-11 | `feedback.test.js` view cases: list, pills, sections, decision buttons |
| FR-12 | `feedback.test.js` filter, grouping, and search cases |
| FR-13 | `test_write_decision_records_and_clears_the_execution_marker` (replace-style write observed through re-reads) |
| NFR-1 | Module structure: `feedback_store.py` imports no FastAPI (verified by review, not a test) |
| NFR-2 | `test_set_decision_endpoint` plus the executor contract in the skill's own documentation |
| NFR-3 | No test asserts GitHub writes because none exist; covered by the module split (NFR-1) |
| NFR-4 | Shared `enrich_from_github` cache, exercised by `test_list_feedback_endpoint` stubbing |
