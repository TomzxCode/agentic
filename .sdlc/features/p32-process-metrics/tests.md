---
title: "Process view: flow and cycle time"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Test Plan: Process view: flow and cycle time

## Scope

Covers the pure flow and cycle-time modules, the `GET /api/process` router, the `GET /api/metrics/cycle-time` endpoint, and the Process page rendering.
Out of scope: real GitHub calls (fetches are monkeypatched), and the p11 factory metrics.

## Unit Tests

| ID | Description | File |
|---|---|---|
| TC-1 | `quantile` interpolates between order statistics and returns None for an empty sample | test_process_flow.py |
| TC-2 | `stage_timeline` walks forward, ignores a transition out of a station the task has left, and collapses missing history to the current station | test_process_flow.py |
| TC-3 | Station inventory counts and ages, with empty stations carrying no ages | test_process_flow.py |
| TC-4 | Station flows count only moves inside the window | test_process_flow.py |
| TC-5 | Histogram buckets sum to the sample across all eight buckets | test_process_flow.py |
| TC-6 | Dwell accumulates time before completion per station | test_process_flow.py |
| TC-7 | Wait shares split cycle time, sum to 1.0, and only waited-in stations carry counts | test_process_flow.py |
| TC-8 | Queue pressure reads arrivals (creations included), departures, net trend, and weekly inventory samples | test_process_flow.py |
| TC-9 | Little's law integrates work in process exactly and derives the implied cycle time | test_process_flow.py |
| TC-10 | Flow samples snapshot daily, completions only grow, and the last sample matches the current inventory | test_process_flow.py |
| TC-11 | WIP items sort longest wait first and exclude done and archived tasks | test_process_flow.py |
| TC-12 | Touch stats clip sessions to the trip; an open session is clipped, a later session does not count, and no sessions read as zero touched | test_process_flow.py |
| TC-13 | Forecast resamples weekly history (deterministic with seed), supports no forecast without completions, and finishes an empty line now | test_process_flow.py |
| TC-14 | Outcomes split window arrivals by disposition and drop older arrivals | test_process_flow.py |
| TC-15 | Issue close keeps only issues closed in the window | test_cycle_time.py |
| TC-16 | Review wait runs to the first review after the request and skips pulls without a request or a later review | test_cycle_time.py |
| TC-17 | Review to merge counts only merged pulls reviewed before the merge | test_cycle_time.py |
| TC-18 | Trend buckets keep empty periods and take per-bucket medians | test_cycle_time.py |
| TC-19 | `build_series_for` returns all three metrics with their medians | test_cycle_time.py |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-20 | `build_report` end to end over a four-task scenario | fixed tasks and transitions | arrivals, completions, cycle time, histogram, weekly stub week, shares, pressure, samples, WIP, touch, forecast, and outcomes all consistent |
| TC-21 | GET /api/process computes from recorded status changes | two tasks created and moved through the API | stage counts, flows, cycle time, histogram sum, throughput, weekly rows, shares sum to 1, pressure trends, 31 daily samples, WIP, touch, forecast, and outcomes match |
| TC-22 | GET /api/metrics/cycle-time reads GitHub and buckets it | repository with a GitHub remote, fetch monkeypatched | one repository entry with full name and three series with bucketed medians |
| TC-23 | GET /api/metrics/cycle-time rejects a repository without a GitHub remote | local-only repository | 400 with a "no GitHub remote" detail |
| TC-24 | ProcessView renders the report and reloads on window change | monkeypatched `api.process.get` | stations, edge labels, other moves, cards, histogram, bottleneck bar, pressure rows, CFD bands, WIP links, efficiency, forecast, outcomes, and dwell all rendered; selector passes the new days |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-25 | A task status outside the five known values | it counts in the backlog |
| TC-26 | A transition whose from-station does not match the walk | it is ignored |
| TC-27 | A pull request whose review predates the request | it does not answer the request; wait comes from the next review |
| TC-28 | An empty cycle-time sample | every summary field is None rather than zero |
| TC-29 | No completions in the window | dwell and wait shares show the empty state and queue pressure still renders |
| TC-30 | A repository whose GitHub read fails | the report keeps the other repositories and carries an error entry naming the GitHub read |

## Test Infrastructure

- `backend/tests/test_process_flow.py` and `backend/tests/test_cycle_time.py` use fixed UTC datetimes (`NOW`) and the app's `TestClient`; no database fixtures beyond the app's startup.
- GitHub reads are monkeypatched at `agentic.routers.metrics.fetch_github_cycle_time`; the cycle-time API test registers a real temporary git repository to get a repository row.
- `frontend/src/__tests__/processView.test.js` mounts the view with a mocked `api.process.get` and a stubbed `RouterLink`.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-25 |
| FR-2 | TC-2 |
| FR-3 | TC-3 |
| FR-4 | TC-4 |
| FR-5 | TC-5, TC-20 |
| FR-6 | TC-6, TC-29 |
| FR-7 | TC-7 |
| FR-8 | TC-8 |
| FR-9 | TC-10 |
| FR-10 | TC-11 |
| FR-11 | TC-12 |
| FR-12 | TC-13 |
| FR-13 | TC-14 |
| FR-14 | TC-9 |
| FR-15 | TC-20, TC-21 |
| FR-16 | TC-15, TC-16, TC-17, TC-27 |
| FR-17 | TC-22, TC-23, TC-28, TC-30 |
| FR-18 | TC-24 |
| FR-19 | TC-18, TC-24 (MetricsView side covered by frontend `metrics.test.js`) |
| NFR-1 | TC-1 to TC-19 (all pure, no database or network) |
| NFR-2 | TC-5, TC-18, TC-20 |
| NFR-3 | TC-13 |
| NFR-5 | TC-24 (diagram container and aria labels asserted in the view test) |
