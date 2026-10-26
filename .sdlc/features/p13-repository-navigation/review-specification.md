---
artifact: specification
verdict: changes-requested
reviewed_at: 2026-10-12
session_link: http://localhost:10000/?session=ses_ed1823a65ffe7LJmF4SEXBZr08
---

# Review: Specification (Repository navigation)

Scoped re-review after revision 1 of `specification.md`.
Confirms each prior finding from the previous `changes-requested` review is addressed, and reviews only the changed content (component table, `RepositoryItem.tasks` source and Task resolution bullet, the Repositories page load sequence, the new "View States and Behavior" section, and the frontmatter).
Verdict and evidence for content the revision did not touch carry over from the prior review.
The spec remains a draft for a not-yet-implemented feature, so findings are cited (`L1 - Cited`) unless executed.

Deterministic checks:

- No `api.yaml` accompanies this specification and none is expected, because the feature defines no new API surface (specification.md:118); the spectral lint step is not applicable (skipped, never blocks).
- All four `mermaid` blocks were re-extracted and re-rendered with `mmdc -p <pptr.json with --no-sandbox>`; all four succeeded, including the changed Repositories page load sequence. `L3 - Executed`
- Code claims in the changed content were checked against the codebase: `store.notify(message, isError)` exists (`frontend/src/store.js:50`), the `760px` mobile breakpoint exists (`frontend/src/styles.css:1696`), and `RepositorySelect.vue` renders each selected repository as a chip (`frontend/src/components/RepositorySelect.vue:47-50`), matching the newly added component row. `L3 - Executed`
- The derivation rules and the backend helpers carry over from the prior review: `parse_github` and `github_owner_repo` match the spec's Derivation rules and the FR-5 exclusions. `L3 - Executed` (unchanged content)

## Prior Findings

1. **[advisory] (Ambiguities) Whether the Repositories page needs task data was unclear.**
   Addressed. `RepositoryItem.tasks` now names its resolver (`resolved from store.tasks by RepositoryDetailView`, specification.md:97), a **Task resolution** bullet states the helper returns each item's `task_ids` only and that the Repositories page renders no task links and does not load tasks (specification.md:107), and the Repositories page load sequence now calls `groupItemsByRepository(repositories, items)` with no `tasks` argument (specification.md:145).
2. **[blocking] (Missing Information) The FR-6 error state with a retry action and the Repositories page's no-repositories empty state were not specified.**
   Addressed. Both view rows in the component table now name their states (specification.md:55-56), and the new **View States and Behavior** section defines, per view, a Loading, Empty, Error, and (for the detail view) Not-found state: the Repositories page Empty state offers the add controls inline and its Error state offers a Retry action (specification.md:199-204); the detail view's Not-found links back to `/repositories` and its Error state offers a Retry (specification.md:208-214). This designs the Must criterion `FR-6` (requirements.md:34, :174-200).
3. **[advisory] (Missing Information) NFR-4 (phone widths, no horizontal scrolling) and NFR-5 (aria-labels, kind as text, keyboard-reachable rows and links) had no treatment.**
   Addressed. New **Responsiveness (NFR-4)** and **Accessibility (NFR-5)** subsections map each requirement to the design, including the 375px acceptance wording and the `aria-label`/text-badge/keyboard statements (specification.md:216-227).
4. **[advisory] (Implementability) The component that renders a task's repository chips was not listed as changed.**
   Addressed. `RepositorySelect.vue` is now listed as Extend with a `linkToDetail` flag that renders each selected repository as a link to `/repositories/:id`, and the `TaskView.vue` row sets that flag (specification.md:62-63), covering `FR-8` (requirements.md:36).

## Inconsistencies

- **[advisory]** The detail-view sequence still passes `tasks` to the helper, which the new Task resolution bullet says the helper does not resolve.
  The new bullet states the helper returns each item's `task_ids` only and that `RepositoryDetailView` resolves them to `{id, title, status}` (specification.md:97, :107), but the detail sequence shows `RVD->>H: itemsForRepository(repository, items, tasks)` returning `RepositoryItem[]` (which carries `tasks`) (specification.md:163-164).
  If the helper takes `tasks` and returns resolved tasks, the bullet is inaccurate; if the bullet is right, the sequence should call `itemsForRepository(repository, items)` and resolve tasks in the view.
  Aligning the sequence with the bullet removes the ambiguity; it does not change the view contract, so it is advisory. `L1 - Cited`

## Incoherences

No issues found in the changed content.
The new View States section agrees with the component table, the sequences, and the requirement priorities, and the state vocabulary (Loading / Empty / Error + retry / Not-found / Loaded) is used consistently across both views.

## Missing Information

No issues found in the changed content.
The prior blocking gap (`FR-6`) and the prior `NFR-4`/`NFR-5` gap are both closed; the changed content adds no new gap.

## Implementability

No issues found in the changed content.
Adding a `linkToDetail` flag to `RepositorySelect.vue` and setting it from `TaskView.vue` is a small, local change that leaves the other `RepositorySelect` usages (command palette, repository groups panel) unaffected when the flag is unset.

## Reversibility

No issues found in the changed content; the change remains additive and read-only.
(Carried over: two new routes, a new helper, and store/API extensions, with no table, column, migration, or destructive operation.)

## Forward Compatibility

No issues found in the changed content; the additive-only stance is unchanged.
(Carried over: the helper reads a fixed field set and ignores unknown fields, `kind` normalizes through an open map with an excluded fallback, and matching keys off each item's own URL.)

## Open Questions

Carried from `requirements.md:316`; the spec defers it explicitly and the revision did not change it.

1. Should the repository detail view let the user import a new task from an issue or PR that is not yet associated, or is navigation of already-associated items enough for this feature?
   The spec puts this out of scope (specification.md:239, :253), which keeps the feature read-only navigation.
   This is a product-scope decision rather than an unverified technical assumption, so no `/create-assumption` record was created.

## Verdict

`approved`.
No blocking findings.
All four prior findings are addressed, including the single blocking `FR-6` finding.
One advisory finding is carried forward: the detail-view sequence still passes `tasks` to the helper while the new Task resolution bullet says the helper returns `task_ids` only (Inconsistencies).

## Sync drift: 2026-10-26

The implementation has moved past the approved specification. Reopened during /sync-sdlc; the specification was not rewritten.

- `frontend/src/repositories.js` was split into `repositories/parse.js` and `repositories/rows.js`.
- Both views render as AG Grid data grids (`RepositoriesGrid.vue`, `RepositoryItemsGrid.vue`, with `repositoriesCells.js`, `repositoryItemsCells.js`, `gridSetup.js`, `ValuesFilter.vue`), not the specified `.panel`/`.item` sections.
- The detail view's load now also fetches the live ghx listing, people, and change records, beyond the specified repositories, items, and tasks.
- The out-of-scope item "Importing a task from an unassociated issue or PR" is implemented (the grid's New task action calls `api.tasks.create` with `github_url`).
- The consumption contract grew beyond the two list endpoints: `GET /api/github/repository` (live listing), `POST /api/items/{id}/refresh`, and `POST /api/changes` (record a change from a merged PR), plus ghx web-UI links.
- A home-grown column chooser (`GridColumnChooser.vue`) with per-device `agentic.gridColumns.*` localStorage preferences was added; the specification does not cover it.
