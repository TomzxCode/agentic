---
title: "Inbox: derived suggestions"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: Inbox: derived suggestions

## Scope

The pure suggestion rules in `backend/src/agentic/inbox.py`, the `GET /api/inbox` endpoint in `backend/src/agentic/routers/inbox.py`, and the `InboxView.vue` actions.
Out of scope: the endpoints the actions call (covered by their own features) and the review scan that produces the stored review requests.

## Unit Tests

Covered by `backend/tests/test_inbox.py` (pure rules, no database).

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | A task with one merged PR gets close and record-change suggestions in order | open task, merged PR, link | `close_task_finished_items` then `record_change_merged_pr`, with the right reasons and actions |
| TC-2 | A recorded change suppresses the record suggestion | same plus a change whose external ref matches the PR | only the close suggestion |
| TC-3 | Two merged PRs are each offered a change and the task is offered closing | two merged PRs | close suggestion with the "all 2 linked" reason plus two record suggestions |
| TC-4 | A closed issue offers closing | open task, closed issue | close suggestion with reason "Issue #7 is closed." |
| TC-5 | An open issue keeps the task out of the close suggestion | open task, open issue | no suggestions |
| TC-6 | A PR closed without merging still offers closing | open task, PR state CLOSED | close suggestion with reason "PR o/r#5 is closed." |
| TC-7 | A closed issue plus a merged PR are offered for closing | mixed links | close plus one record suggestion |
| TC-8 | A task with no GitHub item is left alone | note item only | no suggestions |
| TC-9 | Only the viewer's merged PRs are offered a change | viewer login set, one own PR and one other's | close plus one record suggestion for the viewer's item |
| TC-10 | An unknown viewer does not filter by author | empty viewer login | both record suggestions |
| TC-11 | A PR with no stored author is not treated as the viewer's | author missing | record suggestion hidden |
| TC-12 | An open PR is not merged | PR state OPEN | no suggestions |
| TC-13 | A done task is not offered closing but still records a change | done task, merged PR | only `record_change_merged_pr` |
| TC-14 | An archived task is left alone entirely | archived task, merged PR | no suggestions |
| TC-15 | A closed task with an active worktree is offered pruning, a removed one is not | done task, worktree active then removed | suggestion appears, then disappears |
| TC-16 | An open task keeps its worktree | open task, active worktree | no suggestions |
| TC-17 | Suggestions are ordered by kind rank | mixed state across two tasks | close, record, worktree order |
| TC-18 | A PR past the review SLO is suggested | request first seen 2d 3h ago, SLO 1d | `review_pr_past_slo` with wait, SLO, and `open_url` action |
| TC-19 | A PR within the SLO is left alone | first seen 2h ago | none |
| TC-20 | The review SLO is off when unset | SLO null | none |
| TC-21 | Reviewed, draft, and merged requests are skipped | three requests | none |
| TC-22 | A naive first-seen time reads as UTC | naive datetime | suggestion still produced |
| TC-23 | An unreviewed PR past the nudge threshold is suggested with its reviewers | own PR with two requested reviewers | `poke_pr_no_reviews` carrying the two logins, with an `open_pr` action |
| TC-24 | A PR with no requested reviewer goes in its own kind | no reviewers | `find_pr_reviewer`, empty `reviewers`, only `open_pr`, reason says no reviewer is requested |
| TC-25 | Reviewed, draft, unaged, and undated PRs are left alone | four pulls | none |
| TC-26 | The nudge threshold is off when unset | threshold null | none |

## Integration Tests

Covered by `backend/tests/test_inbox.py` (TestClient against the app and its database) and `frontend/src/__tests__/inbox.test.js` (mounted view with a mocked API).

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-27 | The endpoint lists a close suggestion for a merged PR and drops it after the task is closed | task plus merged PR created through the API | `GET /api/inbox` returns both suggestions, then only the record suggestion after the patch |
| TC-28 | The endpoint hides a change for a PR the viewer did not author | `github_login` setting set | only the close suggestion |
| TC-29 | The endpoint offers the two unreviewed PR kinds and stops when the nudge is off | My PRs read and nudge SLO monkeypatched, one PR with a reviewer and one without | `poke_pr_no_reviews` with reviewers and `find_pr_reviewer`, then none |
| TC-30 | The endpoint flags a PR past the review SLO from stored data | stored review request, `review_slo` setting | `review_pr_past_slo` with the task fields empty |
| TC-31 | The page shows inbox zero when nothing is suggested | empty report | "Inbox zero" text |
| TC-32 | The page closes a task through its action and reloads | close suggestion mocked | task update called, then inbox zero |
| TC-33 | The page records a change from the stored merge time | item with `merged_at` | change created accepted with the PR external ref, no refresh call |
| TC-34 | The page removes a leftover worktree | worktree suggestion mocked | worktree remove called |
| TC-35 | The page lists the reviewers with a poke each and pokes one | poke report mocked | `review-person` rows per requested login, `myPulls.poke` called with that login, success toast |
| TC-36 | The page reports why a reviewer could not be poked | failed poke report | error toast carries the failure reason |
| TC-37 | The page keeps an unreviewed PR with no reviewer in its own section | `find_pr_reviewer` mocked | "Find a reviewer" section, no reviewer rows and no poke button, both links to the PR page |
| TC-41 | The page shows a tab per kind present, with counts, and narrows the list to the picked one | review and close suggestions mocked | `All`, `Reviews past SLO`, and `Close finished tasks` tabs; picking close leaves only its section and row |
| TC-42 | The page falls back to All when the picked kind empties | close suggestion, picked tab, then a reload with only a review suggestion | `All` is selected again and the review suggestion renders |
| TC-43 | The page shows no tabs when the inbox is empty | empty report | no tab bar |
| TC-44 | The page remembers the picked tab across visits | close suggestion, picked tab, remounted view | stored under `agentic.inboxTab`, the reopened page selects that tab and shows only its section |
| TC-45 | A stored tab that is not a known kind is ignored | `agentic.inboxTab` set to an unknown string | `All` is selected |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-38 | Naive timestamps from SQLite | read as UTC, suggestion still produced (TC-22) |
| TC-39 | A pull request the app just found | within the SLO, not suggested (TC-19) |
| TC-40 | A failed My PRs read | the inbox renders without poke suggestions (router behavior, asserted via TC-29's monkeypatched variants) |

## Test Infrastructure

- Backend: pure functions are called with hand-built `Task`, `SourceItem`, `Worktree`, `Change`, and `ReviewRequest` rows; endpoint tests use `TestClient(app)` with the shared temp data directory and clean up their rows.
- Frontend: Vitest with the API module mocked per endpoint and the store's loaders stubbed.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-17 |
| FR-2 | TC-4, TC-5, TC-6, TC-7, TC-8, TC-13, TC-14, TC-31, TC-32 |
| FR-3 | TC-1, TC-2, TC-3, TC-9, TC-10, TC-11, TC-12, TC-13, TC-27, TC-28, TC-33 |
| FR-4 | TC-15, TC-16, TC-34 |
| FR-5 | TC-18, TC-19, TC-20, TC-21, TC-30 |
| FR-6 | TC-23, TC-24, TC-25, TC-26, TC-29, TC-35, TC-36, TC-37 |
| FR-7 | TC-27, TC-15 |
| FR-8 | TC-31, TC-32, TC-34 |
| FR-9 | TC-33 |
| FR-10 | TC-41, TC-42, TC-43, TC-44, TC-45 |
| NFR-1 | TC-1 to TC-26 run without a database |
| NFR-3 | TC-22, TC-29 |
