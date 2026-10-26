# Roadmap

Based on outcomes, not a delivery calendar. Expected to change.
Initiative IDs (INIT-N) are assigned when `/pdlc discover` starts an initiative; candidates below are named, not yet discovered.

## Now (high confidence, capacity-assigned)

| Initiative | Outcome (objective) | Owner | Confidence |
|---|---|---|---|
| Record the change lifecycle (baseline autonomy rate and yield) | O2 | owner | High |
| Harden the run queue: supervise the worker, restart or fail stalled runs loudly | O1, GM-3 | owner | High |
| Context freshness loop: scheduled context refresh for stale in-flight tasks | O1 | owner | High |

## Next (medium confidence)

| Initiative | Outcome (objective) | Owner | Confidence |
|---|---|---|---|
| Phone triage pass: tighten inbox, stack, and deadlines flows at 360px | O3 | owner | Med |
| Measure resume time and remove the top friction found | O1 | owner | Med |
| People and deferral polish: alias coverage so Slack and GitHub handles merge cleanly | O1 (parked tasks return on time) | owner | Med |

## Later (plausible, not yet validated)

| Initiative | Outcome (objective) | Owner | Confidence |
|---|---|---|---|
| Read-only remote view of the tracker (would need a scope decision on "no cloud") | O3 | owner | Low |
| Cross-task portfolio reporting over recorded changes (trends per repository or class) | O2 | owner | Low |
| Agent-authored initiatives: agents file discovery briefs the owner gates | vision (agents maintain the tracker) | owner | Low |

## Capacity Check

- **Available capacity:** one owner, part-time, with coding agents doing most implementation.
- **Now-column demand:** three initiatives, all small enough to land in days with agent help.
- **Over/under allocation:** balanced; do not add a fourth Now initiative until one closes.

## Sequencing Rationale

Measurement comes first because every later decision (what to improve, whether agents are getting more autonomous) needs the baseline the tracker itself produces.
Run-queue hardening is second because agent runs are the product's core action and a silently stalled run breaks trust in everything else.
The context freshness loop third because it makes the resume promise automatic instead of manual.
Phone triage waits for the loop to be automatic; there is no value in triaging from a phone until the tracker keeps itself current.

## Grounding

- Everything in Now is grounded in a known gap or an existing but unexercised capability: changes are recordable today but rarely recorded; the worker is a bare process with no supervisor (restarts drop in-flight runs); context refresh exists but runs on demand only.
- The Later column deliberately includes items that would change scope (a remote view conflicts with the no-cloud non-goal) and says so.
