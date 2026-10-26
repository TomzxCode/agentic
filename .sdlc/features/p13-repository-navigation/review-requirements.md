---
artifact: requirements
verdict: changes-requested
reviewed_at: 2026-10-12
session_link: http://localhost:10000/?session=ses_ed1823a65ffe7LJmF4SEXBZr08
---

# Review: Requirements — Repository navigation

No blocking findings.

Scoped re-review after revision 1 (see "Scoped re-review after a revision" in `skills/sdlc/references/shared.md`).
Evidence note: this is a document review, so every claim is cited from the artifact, its cross-referenced requirements, or the code (`L1 - Cited`); no behavioral claim is executed.
The verdict is a pass, but the artifact is a document (not a runtime behavior), so the `L3 - Executed` / `L4 - Reproduced` floor does not apply.

## Prior findings — confirmation

Every finding from the previous `changes-requested` review is addressed in the revision, including the single blocking one.

- [x] **[blocking] Conflicts — FR-3 + FR-4 vs FR-5** (acceptance-criteria contradiction). FR-5 is now scoped to "A GitHub issue or PR item" and states that "an item of another kind (for example a GitHub commit or a plain URL) or one whose URL matches no registered repository shall not appear on the Repositories page or on any repository detail view". The two new FR-5 scenarios ("An item with no matching repository is excluded", "A non-issue GitHub item is excluded") assert the same. Resolved as suggested.
- [x] **[advisory] Clarity — stale Open Questions.** The section now carries only the import question (the former OQ4), with the resolved ones (live open/closed state, no-remote repositories, Settings management removal) recorded as settled. OQ1–OQ3 are closed.
- [x] **[advisory] Clarity — FR-5 "Resources page".** Now reads "the item is still shown on the Items page", matching the app's `/items` route and label (`frontend/src/App.vue:622`) and `vocabulary.md`.
- [x] **[advisory] Clarity — FR-4 number derivation.** FR-4 now says the number shows "when one can be derived from the item's URL or external id", with a "A row without a derivable number" scenario.
- [x] **[advisory] Clarity — FR-9 totals scope.** FR-9 now counts "as the sum of the per-repository (grouped) counts and excluding items with no matching repository".
- [x] **[advisory] Clarity — FEAT-p3 FR-3 attribution.** Constraints and Conflicts now read "FEAT-p3 FR-3 names no SPA placement"; the Settings surface is attributed to code. Confirmed against `.sdlc/features/p3-repositories/requirements.md` FR-3, which names only list/read/delete.
- [x] **[advisory] Completeness — reach the Repositories page.** FR-1 gained the "Reach the page from the app's navigation" scenario. Confirmed the sidebar has no Repositories entry today (`frontend/src/App.vue:552-640` lists Tasks/Gantt/Metrics/Items).
- [x] **[advisory] Completeness — unknown repository id.** FR-6 gained the "An unknown repository id" scenario (not-found state plus a link back).
- [x] **[advisory] Testability — NFR-4 "legible".** Restated as the measurable proxy "shows its kind and number untruncated" at 375 px, default text size.
- [x] **[advisory] Testability — NFR-3 measurement method.** Now specifies the production build, a warm local API, and excluding the initial API fetch.
- [x] **[advisory] Testability — FR-5 blank line.** Removed; every `@FR-5` block is well-formed.
- [x] **[advisory] Feasibility — URL/remote parsing.** The Constraints now state the SPA cannot call `parse_github` / `github_owner_repo` and parses and normalizes both remote forms itself, leaving server-side derivation to the specification.
- [x] **[advisory] Feasibility — NFR-3 per-item cost.** The Constraints now name the target scale (tens of repositories, hundreds of items) and flag a server-side count or a repository id on the item read as a specification decision.
- [x] **[advisory] Conflicts — FR-2 vs OQ3.** OQ3 closed; FR-2 keeps repository groups under Settings. Confirmed the Settings view has separate "Repositories" and "Repository groups" sections (`frontend/src/views/SettingsView.vue:14-15`), so the split is feasible.
- [x] **[advisory] Conflicts — FR-1 vs OQ2.** OQ2 closed; FR-1 lists every registered repository, with no-GitHub-remote ones as zero-count rows.

## Testability

- **[advisory]** (L1 - Cited) FR-4's new "A row without a derivable number" scenario (line 131) presupposes "a GitHub item whose URL carries no number" inside a repository detail view, but FR-5 now restricts those views to GitHub issue/PR items. Such items always carry a number: the issue/PR URL is matched by `GITHUB_RE` in `parse_github` (`backend/src/agentic/services.py:152`), which requires `/(issues|pull)/<num>`, and the derived `external_id` is `o/r#<num>`. The precondition therefore looks unreachable. Either ground the scenario in a concrete shape that can occur (for example an item whose `url` is a non-canonical form while `external_id` is absent) or note it as defensive.

## Clarity

- **[advisory]** (L1 - Cited) NFR-4's acceptance criterion (line 291) reads "each repository row and item row shows its kind and number untruncated", but repository rows show name, path, remote, branch, and counts (`RepositoryRead`, `backend/src/agentic/schemas.py:86`), not a kind or a number; the kind and number belong to the item rows. Scope the clause to item rows, or restate what a repository row must keep untruncated.

## Conflicts

No conflict found in the changed content.
FR-2's removal of the Settings "Repositories" section while keeping "Repository groups" matches the code's separate sections, and FR-5's issue/PR scoping removes the contradiction the previous round flagged.

## Sync drift: 2026-10-26

The implementation has moved past the approved requirements (AG Grid, live GitHub listing, task import). Reopened during /sync-sdlc; no requirement text was rewritten.

- FR-3: the repository detail view now lists the repository's whole issue and PR listing fetched from GitHub (ghx), including items associated with no task (each offering a New task action), not only items associated with at least one task.
- FR-6: the detail empty state reads "No issues or pull requests to show for this repository"; it no longer describes the rows as task-associated.
- FR-7: the separate Issues and Pull requests sections with headings, counts, and a text query were replaced by one data grid with a Kind column and per-column filters.
- NFR-2: the detail view fetches a live GitHub listing on load; stored item metadata is the fallback after a ghx failure, not the only source of the rows.
