---
artifact: mockups
verdict: changes-requested
reviewed_at: 2026-10-12
session_link: http://localhost:10000/?session=ses_ed1823a65ffe7LJmF4SEXBZr08
---

# Review: Mockups — Repository navigation (scoped re-review, revision 1)

Scoped re-review of `mockups.md` plus `mockups/repositories.html`, `mockups/repository-detail.html`, and the new `mockups/task-repository-link.html`, against the prior findings in this file (revision 0) and the revision-1 delta.

Verdict and evidence for content the revision did not touch carry over from the revision-0 review.
The deterministic checks below were re-run against the current files (`L3 - Executed`): all three HTML files are self-contained (no `<link>`, `<script>`, `url(http)`, or `@import`), all three carry the `<!-- session_link: ... -->` first line, no `--faint` reference remains, and the single Mermaid navigation-flow block re-renders with `mmdc` (with `--no-sandbox`; the default failure is a browser sandbox issue, not a syntax error).
Code and sibling-artifact comparisons are cited (`L1 - Cited`).

## Prior findings — status

- **Blocking (Accessibility): mobile sidebar hidden with no toggle.** Addressed. Both full-page mockups now render the top-bar `.menu-btn` toggle (`repositories.html:95,179`, `repository-detail.html:91`) with `aria-label="Toggle navigation"`, and `repositories.html` renders a labelled "Mobile (<760px)" drawer section (`repositories.html:177-194`). The contradiction with `mockups.md:135`, `specification.md:220`, FEAT-p7 FR-3, and the app's `.app > .menu-btn` is gone.
- **Blocking (Consistency): populated rows mixed link and non-link markup.** Addressed. All three rows in `repositories.html` are now `.item` with an `<a href="repository-detail.html">` for the name and a sibling Remove button (`repositories.html:112-149`); a grep confirms no `<button>` nested in an `<a>`.
- **Blocking (State Coverage): detail empty state dropped the kind filter.** Addressed. `repository-detail.html:161-173` now renders the All/Issues/PRs controls and the filter input above the empty message.
- **Blocking (Responsiveness): 640px breakpoint vs the spec's 760px.** Addressed. Both files use `@media (max-width: 760px)` and `mockups.md:133-137` now lists Mobile ≤760px / Tablet 761-1000px / Desktop >1000px.
- **Advisory (Coverage): FR-8 task link and Settings pointer unrendered.** Addressed by the new `task-repository-link.html`.
- **Advisory (Coverage): "number not derivable" variant unrendered.** Addressed (`repository-detail.html:148-158`).
- **Advisory (Usability): Remove has no confirmation affordance.** Addressed in `mockups.md:153` (confirm copy documented, unchanged from Settings).
- **Advisory (Accessibility): `--faint` used for content; blanket AA claim.** Addressed. `--faint` is gone; content uses `--text`/`--muted`/`--accent`, and the claim at `mockups.md:143` is now scoped to body and link text.
- **Advisory (Accessibility): button nested in anchor.** Addressed (see the Consistency item).
- **Advisory (Accessibility): kind filter state not exposed.** Addressed. The filter buttons now carry `aria-pressed` (`repository-detail.html:105-107,164-166`).
- **Advisory (Consistency): bare icon sidebar vs the real sidebar.** Addressed. The sidebar and drawer now carry the brand, palette trigger, New task button, tag filters, task cards, and icon nav; Repositories uses a distinct `▦` glyph (Gantt stays `▤`).
- **Advisory (Consistency): kind color reused for task-status chips.** Addressed. Task chips now use a neutral `.badge` (`repository-detail.html:118-119,131,143,155`; `mockups.md:87`).
- **Advisory (Consistency): loading used `.panel` instead of `.empty`.** Addressed. Loading now uses `.empty` + `.spinner` (`repositories.html:166`, `repository-detail.html:177`).
- **Advisory (Spec Fidelity): item title link `#` plus a separate GitHub link.** Addressed. The title is now the single GitHub link and the separate link is dropped (`repository-detail.html:115,128,140,151`).
- **Advisory (Implementability): new `.badge.*`/`.btn.chip` variants not listed.** Addressed (`mockups.md:85-87`).
- **Advisory (Implementability): HTML mockups lacked the session_link comment.** Addressed on all three files.
- **Open questions 1 and 2.** Both resolved (760px adopted; the item title is the GitHub link).

No blocking findings.

## Accessibility

- **[advisory]** (L3 - Executed) `repository-detail.html` renders the top-bar `menu-btn` toggle but no labelled mobile-drawer section (grep: 0 `drawer` occurrences), so the mobile nav state is demonstrated only on `repositories.html`. The prior blocking concern (nav unreachable at mobile) is resolved by the toggle on both pages, and the drawer is shared chrome; this is a demonstration-completeness gap, not an operability one. The revision summary's claim that both full-page mockups carry a labelled drawer section does not hold for the detail page.
- **[advisory]** (L1 - Cited) The mockups' `.menu-btn` is in flow (`margin-bottom: 12px`), while the app's button is `position: fixed` and the app reserves `padding: calc(64px + env(safe-area-inset-top))` on `.main` (`styles.css:1725`). The static simplification is reasonable (no fixed button means no reserved padding is needed), but it diverges from the app's mechanism; note it so implementation follows the app.
- **[advisory]** (L3 - Executed) `.badge.issue` renders `--accent-2` `#3b82f6` on the badge surface `--bg-3` `#232a36` = about **3.9:1**, below the WCAG AA 4.5:1 for 12px text. `.badge.pr` (`--warn` `#fbbf24`) passes (~8.6:1). This markup is unchanged from revision 0 and the revision's scoped AA claim (`mockups.md:143`, body and link text only) does not cover badges, so no contradiction; recorded for completeness since the kind badge is the primary kind indicator.

## Consistency

- **[advisory]** (L3 - Executed) The task-repository-link chips use `.chip` (`task-repository-link.html:29,49-50`) while `repository-detail.html` and `mockups.md:86` name the class `.btn.chip`; unify the class name across the mockups so the component is specified once.

## Coverage

- **[advisory]** (L1 - Cited) The `DirectoryPicker` bulk-add modal (FR-2) remains unrendered, carried over from revision 0 as a deliberate reduction for a reused component (`specification.md:64`).

## State Coverage

- **[advisory]** (L1 - Cited) The per-screen Error sections still do not show the `store.notify` surfacing `specification.md:205` mentions; acceptable for a static mockup, carried over from revision 0.

## Verdict

`approved`.
All four blocking findings from revision 0 are addressed, and the advisory findings are resolved or carried forward. The remaining findings are advisory and do not force another round.

## Sync drift: 2026-10-26

The approved mockups no longer match the implemented views. Reopened during /sync-sdlc; the mockups were not rewritten.

- The mockups draw the repositories list and the repository detail as stacked `.item` rows; the implementation renders both as AG Grid data grids with per-column filters and a column chooser.
- `repository-detail.html` shows separate Issues and Pull requests sections with headings and counts; the implementation shows one grid with a Kind column, plus State, Author, Task status, Changes, and Actions columns the mockups do not show.
- The mockups have no New task action on an unassociated issue or PR row, no Refresh all / Refresh linked controls, and no ghx web-UI link; all three exist in the implementation.
