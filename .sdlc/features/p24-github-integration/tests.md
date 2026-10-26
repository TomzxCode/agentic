---
title: "GitHub read surface: issues, pull requests, My PRs"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: GitHub read surface: issues, pull requests, My PRs

## Scope

Covers the `services/github.py` helpers and their routers (issue fetch, issue listing, issue creation, the whole-repository listing with its item sync), the My PRs search, cache, counts, and poke, and the per-item reviewer read and poke.
Out of scope: real network calls to GitHub or Slack, and the cycle-time reads the metrics feature owns.

## Unit Tests

| ID | Description | File |
|---|---|---|
| TC-1 | Extract (owner, repo) from GitHub URLs, https and ssh remotes, and reject non-GitHub values | test_github.py |
| TC-2 | Parse a `ghx` issue list into normalized issue dicts | test_github.py |
| TC-3 | A PR fetch carries state, draft flag, merged_at, and review decision, and picks the `pr` subcommand | test_github.py |
| TC-4 | Parse a `ghx` PR list with a narrow `--json` field set; none when the CLI fails | test_github.py |
| TC-5 | The combined listing tags kinds, drops issue bodies, reports a one-kind failure, and is none when both fail | test_github.py |
| TC-6 | `refresh_github_cache` calls `ghx cache --force` and is False when it cannot run | test_github.py |
| TC-7 | `_fetch_github` populates title, content, metadata (author and merged_at may be None), and people; it ignores bad URLs and missing issues | test_services_github.py |
| TC-8 | The issue list clamps its limit to at least 1 and returns none when the CLI fails | test_services_github.py |
| TC-9 | A My PRs search node reduces to a row with repository, number, approval state, approvers, ci, and thread counts | test_my_pulls.py |
| TC-10 | Check rollup states map to success, pending (PENDING and EXPECTED), and none | test_my_pulls.py |
| TC-11 | Approvers come from opinionated reviews only; a decision of CHANGES_REQUESTED is not approved | test_my_pulls.py |
| TC-12 | `reviewed` counts anyone but the author, ignores the author's own reviews, and treats an overflowing review page as reviewed; requested reviewers carry logins and team names | test_my_pulls.py |
| TC-13 | `pull_counts` totals, attention, approved, failing, open threads, and drafts | test_my_pulls.py |
| TC-14 | The My PRs cache is reused without refresh, bypassed with refresh, and a failed lookup reports the unreachable error | test_my_pulls.py |
| TC-15 | `fetch_my_pulls` without a login reports the no-login error | test_my_pulls.py |
| TC-16 | Reviewer parsing keeps each reviewer once, keeps the latest decisive state over a later comment, keeps the last review time, marks a re-requested reviewer PENDING, and skips teams | test_item_github_reviewers.py |
| TC-17 | My PRs page helpers: labels, attention ranking, sorting, search, counts, groupings, and filter matching | frontend `myPulls.test.js` |
| TC-18 | `layoutGraph` layers by longest path, stacks independent nodes, drops undrawn edges, and sizes the canvas; `edgePath`; `wrapTitle` | frontend `graph.test.js` |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-19 | Issues endpoint by owner/repo and by registered repository | monkeypatched `ghx` | issues listed; 400 without coordinates; 404 unknown repository; 400 non-GitHub remote; 502 when ghx fails |
| TC-20 | Single issue endpoint | monkeypatched `ghx` | issue returned; 400 for a non-GitHub URL; 502 when the read fails |
| TC-21 | Create issue endpoint | monkeypatched `create_github_issue` | issue created; 400 for a blank title or unresolvable repository; 502 on failure |
| TC-22 | Repository endpoint with refresh | monkeypatched `ghx` | `ghx cache --force` runs first; 502 when both kinds fail |
| TC-23 | Repository listing syncs the items it names | stored item for a listed issue | item's state metadata and author updated; an identical listing writes nothing; other repositories' items untouched |
| TC-24 | My PRs endpoint | login resolved, search monkeypatched | rows and counts returned; the no-login case carries the error |
| TC-25 | My PRs poke | people and Slack monkeypatched | one DM per deduplicated login; per-reviewer failure reasons; 400 with no logins |
| TC-26 | Item reviewers endpoint | PR item, monkeypatched `gh` | reviewers listed with a PENDING request; a non-PR item returns an empty list; a failed read carries the error |
| TC-27 | Item poke | person with Slack aliases, Slack monkeypatched | DM sent without unfurl to the resolved user id; 400 naming the missing person or Slack id; 502 when Slack refuses |
| TC-28 | TaskIssuePanel and the task's issue mode | stored item, monkeypatched API | live GitHub read shown with the agent panel; stored-item fallback; author person links |
| TC-29 | MyPullsView | monkeypatched API | rows rendered with badges, filters, grouping (remembered in localStorage), repository multi-select, refresh, empty and error states |
| TC-30 | Repository detail view and grid | monkeypatched API and store | grid rows with kind, state, author, tasks, and app/ghx links; refresh all; new-task and record-change actions |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-31 | `ghx` returns nothing | endpoints answer 502 with a detail naming `ghx`, never an empty list |
| TC-32 | A pull request with no check rollup or empty commit list | `ci` reads `none` |
| TC-33 | A payload without people, or with no author | metadata stores None rather than failing |
| TC-34 | A reviewer who reviewed before and is asked again | one row, state PENDING, still carrying their last review time |
| TC-35 | A reviewer login repeated in different cases | deduplicated to one DM |

## Test Infrastructure

- `monkeypatch.setattr(shell, "_run_cli", ...)` replaces the CLI boundary, so no test calls `ghx` or `gh`.
- `TestClient` over the FastAPI app for the endpoints; people and Slack dependencies monkeypatched at the router module.
- Frontend Vitest suites stub `api.js` and mount the views; the pure helpers (`myPulls.js`, `graph.js`) are tested directly.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-3, TC-20 |
| FR-2 | TC-2, TC-19 |
| FR-3 | TC-21 |
| FR-4 | TC-5, TC-22 |
| FR-5 | TC-6, TC-22, TC-23 |
| FR-6 | TC-9, TC-10, TC-11, TC-12, TC-24 |
| FR-7 | TC-14, TC-15, TC-24 |
| FR-8 | TC-14 |
| FR-9 | TC-25 |
| FR-10 | TC-28 |
| FR-11 | TC-29, TC-30 |
| FR-12 | TC-16, TC-26 |
| FR-13 | TC-27 |
| NFR-1 | TC-19, TC-20, TC-31 |
| NFR-2 | TC-13, TC-14 |
| NFR-3 | TC-23 |
| NFR-4 | TC-17 |
| NFR-5 | TC-27 (no unfurl), TC-28 (sanitized Markdown) |
