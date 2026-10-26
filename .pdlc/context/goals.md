# Goals

Time horizon: 2026 Q4 through 2027 Q2, reviewed monthly.

## Objectives

### O1: Resuming any task takes under a minute

- **KR1:** At least 80% of in-flight tasks have a summary and next steps refreshed within the last 7 days, measured from task fields, by 2027-03-31.
- **KR2:** The median time from opening a task to having usable context (summary plus next steps visible) is under 60 seconds, measured in a monthly self-check on 5 sampled tasks, from 2027-01-31.

### O2: Agent autonomy is measured and improving

- **KR1:** Autonomy rate and yield baselines are recorded from at least 20 accepted changes by 2026-12-31.
- **KR2:** Autonomy rate improves against its baseline for two consecutive monthly reviews by 2027-06-30.

### O3: The full work loop works from a phone

- **KR1:** Triage (inbox, stack, deadlines), task park and resume, and run status are all completable in the PWA at 360px width, verified per release from 2026-12-31.

## Metrics

| ID | Name | Type | Baseline | Target / Floor | Owner | Source |
|---|---|---|---|---|---|---|
| SM-1 | Context freshness share | success | unset | >= 80% of in-flight tasks within 7 days | owner | task summary/next-step timestamps via `GET /api/tasks` |
| SM-2 | Autonomy rate | success | unset (first 30-day window) | improving vs baseline | owner | recorded changes via MetricsView / `agentic change list` |
| SM-3 | Yield | success | unset (first window + observation period) | improving vs baseline | owner | recorded changes via MetricsView |
| SM-4 | Resume time (median) | success | unset | < 60s on sampled tasks | owner | monthly self-check sample |
| GM-1 | Persisted data survives restarts | guardrail | holds today | 0 lost tasks, items, events, changes | owner | restart smoke test against `~/.agentic` |
| GM-2 | Mobile usability | guardrail | holds today | every view usable at 360px before done | owner | mobile check in review per UI change |
| GM-3 | Run failures are visible | guardrail | holds today | 0 runs stuck without a status or error event | owner | run status query / run transcript |

Every metric must have a measurement source. Metrics without a source are wishes.

## Notes

- Baselines are deliberately unset until SM-2 and SM-3 have their first recorded window; targets that would need invented numbers are set relative to baseline instead.
- Autonomy rate and yield only mean something once changes are recorded; recording them is part of O2, not a precondition for it.
