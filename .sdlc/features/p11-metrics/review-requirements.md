---
artifact: requirements
verdict: changes-requested
reviewed_at: 2026-10-12
session_link: http://localhost:10000/?session=ses_ed20dd7b7ffeRNOIfPEWqJEfmH
---

# Review: Requirements (Factory metrics: autonomy rate and yield)

Reviewed `requirements.md` (no `cli-design.md` companion exists beside it, so the CLI Design category is omitted per the skill).
Findings carry an evidence level (`skills/sdlc/references/evidence.md`); the decisive findings cite the artifact line numbers.
One blocking finding (missing acceptance criteria for eight requirements, three of them Must) keeps the verdict at `changes-requested`; the rest are advisory.

## Clarity

No blocking finding.

- **FR-1 does not enumerate the allowed `change class` values** (requirements.md:30).
  The accepted set (feature, bugfix, refactor, chore, docs, test, trivial) appears only in `specification.md:41`, so the requirement as written does not constrain the field.
  Advisory: list the allowed values here, or state that the class is a free-form label. `L1 - Cited` (requirements.md:30, specification.md:41)
- **FR-3's "stamp the timestamp" is singular and unspecified, and it sits against FR-1's "start/end timestamps"** (requirements.md:30, 32).
  `specification.md` uses one column per transition (`verified_at`, `accepted_at`, `closed_at`), which the requirement does not name.
  Advisory: name the stamped field(s) per transition, or say the change carries a transition-timestamp set. `L1 - Cited` (requirements.md:32, specification.md:49-51)
- **The report window is configurable (FR-6) but the baseline's window is not tied to the comparison (FR-7).**
  A stored baseline is measured over a fixed window (the constraints say the reporting window is overridable per request; `specification.md:71` stores `window_days` on the baseline), yet neither requirement says the direction must be computed against the window the baseline was captured over.
  A direction can therefore flip just by changing the request window, which weakens "improving or worsening" as a signal.
  Advisory: state that direction compares a value computed over the baseline's window, or that the baseline and the current value always share a window. `L1 - Cited` (requirements.md:35-36, 54-55)
- **NFR-2's "stay responsive for thousands of changes" is unquantified** (requirements.md:45), and **NFR-4's "usable and legible at phone widths" is unquantified** (requirements.md:47).
  Advisory: give a threshold (for example, "under 200 ms for 5,000 changes") and a viewport width; the project already fixes the primary breakpoint at 760px (`conventions.md:36`). `L1 - Cited` (requirements.md:45, 47)

## Completeness

- **BLOCKING — Acceptance criteria are missing for eight of the fourteen requirements** (requirements.md:57-117).
  Only FR-3, FR-4, FR-5, FR-6, FR-7, and NFR-1 have tagged `gherkin` blocks.
  FR-1, FR-2, and FR-8 are **Must** and have no criterion; FR-9, NFR-2, NFR-3, NFR-4, and NFR-5 are unverified too.
  The project's style requires acceptance criteria as fenced `gherkin` blocks tagged with their requirement ID (`conventions.md:58`), and the checklist asks for a criterion per requirement.
  Without them the change lifecycle (FR-1), the intervention flag that autonomy rate depends on (FR-2), delete cascades (NFR-3), whole-store scope (NFR-5), and the HTTP/CLI surface (FR-8) cannot be verified downstream.
  Suggested resolution: add at least one tagged block per remaining requirement.
  `L1 - Cited` (requirements.md:30-31, 37-38, 45-48, 57-117)

- **FR-7's edge branches have no criterion.**
  FR-7 names five direction values, but its single scenario only exercises `improving` (requirements.md:99-107); the `no-baseline` and `no-data` branches (requirements.md:55, 36) are untested.
  Advisory: add scenarios for a missing baseline and a zero-denominator metric. `L1 - Cited` (requirements.md:99-107, 36, 55)

- **No error or invalid-input criteria for FR-1 and FR-2.**
  Neither an unknown lifecycle status/transition nor an unknown intervention kind is covered (requirements.md:30-31).
  Advisory: add a rejected-invalid-value scenario. `L1 - Cited` (requirements.md:30-31)

- **FR-8 requires a CLI surface, but no `cli-design.md` exists beside the requirements** (FR-8, requirements.md:37; the feature directory holds only `requirements.md` and `specification.md`).
  The skill reviews a CLI design only when present, so this is not scored under CLI Design; it is flagged here as a coverage gap because `/create-cli-design` normally runs when a feature adds commands.
  Advisory: run `/create-cli-design` for the `change` and `metrics` command groups. `L1 - Cited` (requirements.md:37)

## Testability

- **BLOCKING — The eight requirements without acceptance criteria cannot be verified with a concrete test** (requirements.md:57-117).
  This is the same gap recorded under Completeness, restated here as its testability consequence: FR-1, FR-2, FR-8, FR-9, NFR-2, NFR-3, NFR-4, and NFR-5 have no criterion to execute.
  `L1 - Cited` (requirements.md:30-31, 37-38, 45-48, 57-117)

- **NFR-2 gives no quantitative threshold, so it is not measurable** (requirements.md:45).
  Advisory: state a latency budget and the scale it must hold at. `L1 - Cited` (requirements.md:45)

- **The present `gherkin` blocks are otherwise well-formed.**
  Each carries a tag matching its requirement ID, a named `Scenario:`, and at least one `Given`/`When`/`Then` (requirements.md:61-117), so no well-formedness finding applies to them. `L1 - Cited` (requirements.md:61-117)

- **The FR-4 and FR-5 scenarios do not state that the sample changes fall inside the reporting window** (requirements.md:69-87), so a test must assume "now" and the default 30-day window.
  Advisory: state the window in the `Given`, or rely explicitly on the default. `L1 - Cited` (requirements.md:69-87, 54)

- **FR-6's `Then` asserts an internal quantity ("only the older change is in the denominator")** rather than an observable output (requirements.md:89-97).
  Advisory: assert the returned counts and the resulting yield value instead of the denominator alone. `L1 - Cited` (requirements.md:89-97)

## Feasibility

No blocking finding.

- The persistence constraint matches the codebase: new tables are created by `create_all` and new columns by `_ensure_columns()` (`db.py:35`, `db.py:86`), exactly as the constraints state (requirements.md:52). `L1 - Cited`
- Editing the lifecycle and metrics pure functions, exposing two routers, and registering them follow existing patterns: routers are registered in a loop in `main.py:44`, and the SPA mounts routes in `frontend/src/main.js`. Adding `/metrics` there is straightforward. `L1 - Cited`
- NFR-3's cascade delete matches the project's documented practice of explicit, ordered `session.execute(sa_delete(...))` statements because SQLite enforces foreign keys (`conventions.md:28`). `L1 - Cited`
- No external system or new dependency is introduced beyond what the app already uses (FastAPI, SQLModel, Vue, cyclopts), so no new integration risk. `L1 - Cited`
- Scope is moderate (three tables, two routers, two CLI groups, one SPA page) but within one iteration; no Must/Should overload beyond comprehension, and no requirement is technically impractical given the constraints. `L1 - Cited`

## Conflicts

No issues found.
No pair of requirements asserts opposite behaviors or is mutually exclusive:

- FR-5 and FR-6 pull in the same direction (FR-5 defines yield; FR-6 fixes the denominator by excluding unobserved changes). `L1 - Cited` (requirements.md:34-35)
- FR-1's "change belongs to exactly one task" matches the constraint at requirements.md:53. `L1 - Cited`
- FR-4's per-change autonomy and NFR-5's whole-store, never-per-person scope are compatible; the requirement never measures an individual. `L1 - Cited` (requirements.md:33, 48)
- FR-6's configurable window versus FR-7's baseline is an under-specification (recorded under Clarity), not a contradiction, because it can be resolved by fixing the comparison window. `L1 - Cited` (requirements.md:35-36)

## Open Questions

Carried forward from the requirements document (requirements.md:125-127):

1. Should the system auto-create a change when an agent run starts, or is explicit recording enough for the first iteration?
2. Should a change's class default from the task's tags, or is an explicit class always required?
3. Should yield also count changes rejected at verification, on top of changes reverted after acceptance?

Question 3 carries real implementation impact: it changes FR-5's numerator and denominator and the yield definition in the specification (`specification.md:83, 87`), so it is worth resolving before yield is implemented and baselined.
Questions 1 and 2 affect FR-1's write path but not the metric formulas.
These are product-scope decisions, not unverified technical assumptions, so no `/create-assumption` was recorded (matching the p9-tags precedent).

## Verdict

`changes-requested`: the requirements are clear, feasible, and internally consistent, but eight of fourteen requirements, including three Must requirements (FR-1, FR-2, FR-8), have no acceptance criteria, so the artifact cannot move to verification until each requirement carries a tagged `gherkin` block.
The remaining findings are advisory.
