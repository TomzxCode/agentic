---
title: "Process view: flow and cycle time"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: Process view: flow and cycle time

## Overview

The SDLC process is read as a production line: tasks are work items that move between stations, where the backlog is the raw-material queue, in progress is the work station, blocked is the rework and waiting area, done is finished goods, and archived goods have shipped.
`process_flow.py` holds the pure manufacturing metrics (station inventory, flows, cycle time, dwell, weekly flow, Little's law, queue pressure, cumulative flow, aging WIP, touch efficiency, forecast, outcomes), `routers/process.py` loads tasks and their recorded status changes from the timeline and exposes `GET /api/process`, and the SPA's Process page draws the line.
`cycle_time.py` derives three cycle-time metrics from GitHub issue and pull request events (issue close, review wait, review to merge), and `routers/metrics.py` exposes them per repository at `GET /api/metrics/cycle-time` behind the Metrics page's cycle-time panel.
This feature is bounded against p11-metrics, which covers the factory metrics autonomy rate and yield computed from change records; p32 covers the flow and production-line view of tasks and the GitHub-derived cycle times, and computes nothing from changes.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | See where work piles up, how long an item takes to travel the line, and which station holds the bottleneck |
| Agent | Read the same numbers through the HTTP API without the web UI |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall map every task status onto a station (open to backlog, in_progress to in progress, blocked to blocked, done to done, archived to archived), with unknown statuses falling back to the backlog |
| FR-2 | Must | The system shall walk each task's station timeline from creation, applying a recorded transition only when the task is in the station it claims to leave, and correcting the last entry to the current station when history is missing |
| FR-3 | Must | The system shall report per-station inventory: how many items sit there now and how long they have been waiting (oldest, median, and newest queue age) |
| FR-4 | Must | The system shall report station flows: how many items moved between each pair of stations inside the window, plus arrivals into the backlog (creations) and completions out of it |
| FR-5 | Must | The system shall report the cycle time of items completed in the window (creation to done) as a distribution (count, mean, median, p10, p90, fastest, slowest) and as a fixed set of duration histogram buckets |
| FR-6 | Must | The system shall report per-station dwell for completed items: how many waited in the station and their mean and median wait |
| FR-7 | Must | The system shall rank bottlenecks: each station's share of the completed items' total cycle time |
| FR-8 | Must | The system shall report queue pressure for each active station: arrivals, departures, net flow, a filling/draining/steady verdict, and weekly inventory samples for a sparkline |
| FR-9 | Must | The system shall report cumulative flow samples: one snapshot per day of the backlog, in progress, and blocked inventory plus cumulative completions |
| FR-10 | Must | The system shall report the aging work-in-progress list: every item currently in an active station with its station, entry time, and age, longest wait first |
| FR-11 | Must | The system shall report flow efficiency from focus-stack sessions: touch time clipped to each completed trip, covered completions, and touch as a share of cycle time |
| FR-12 | Must | The system shall forecast when the items currently on the line will finish by resampling the window's weekly completions (Monte Carlo, fixed seed) and reporting P50 and P85 as weeks and dates |
| FR-13 | Must | The system shall report where the window's arrivals stand now (done, archived, still active) and the weekly arrivals-versus-completions chart data |
| FR-14 | Must | The system shall report Little's law: average work in process as the exact time integral over the active stations, throughput as completions per day, and the cycle time the queue depth implies |
| FR-15 | Must | `GET /api/process` shall build the report from the tasks and the `updated` timeline events that carry a `changes.status` before/after pair, skipping events whose diff is missing, unparseable, or not a real station move, with a `days` window parameter (1 to 730, default 90) |
| FR-16 | Must | The system shall derive three cycle-time metrics from GitHub records: issue close (open to close), review wait (first review request to the first review after it), and review to merge (first review to merge), each as an overall median plus per-bucket medians over the window |
| FR-17 | Must | `GET /api/metrics/cycle-time` shall return the three series per repository with a GitHub remote (optional `repository_id`, `days`, `bucket_days`, `refresh`), reading GitHub through the cached fetcher and reporting a per-repository error instead of failing the whole report |
| FR-18 | Must | The Process page shall draw the production line (stations with queue counts and median waits, arrows labeled with move counts, other moves listed), the cumulative flow diagram, the bottleneck takeaway with wait shares and queue pressure rows, the aging WIP list, the cycle-time cards and histogram, the flow cards with the weekly chart, the forecast, and the dwell breakdown, with a window selector (30, 90, 180, 365 days) |
| FR-19 | Should | The Metrics page's cycle-time panel shall render each repository's three series with a per-bucket trend chart, formatted through the shared `cycleTime.js` helpers, with a refresh action and a no-remote empty state |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Testability | `process_flow.py` and `cycle_time.py` expose pure functions that take values and return values, so they are tested without a database, network, or clock |
| NFR-2 | Must | Correctness | Buckets and windows never drop empty periods: cycle-time histogram buckets sum to the sample, trend buckets cover the window continuously, and weekly spans close the window exactly |
| NFR-3 | Must | Determinism | The forecast uses a seeded random generator (default seed 0), so the same inputs produce the same P50 and P85 |
| NFR-4 | Should | Performance | The cycle-time GitHub reads are cached per repository (ten minutes) and fetched a few at a time across repositories |
| NFR-5 | Must | Usability | The production-line diagram scrolls sideways on phones instead of scaling its text below readability, and every chart carries an accessible name |
| NFR-6 | Must | Scope | Metrics are computed over tasks and GitHub records only; no endpoint accepts a person identifier, matching the p11 boundary against per-person measurement |

## Constraints

- Transitions come from the timeline's `updated` events; the module never guesses a move that was not recorded.
- `process_flow.py` keeps the purity convention shared with `metrics.py` and `cycle_time.py`; database access lives in the routers.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Unknown statuses fall back to the backlog
      Given a task whose status is not one of the five known statuses
      When the station of the task is computed
      Then the task is counted in the backlog station
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Out-of-order history cannot corrupt the walk
      Given a task that entered in progress, with a second open-to-in-progress event recorded later
      When the station timeline is walked
      Then the second event is ignored because the task is no longer in the backlog
      And with no recorded history at all the timeline collapses to the current station entered at creation
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Station inventory with queue ages
      Given tasks in each station with known creation and transition times
      When the station inventory is computed
      Then each station reports its count and the oldest, median, and newest age in hours
      And an empty station reports counts of zero with no ages
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Flows count only moves inside the window
      Given transitions inside and outside the reporting window
      When the station flows are computed
      Then only the moves inside the window are counted per station pair
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Cycle time of the window's completions
      Given one task created nine days before it reached done inside the window
      When the cycle-time distribution is computed
      Then the median is 216 hours and the duration lands in the 1-2 week histogram bucket
      And the histogram buckets sum to the number of completions
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Dwell covers only stations an item waited in
      Given a completed item that spent two days in the backlog and seven in progress
      When the dwell is computed
      Then the backlog and in progress rows carry counts and medians
      And the blocked row reports zero items with no median
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Wait shares sum to one
      Given completed items with per-station waits
      When the wait shares are computed
      Then every station's share is its total wait over the grand total and the shares sum to 1.0
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: Queue trend reads the net flow
      Given a backlog with four arrivals and three departures in the window
      When the queue pressure is computed
      Then the backlog reports arrived 4, departed 3, and the filling trend
      And each active station carries one weekly inventory sample per week ending at the current count
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: One sample per day, completions only grow
      Given a 90-day window with one completion
      When the flow samples are computed
      Then there is one sample per day inclusive of both ends
      And the completed counts are non-decreasing and end at the current inventory
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: Aging list, longest wait first
      Given tasks in the backlog, in progress, and blocked stations plus one done task
      When the WIP list is computed
      Then only active-station items appear, ordered by age with the blocked item first
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: Touch time clipped to the trip
      Given a completed item with sessions inside, overlapping, and after its trip
      When the touch stats are computed
      Then only the session time inside creation-to-completion counts
      And an item nobody focused reads as zero touched, not as missing data
    ```

- [ ] **FR-12**

    ```gherkin
    @FR-12
    Scenario: Forecast from weekly history
      Given two items on the line and a history of one completion per week
      When the forecast is computed
      Then P50 and P85 are two weeks with the dates two weeks out
      And a window with no completions supports no forecast, leaving the quantiles unset
      And an empty line finishes now
    ```

- [ ] **FR-13**

    ```gherkin
    @FR-13
    Scenario: Outcomes split the window's arrivals
      Given tasks created inside and outside the window in mixed dispositions
      When the outcomes are computed
      Then only in-window arrivals are counted, split into done, archived, and active
    ```

- [ ] **FR-14**

    ```gherkin
    @FR-14
    Scenario: Little's law integrates work in process
      Given tasks with known active-station spans inside the window
      When Little's law is computed
      Then average WIP equals total active hours over window hours
      And throughput is completions per day and the implied cycle time is WIP over throughput in hours
    ```

- [ ] **FR-15**

    ```gherkin
    @FR-15
    Scenario: The report is built from recorded status changes
      Given two tasks created through the API, one moved to in progress and then done
      When GET /api/process is called
      Then the stage counts, flows, cycle time, histogram, weekly flow, pressure, and outcomes match the recorded moves
      And days defaults to 90 and is bounded to 1 through 730
    ```

- [ ] **FR-16**

    ```gherkin
    @FR-16
    Scenario: Review wait runs from the request to the review after it
      Given a pull request whose first review predates its review request
      When the review wait is computed
      Then the interval runs from the first request to the first review submitted after it
      And a pull request with no request or no later review is skipped
    ```

- [ ] **FR-17**

    ```gherkin
    @FR-17
    Scenario: Cycle-time report per repository
      Given a repository with a GitHub remote whose data is available
      When GET /api/metrics/cycle-time is called with its id
      Then the report carries the repository's full name and all three series with bucketed medians
      And a repository without a GitHub remote is rejected with 400
      And an unreadable repository appears with an error entry instead of failing the report
    ```

- [ ] **FR-18**

    ```gherkin
    @FR-18
    Scenario: The Process page renders the report
      Given a process report from the API
      When the Process page is opened
      Then the five stations, edge counts, other moves, cumulative flow bands, bottleneck takeaway and pressure rows, WIP links, cycle-time cards, histogram, flow cards, forecast, and dwell rows are all shown
      And changing the window selector reloads the report with the chosen days
    ```

- [ ] **FR-19**

    ```gherkin
    @FR-19
    Scenario: Cycle-time trends on the Metrics page
      Given a repository with cycle-time series
      When the Metrics page's cycle-time panel renders
      Then each series shows its median and a bar per bucket drawn against the largest median
      And a bucket with no data renders as an empty bar
    ```

## Conflicts

None identified yet.

## Open Questions

1. The drawn production line hides moves outside the five drawn edges in an "other moves" list; whether a common nonstandard move (done back to backlog) deserves its own arrow is a design call, not answerable from the code.
