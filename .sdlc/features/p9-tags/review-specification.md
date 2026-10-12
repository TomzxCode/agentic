---
artifact: specification
verdict: approved
reviewed_at: 2026-10-12
---

# Review: Specification (Task tags)

Re-review of `specification.md` and its contract `api.yaml` after the prior review returned `approved` with non-blocking findings.
Judge the specification on its own terms (clarity, internal consistency, coherence with the approved requirements, implementability, forward compatibility); it was reverse-documented after the feature shipped.
Findings carry an evidence level; the ladder is in `skills/sdlc/references/evidence.md`.

Deterministic checks:

- `npx -y @stoplight/spectral-cli lint` with the `spectral:oas` ruleset: no errors. (The header comment's `-r spectral:oas` form does not resolve in spectral 6.17.0; a ruleset file that `extends: ["spectral:oas"]` works.) `L3 - Executed`
- All four `mermaid` blocks rendered with `mmdc` (no syntax errors). `L3 - Executed`

## Previous Findings

| # | Prior finding | Status |
|---|---|---|
| 1 | Overview implied create writes a tag-change timeline event | Addressed: the sentence now separates normalization (create and update) from timeline recording, and states "the timeline is only written on update; create records a single 'created' event" (specification.md:12). Matches the code (create writes one `created` event at routers/tasks.py:207; tag changes are recorded on PATCH at routers/tasks.py:243-254). `L1 - Cited` |
| 2 | Filter sequence implied the SPA sends the `tag` query parameter | Addressed in prose: the section now states the SPA filters the already-loaded list in the browser and only the CLI sends `tag` (specification.md:87), reinforced by the Web UI section ("it does not send the `tag` query parameter", specification.md:81). Residual nit below: the diagram's client participant still reads "Client (SPA / CLI)". `L1 - Cited` |
| 3 | `api.yaml` lacked the write path and error responses | Addressed: `POST /api/tasks` (api.yaml:74-97) and `PATCH /api/tasks/{task_id}` (api.yaml:98-128) are now defined, with an `Error` schema (api.yaml:217-222) and 400/404 responses. The four operations match the specification's summary table one for one. `L1 - Cited` |
| 4 | `api.yaml` lacked a `session_link` comment | Addressed: `# session_link: ...` is the first line (api.yaml:1), per the YAML convention. `L1 - Cited` |
| 5 | `api.yaml` bounded `priority` without API enforcement | Addressed: `minimum`/`maximum` removed; `Task.priority` now documents "not range-validated by the API" (api.yaml:158-160), matching the plain `int` with no validator in schemas.py:223. `L1 - Cited` |
| 6 | NFR-3, NFR-4, and the no-auth constraint were not carried into the spec | Addressed: a Non-Functional Considerations section now maps NFR-1 (data integrity) through NFR-4 (performance) plus Security/no-auth (specification.md:133-139). `L1 - Cited` |
| 7 | Web UI behavior under-recorded | Addressed: a Web UI section maps each component to its FRs (specification.md:70-81). Verified against the code: `TagInput.vue` chips plus Enter/comma-add and Backspace-remove; `App.vue` sidebar pills, filter row, and new-task modal TagInput (App.vue:425-444, :614); `TaskView.vue` header Tags and PATCH on save (TaskView.vue:185-190, :73-84); `TasksView.vue` pills, filter row, filtered status counts; `store.js` `tags`/`tagFilter`/`loadTags`/`toggleTagFilter`; `api.js` `api.tags.list()`. `L1 - Cited` |

## Ambiguities

- Web UI table row: "counts reflect the active filter" (specification.md:77).
  The status badges in `TasksView.vue` do reflect the filter, but the per-tag counts in the filter row come from `store.tags` (`tag.count`) and stay global.
  Naming which counts are meant (e.g. "the status counts reflect the active filter") removes the ambiguity. Non-blocking. `L1 - Cited`
- The filter sequence diagram still labels its client participant "Client (SPA / CLI)" (specification.md:92) while the sentence above it says the SPA does not send the query.
  Relabeling the participant "CLI" (the path the diagram depicts) would match the prose exactly. Non-blocking. `L1 - Cited`

## Inconsistencies

- The summary table's error column uses symbolic codes (`INVALID_INPUT`, `NOT_FOUND`, specification.md:62-68) that are not present in the response body: `api.yaml`'s `Error` schema carries only `detail` (api.yaml:217-222), and the API returns FastAPI's `{"detail": ...}`.
  This is the same documentation convention `p1-tasks/specification.md` uses for the shared API, so the statuses and descriptions now agree across both; the symbolic codes are labels, not fields. Pre-existing and non-blocking. `L1 - Cited`
- The `api.yaml` header comment (api.yaml:7) gives the validation command `npx -y @stoplight/spectral-cli lint -r spectral:oas api.yaml`, which spectral 6.17.0 treats as a file path and fails to resolve.
  A comment pointing at a ruleset file (or the plain `lint api.yaml` with a `.spectral.yaml`) would be runnable. Non-blocking doc nit. `L3 - Executed`

## Incoherences

No issues found.
The Overview's "no table or migration" claim, the Storage technical decision, and risk 1 (a future `tag` table) point the same way rather than contradicting each other.

## Missing Information

No blocking gaps.
The requirements' NFR-1 through NFR-4 and the no-auth constraint are all carried into the Non-Functional Considerations section, and every functional requirement (FR-1 through FR-8) is reflected in the Overview, Web UI, Sequences, or Technical Decisions.

## Implementability

No issues found.
The design is small and matches the code: one normalizer at the router boundary (crud.py:20-30), one derived-tag router (routers/tags.py:20-30), and in-process filtering over the already-fetched list (routers/tasks.py:144-151).
No external dependency and no circular constraint.

## Reversibility

No issues found.
No destructive change: `task.tags` already exists, so there is no migration, and risk 1 names the forward path (a `tag` table with an index) if in-process scanning stops scaling.
The API changes are additive (a new query parameter and a new endpoint, with the write path already part of the tasks API).
The one semi-committing choice, storing tags as an array of strings rather than objects, is discussed under Forward Compatibility.

## Forward Compatibility

- `api.yaml` states the compatibility policy (additive fields are non-breaking; removing or renaming is breaking) and marks both schemas `additionalProperties: true` (api.yaml:13-22, :148, :168, :189). Good.
- The storage shape is fixed as a JSON array of strings (specification.md:37).
  If tags later need metadata (a color, a hierarchy), the element type would have to change to an object, which the additive policy does not cover and which would break string-reading consumers.
  Naming that as the next breaking change, or reserving an object shape now, would keep the door open. `L1 - Cited`
- A multi-tag "any" filter is called out as a later addition (specification.md:149), and the `tag` parameter already accepts repeats, so it grows additively. `L1 - Cited`

## Open Questions

Carried from `requirements.md:225-229`; none is resolved by the specification:

1. Case-sensitive tags (current) or case-insensitive?
2. Rename/delete a tag across all tasks, or per-task editing only?
3. A limit on tags per task?

These are product-scope decisions rather than unverified technical assumptions, matching the approved requirements review, so no `/create-assumption` record was created.
Open Question 1 carries the most implementation impact (it changes write normalization, filter comparison, and count grouping), so resolving it before tag-driven views build on the current case-sensitive behavior is still worthwhile.

## Verdict

`approved`: no blocking finding.
All seven prior non-blocking findings are addressed, both deterministic checks pass, and the specification is internally consistent, coherent with the approved requirements, and accurate to the implementation.
The two Ambiguities and two Inconsistencies above are non-blocking clarity and tooling-command nits.
