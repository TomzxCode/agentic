---
artifact: specification
verdict: changes-requested
reviewed_at: 2026-10-12
session_link: http://localhost:10000/?session=ses_ed20dd7b7ffeRNOIfPEWqJEfmH
---

# Review: Specification (Factory metrics: autonomy rate and yield)

Review of `specification.md` against its sibling `requirements.md`, the project context in `.sdlc/context/`, and the existing codebase it extends.
The spec is a draft (`status: draft`) for a not-yet-implemented feature, so findings are cited (`L1 - Cited`) rather than executed.
Findings carry an evidence level; the ladder is in `skills/sdlc/references/evidence.md`.

Deterministic checks:

- No `api.yaml` accompanies this specification, so the spectral lint step is not applicable (skipped, never blocks).
- Both `mermaid` blocks were extracted and passed to `mmdc`; the tool is installed but its Chrome backend fails to launch in this environment, which is a tooling failure rather than a syntax failure.
  Mermaid syntax is therefore `unproven`; rendering is the runtime evidence it needed and could not run here.

## Ambiguities

- **[blocking]** Lifecycle transition rules are undefined.
  The spec lists the statuses (`proposed, verified, accepted, rejected, reverted`, specification.md:42) and the stamps each transition writes (`verified_at`, `accepted_at`, `closed_at`, specification.md:49-51), and exposes a transition endpoint (`POST /api/changes/{change_id}/status`, specification.md:110), but never states which transitions are allowed, whether `verified` is a mandatory step before `accepted`, whether backwards or repeat transitions are permitted, or what an invalid transition does.
  The sequence and the FR-3 acceptance criterion both move `proposed -> accepted` directly (specification.md:134; requirements.md:59-67), which is only valid if `verified` is optional, an assumption the spec never makes explicit.
  This changes behavior (transition validation) and makes the endpoint and its tests unimplementable as written. `L1 - Cited`
- **[advisory]** `PATCH /api/changes/{change_id}` says it updates "editable fields" (specification.md:109) without naming them.
  The data model (specification.md:36-53) offers several candidates (`title`, `change_class`, `repository_id`, `worktree_id`, `external_ref`, `notes`) and the read-only ones (`task_id`, status, timestamps, the denormalized counters) are not distinguished from the editable ones. `L1 - Cited`
- **[advisory]** The tolerance behind direction "defaults to 0.02" (specification.md:100), but no mechanism to set it is given: it is not a stored field (specification.md:65-74), not an `GET /api/metrics` parameter (specification.md:118), and not a config key.
  Either it is a constant (and "defaults to" should read "is fixed at") or a settable knob that is missing from the contract. `L1 - Cited`
- **[advisory]** `GET /api/metrics` returns "one result per metric plus raw counts" (specification.md:118) without defining the result or count fields, so the response is not pinned down. `L1 - Cited`
- **[advisory]** Whether an `approval` intervention should count against autonomy rate is unstated.
  An approval is listed as an intervention kind (specification.md:61) and any intervention sets `human_intervened = true` (specification.md:46), so a change that a human only ever approved reports as not autonomous, which may or may not match the metric's intent ("how much of the work reached production without me touching it", requirements.md:13). `L1 - Cited`
- **[advisory]** `FR-1` requires the change to record "start/end timestamps" (requirements.md:30), but the model replaces these with lifecycle stamps (`opened_at`, `verified_at`, `accepted_at`, `closed_at`, specification.md:48-51) and never states which column is the "end" of an accepted change. `L1 - Cited`
- **[advisory]** The spec adds `task_id` and `change_class` filters to `GET /api/metrics` (specification.md:118) while a technical decision declares metrics whole-store and "never per person" (specification.md:153).
  These are not contradictory (a task is not a person), but the interaction is worth one clarifying sentence. `L1 - Cited`

## Inconsistencies

- **[blocking]** Deleting a task is not specified to delete its changes and interventions, contradicting `NFR-3` and the not-null foreign key.
  `NFR-3` requires that "deleting a task or a change shall also delete its interventions so no orphan rows remain" (requirements.md:46), and a change always belongs to exactly one task with `task_id ... FK task, index, not null` (specification.md:39, requirements.md:53).
  The spec only specifies `DELETE /api/changes/{change_id}` deleting "a change and its interventions" (specification.md:112) and never mentions the task-deletion path.
  The existing task delete performs explicit ordered child deletes (routers/tasks.py:282-292), so leaving `change` and `changeintervention` out of it would either violate the foreign key or leave orphan rows. `L1 - Cited`

## Incoherences

No issues found.
The metric definitions, the direction rules, the technical decisions, and the risks point the same way (for example, excluding unobserved changes from yield is stated consistently in the term list and the technical decisions, specification.md:88-89 and :150).

## Missing Information

- **[advisory]** Non-functional coverage is absent.
  The requirements carry five NFRs (requirements.md:44-48); the spec has no Non-Functional Considerations section and only touches NFR-1 (pure functions, specification.md:149) and NFR-5 (whole store, specification.md:153) indirectly.
  `NFR-2` (responsive for thousands of changes) and `NFR-4` (Metrics page usable at phone widths) have no treatment, and the no-auth, trusted single-user assumption the rest of the app makes is not restated.
  A section mapping each NFR to the design (as `p9-tags/specification.md:134-140` does) would close this. `L1 - Cited`
- **[advisory]** Error and edge-case behavior is unspecified across all eleven endpoints (specification.md:106-116): no status codes, no error bodies, and in particular no defined response for an invalid transition (see the blocking lifecycle ambiguity) or for a missing change/baseline. `L1 - Cited`
- **[advisory]** The CLI surface for `FR-8` is not specified.
  `FR-8` (Must) requires changes, interventions, metrics, and baselines to be exposed "over HTTP and through the CLI" (requirements.md:37), but the spec only says "the CLI gains a `change` group and a `metrics` group" (specification.md:14) with no command names, arguments, or output.
  If a `create-cli-design` artifact is planned for this feature (as `p1-tasks`/`p2-source-items` have), that closes the gap; otherwise a Must requirement is under-covered. `L1 - Cited`
- **[advisory]** Performance is asserted but not designed.
  `NFR-2` targets thousands of changes (requirements.md:45), yet the only index in the model is `task_id` (specification.md:39); the metric query filters on `accepted_at` and `status` (specification.md:87-88 and :137), and `GET /api/changes` has no pagination or limit (specification.md:106). `L1 - Cited`
- **[advisory]** The new domain terms (`Change`, `ChangeIntervention`, `MetricBaseline`, `autonomy rate`, `yield`) are not defined in `vocabulary.md`, which the conventions require terminology to match (conventions.md:59). `L1 - Cited`
- **[advisory]** Authentication and authorization are not addressed and are not applicable: the app is a local single-user process with no auth (architecture.md:184-186; p9-tags/specification.md:140), so this is consistent and needs no change. `L1 - Cited`

## Implementability

- **[advisory]** All three tables are new, so `create_all` creates them; the spec does not note that `models.py` must define them and that `db.create_db_and_tables` imports `models` so they register before `create_all` (db.py:31-35) and `main.py` must include the two new routers in its loop (main.py:43-44).
  These are conventions the implementer will follow, but naming them removes a step. `L1 - Cited`
- **[advisory]** No circular dependency or unresolvable constraint is present; the pure-function core (`metrics.py`) and the thin routers keep the design small, and there are no new external dependencies. `L1 - Cited`

## Reversibility

- **[advisory]** `DELETE /api/changes/{change_id}` hard-deletes a change and its interventions (specification.md:112) with no soft-delete and no deprecation window.
  Because metrics are computed from the surviving rows, a delete silently changes historical metric values.
  This may be intended for a local single-user app, but the spec does not call the loss out.
  Baselines are reversible (`DELETE /api/metrics/baselines/{metric}`, specification.md:116), and `reverted` is the intended reversal for a non-deleted change. `L1 - Cited`

## Forward Compatibility

- **[advisory]** No compatibility or versioning policy is stated.
  The spec fixes three enum-like string sets (`change_class`, `kind`, `status`, specification.md:41-42 and :61) and does not say how consumers should treat unknown values or whether changes stay additive within the current API.
  `p9-tags` states an additive-fields policy in `api.yaml`; this spec has no equivalent.
  The `MetricBaseline` primary key on `metric` does grow additively (a new metric is a new row, specification.md:69), which is good. `L1 - Cited`

## Open Questions

Carried from `requirements.md:123-127`; the specification resolves none of them, and its risk 2 explicitly references open question 3 (specification.md:158).

1. Should the system auto-create a change when an agent run starts, or is explicit recording enough for the first iteration?
2. Should a change's class default from the task's tags, or is an explicit class always required?
3. Should yield also count changes rejected at verification, on top of changes reverted after acceptance?

Question 3 carries the most impact: because a rejected change never gets `accepted_at`, it is invisible to both metrics (specification.md:82-83 and :87), so a factory that produces and rejects heavily can still report high autonomy and yield.
These are product-scope decisions rather than unverified technical assumptions, matching the approved `p9-tags` review, so no `/create-assumption` record was created; resolving question 3 before implementation is nonetheless worthwhile since it changes the metric definitions.

## Verdict

`changes-requested`: two blocking findings.
The lifecycle transition rules are undefined (blocking, Ambiguities) and task deletion is not specified to cascade to changes and interventions (blocking, Inconsistencies).
The remaining findings are advisory: response-field and tolerance details, missing non-functional and error coverage, the unspecified CLI surface, the destructive delete, and the absent compatibility policy.
