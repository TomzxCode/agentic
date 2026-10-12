---
artifact: requirements
verdict: approved
reviewed_at: 2026-10-12
---

# Review: Requirements (Task tags)

Reviewed `requirements.md` and `cli-design.md` together as one requirements phase, per the review skill.
This is a re-review after the prior `changes-requested` verdict: all nine prior findings are addressed (table below).
Findings carry an evidence level (`skills/sdlc/references/evidence.md`).
No conflicts were found, so no artifact was amended.

## Previous Findings

| # | Prior finding | Status |
|---|---|---|
| 1 | FR-3 ordering tie-break unclear | Addressed: FR-3 now reads "ordered by count descending and then case-insensitively by name", matching the implementation's `item[0].lower()` key (requirements.md:29, backend/src/agentic/routers/tags.py:29). `L1 - Cited` |
| 2 | "Future tag views" listed as a stakeholder | Addressed: the Stakeholders table now lists only the Sole user and the Coding agent; tag-driven views moved to the Overview's "foundation for" sentence (requirements.md:14, 18-21). `L1 - Cited` |
| 3 | NFR-1 and NFR-3 missing acceptance criteria | Addressed: both have tagged `gherkin` blocks, NFR-1 asserting no separate tag table and NFR-3 asserting no horizontal scroll at 375 px (requirements.md:199-220). `L1 - Cited` |
| 4 | No requirement states create/update accepts a tags list | Addressed: FR-1 now states the API accepts a list of tags on create or update and normalizes it (requirements.md:27). `L1 - Cited` |
| 5 | FR-2 criteria used "bug ui" ambiguously | Addressed: every FR-2 `Given` now names explicit tag lists (`["bug"]`, `["bug", "ui"]`, `["infra"]`), so each scenario is executable as written (requirements.md:72-91). `L1 - Cited` |
| 6 | FR-5 second scenario had no `When` | Addressed: "When its row is shown in the task list" (requirements.md:148). `L1 - Cited` |
| 7 | cli-design `task create`/`update` had no synopsis or options table | Addressed: both now have a synopsis, a positional-argument table, and an options table with types and defaults (cli-design.md:93-130). `L1 - Cited` |
| 8 | cli-design had no error-path example session | Addressed: the "Error path" session shows `agentic task get does-not-exist` printing `error: Task not found (HTTP 404)` and exiting 1, which matches `safe()` and `get_task_or_404` (cli-design.md:223-230, cli/src/agentic_cli/cli.py:60-74, backend/src/agentic/crud.py:41-45). `L1 - Cited` |
| 9 | Command-tree connectors were malformed | Addressed: the tree now reads `├── list`, `├── create`, `└── update` (cli-design.md:16-24). `L1 - Cited` |

## Clarity

No issues found.
FR-3's tie-break is now specified (case-insensitive) and matches the implementation.
Each requirement names a clear subject and action, and no vague terms ("fast", "user-friendly", "easy") appear.

## Completeness

No issues found.
All stakeholders are the two real actors (Sole user, Coding agent).
Happy-path, empty, duplicate, unknown-tag, and threshold cases are covered.
The write surface is explicit in FR-1, and the four non-functional categories (data integrity, consistency, usability, performance) are present and now each have acceptance criteria.

## Testability

No issues found; no blocking finding.
Every requirement (FR-1 through FR-8, NFR-1 through NFR-4) has a `gherkin` block tagged with its ID, each `Scenario:` is named, and each block has at least one `Given`/`When`/`Then`.
NFR-4 gives a concrete threshold (under 200 ms) at a stated scale (300 tasks).

Non-blocking observations:

- The second `@FR-5` block has a blank line between the tag and `Scenario:` (requirements.md:144-146), unlike every other block.
  The official Gherkin parser still attaches the tag to the scenario (verified), so this is cosmetic; removing the blank line keeps the blocks uniform. `L2 - Analyzed`
- FR-3's criterion asserts the counts and the descending order but does not exercise the case-insensitive name tie-break that the previous finding asked to clarify.
  Optional: add two equal-count tags that differ in case and assert their order. `L1 - Cited` (requirements.md:93-102)

## Feasibility

No issues found.
All requirements are implemented and consistent with the stated constraints.
NFR-4 stays inside its budget because the API filters the in-memory task list (a few hundred tasks) rather than running a database query (backend/src/agentic/routers/tasks.py:138-163). `L1 - Cited`
NFR-1 holds because tags live in the existing `task.tags` JSON column and the tag router derives the set from the tasks (backend/src/agentic/routers/tags.py:20-30). `L1 - Cited`
No external system or new dependency is introduced.

## CLI Design

No blocking finding.
Every user-facing functional requirement with a CLI surface appears in the traceability table: FR-1, FR-2, FR-3, FR-6, FR-7, FR-8 (FR-4 and FR-5 are web-only).
Exit codes, the stdout/stderr split, and machine-readable output are defined and consistent across commands.
Command naming, long-option flags, and help style match the existing `agentic` CLI conventions, and the design documents that `task delete` deliberately does not prompt.

Non-blocking observations:

- The `task create` / `task update` synopsis and options table list only the tag-relevant options; they omit existing flags such as `--repository-ids`, `--group-id`, and `--harness-id` (cli/src/agentic_cli/cli.py:188-243).
  Since the section documents existing commands, mark the list as tag-relevant or include the full surface so a reader does not take it as complete. `L1 - Cited`
- The Errors prose says an unreachable API "prints `error: ...` to stderr and exits non-zero" (cli-design.md:63, 91), but `safe()` only catches `ApiError`; a connection failure raises `httpx.ConnectError` uncaught, so a traceback would appear rather than the `error:` line (cli/src/agentic_cli/cli.py:60-74).
  This is pre-existing CLI behavior, not introduced by the tag feature: either wrap connection errors as `ApiError` or soften the claim. `L2 - Analyzed`
- `cli-design.md` has frontmatter without a `session_link`, which the shared conventions require for feature artifacts. `L1 - Cited`
- Open Question 1 in the design is a genuine question, not an error path.

## Conflicts

No issues found.
The requirements pull in compatible directions; no pair is mutually exclusive or a priority conflict.
"The web UI filters by a single tag (FR-5)" versus "FR-2 requires all requested tags to match" remains a scope difference, not a contradiction, because NFR-2's multi-tag semantics are never exercised by the single-tag web filter.
`Tags are case-sensitive` versus Open Question 1 (should they be case-insensitive) is a deliberate open question, not a conflict between two requirements.

## Open Questions

Carried forward from the requirements document (requirements.md:226-230):

1. Should tags be case-sensitive (current) or case-insensitive?
2. Should there be a rename or delete-tag-across-tasks operation, or is per-task editing enough?
3. Should there be a limit on the number of tags per task?

These are product-scope decisions, not unverified technical assumptions, so no `/create-assumption` was recorded.
Open Question 1 is the one with real implementation impact (it changes write normalization, filter comparison, and tag-count grouping), so it is still worth resolving before tag-driven views build on the current case-sensitive behavior.

## Verdict

`approved`: the nine prior findings are resolved and no blocking finding remains.
The remaining items above are minor and non-blocking.
