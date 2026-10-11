---
date: "2026-10-11"
scope: "FEAT-p4"
entry: "code"
flags: "fix: false, create-issues: false"
status: complete
---

# Propagation Report

**Date:** 2026-10-11
**Scope:** FEAT-p4 (p4-worktrees). Only this feature is connected to the change set; the other features under `.sdlc/features/` reference worktrees generically and do not name the default branch scheme.
**Entry:** code (default branch naming changed from a deterministic `agentic/<slug>-<id4>` to a random `agentic/<adjective>-<noun>` retried until free).

## Change Set

- `backend/src/agentic/services.py`: added `random_name()` and `random_branch_name(repo_path)`.
- `backend/src/agentic/routers/worktrees.py`: default branch is now `payload.branch or random_branch_name(repo.path)`.
- `backend/tests/test_services.py`: tests for the name format, prefix, and retry-on-collision.
- `.sdlc/features/p4-worktrees/specification.md`: branch-default decision and services list updated by the author as part of the change.

## Consistency Status

| Feature | Downward updates | Upward drift | IDs | Review order | Status |
|---|---|---|---|---|---|
| FEAT-p4-worktrees | 1 applied / 2 proposed | 2 findings | clean | n/a (no review files) | drifted |

## Updates (downward)

| # | Artifact | Edge | Change | Resolution | Status |
|---|---|---|---|---|---|
| 1 | `backend/tests/test_services.py` | code -> tests | default branch is random, not deterministic | tests for `random_name`, `random_branch_name` prefix, and retry-on-collision | applied |
| 2 | `specification.md` | code -> specification (reverse edit by author) | author updated §Technical Decisions and Overview | mark `status: in-review` and bump `revision` so `/review-specifications` re-approves against the new behavior | proposed |
| 3 | (docs) | code -> documentation | README.md and cli/README.md describe worktrees but never state the default branch scheme | no rewrite needed | clean |

## Questions Raised

| # | Edge | Disagreement | Resolutions | Where recorded |
|---|---|---|---|---|
| 1 | requirements ↔ code | FR-1 and its `@FR-1` acceptance criterion still require the deterministic `agentic/<slug>-<task-id-prefix>` scheme the code no longer uses | (a) update FR-1 and the criterion to the random scheme, or (b) revert the code to the deterministic scheme | this report (report only) |

The user already chose the random scheme when approving the fix, so resolution (a) is the expected one; it is listed as a question only because it rewrites an upstream requirement, which this read-only pass does not do.

## Traceability Matrix

### FEAT-p4-worktrees

| FR / NFR | Spec section | Plan phase | Task(s) | Test(s) | Code location | Docs | Issue AC |
|---|---|---|---|---|---|---|---|
| FR-1 | §Technical Decisions, row "Branch default" | (none) | (none) | `test_random_name_is_two_words`, `test_random_branch_name_prefixes_agentic`, `test_random_branch_name_retries_when_branch_exists` | `services.py:128` `random_branch_name`, `routers/worktrees.py:39` | (none) | FR-1 (stale) |
| FR-2 | §Sequences, "Create a worktree" | (none) | (none) | (none) | `services.py:50` `create_worktree` | (none) | FR-2 |
| FR-3 | §Technical Decisions, row "Path default" | (none) | (none) | (none) | `services.py:426` `worktree_path` | (none) | FR-3 |
| FR-4 | §API Contracts, GET row | (none) | (none) | (none) | `routers/worktrees.py:20` | (none) | (none) |
| FR-5 | §API Contracts, DELETE row | (none) | (none) | (none) | `routers/worktrees.py:56`, `services.py:64` `remove_worktree` | (none) | FR-5 |
| NFR-1 | §API Contracts, error codes | (none) | (none) | (none) | `routers/worktrees.py:43` | (none) | NFR-1 |
| NFR-2 | (not stated) | (none) | (none) | (none) | `services.py:21` `_git` timeouts | (none) | NFR-1 scenario |

The feature has no `plan.md`, `tasks/`, `tests.md`, `lifecycle.md`, `telemetry.md`, or `observability.md`, so those columns stay empty. This is the feature's existing shape, not drift introduced by this change.

## Summary

| Class | Critical | High | Medium | Low | Total |
|---|---|---|---|---|---|
| Orphan upstream | 0 | 2 | 0 | 0 | 2 |
| Orphan downstream | 0 | 0 | 0 | 0 | 0 |
| Broken reference | 0 | 0 | 0 | 0 | 0 |
| Status inversion | 0 | 0 | 0 | 0 | 0 |
| **Total** | **0** | **2** | **0** | **0** | **2** |

## Findings

### 1. FR-1 and its acceptance criterion describe the old default branch scheme

**Feature:** FEAT-p4-worktrees
**Class:** Orphan upstream
**Severity:** High
**Direction:** Upward
**Edge(s):** requirements -> code
**Location:** `.sdlc/features/p4-worktrees/requirements.md:25` (FR-1) and `:52` (`Then a branch named "agentic/<slug>-<id4>" is created`)
**Finding:** The requirement fixes the default branch to `agentic/<slug>-<task-id-prefix>`, but the code now defaults to a random `agentic/<adjective>-<noun>` retried until free. The requirement and the code disagree on the naming scheme.
**Impact:** The requirement no longer describes shipped behavior, so the acceptance criterion cannot pass and the traceability from requirement to code is broken.
**Recommendation:** Update FR-1 to require a unique, memorable default branch name (for example `agentic/<adjective>-<noun>`), and rewrite the `@FR-1` `Then` line to assert a generated branch name rather than a literal pattern. The specification already reflects the new scheme.

### 2. `conventions.md` states the old worktree branch format

**Feature:** FEAT-p4-worktrees (context-level premise)
**Class:** Orphan upstream
**Severity:** Medium
**Direction:** Upward
**Edge(s):** code -> context
**Location:** `.sdlc/context/conventions.md:49`
**Finding:** The Branching section says agent worktrees use `agentic/<slug-of-title>-<first-4-chars-of-task-id>`, for example `agentic/cli-driven-problem-2f43`. The code no longer produces that form.
**Impact:** The stated convention contradicts the implementation, so a reader following conventions.md will expect the wrong branch names.
**Recommendation:** Rewrite the sentence to describe the random `agentic/<adjective>-<noun>` scheme and its collision retry.

## Fixes Applied

None. This pass ran without `--fix`, so it is read-only.

## Recommended Actions

| Priority | Action | Owner decision |
|---|---|---|
| High | Update FR-1 and the `@FR-1` acceptance criterion in `requirements.md` to the random naming scheme | confirm (user already chose random) |
| Medium | Update `.sdlc/context/conventions.md:49` to the random naming scheme | confirm |
| Low | Set `specification.md` `status: in-review` (and bump `revision`) so `/review-specifications` re-approves it against the change | confirm |
| Low | Consider a `tests.md` for FEAT-p4; the naming helper now has tests but the feature still has no test artifact | optional |
