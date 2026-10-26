---
title: "Pull-request review queue"
status: done
---

# Requirements: Pull-request review queue

## Overview

Reviewing a pull request is several steps, and the reports those steps write land as files under the user-global `~/.sdlc` store, invisible unless the user opens that tree.
At the same time GitHub knows which pull requests are waiting for the user's review, including ones no review has ever run against.
This feature turns both sources into one review queue: a background scan stores the pull requests awaiting a review, the report store supplies what each review step concluded, ghx overlays the live GitHub fields, and the must/should/may findings the skills recorded can be selected and handed to an agent.
The scan's `first_seen_at` also feeds the review SLO nudge, which is specified separately in `p18-review-slo` and out of scope here.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | See in one place which pull requests await review, what each review step found, and whether a merge is blocked |
| Coding agent | Read the queue, the reports, and the findings through the API, and receive the findings prompt the Share action builds |
| Review skills | Have the reviewer's decisions on findings recorded beside the findings in their own state files |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall search GitHub for pull requests awaiting the user's review with two searches, `review-requested:@me` and `reviewed-by:@me`, run through `gh search prs`, and store the merged set keyed by repository and number, with the requested source winning on overlap. |
| FR-2 | Must | The scan shall run on a cadence from the `review_scan_interval` setting, checked on a background tick; an empty or off value disables it, and a manual "Scan now" run ignores the cadence. |
| FR-3 | Must | Each scan shall replace the stored set: found pull requests are upserted and the rest deleted, while `first_seen_at` is preserved for rows that survive. |
| FR-4 | Must | A scan whose searches could not run at all shall record the error, leave the stored set untouched, and be retried on the next cadence; one failing search is tolerated when the other ran. |
| FR-5 | Must | The scan shall filter by repository policy: a repository's own `review_scan` policy (default, include, exclude) wins, the app-wide `review_scan_default` decides for the rest, and authors on the exclude list (default `dependabot[bot]`) are dropped. |
| FR-6 | Must | The stored set shall stop feeding the queue as soon as its repository's policy excludes it, before the next scan runs. |
| FR-7 | Must | The API shall report the scan state (interval, enabled, default, stored count, last run, next run, found, kept, error, origin) and offer a forced manual run. |
| FR-8 | Must | The settings API shall reject a malformed `review_scan_interval` and a `review_scan_default` that is not include or exclude, and the repository API shall accept a per-repository `review_scan` policy. |
| FR-9 | Must | The system shall read every pull-request review directory under the user-global store (both the `{owner}/{repo}/pull-requests/{n}` and the bare `{repo}/pull-requests/{n}` layout) as one queue row per pull request, tolerant of owner and repository casing. |
| FR-10 | Must | Each row shall carry, per review step (assess-pr-risk, summarize-behavior-changes, analyze-test-coverage, validate-pr, verify-pr, review-pr), the newest report's verdict, report path, modified time, and reviewed commit, with risk and confidence for assess-pr-risk taken from the marker or the report body. |
| FR-11 | Must | A step with an in-progress marker (`<step>.<sha>.in-progress`) matching the head commit shall be shown as running with its start time; a marker for an older commit is ignored, and with no known head any marker counts. |
| FR-12 | Must | A step whose newest report does not cover the newest reviewed commit shall be marked stale, and every chain step after a stale chain step is stale too. |
| FR-13 | Must | Each row shall carry a merge-readiness signal (red, yellow, green) computed from the step verdicts, the staleness, the draft flag, and the assess route, plus a status of ready, needs-review, or unreviewed. |
| FR-14 | Must | The queue shall overlay each row's GitHub fields (title, url, author, state, creation time, review decision, draft flag, head commit) from ghx, keeping the store's snapshot for any field ghx cannot answer. |
| FR-15 | Must | A row whose pull request the app tracks as a GitHub item shall take the item's title, url, state, and draft flag, and carry the ids of the tasks the item is associated to. |
| FR-16 | Must | Pull requests the scan found but that have no reports yet shall appear as rows with empty steps, a yellow readiness light, status unreviewed, and their request source; a store row the scan also found carries the source too. |
| FR-17 | Must | The API shall serve the whole queue, a task-scoped queue built from the pull requests the task's items link to, and single reports by repository and relative path, with reports over 1 MB truncated and path escapes rejected. |
| FR-18 | Should | ghx lookups for rows without cached metadata shall run concurrently, and results shall be reused briefly so a page reload does not shell out again; `refresh` bypasses the cache. |
| FR-19 | Must | The system shall collect the must, should, and may findings from each skill's findings-state file (`review.yaml`, `validate.yaml`, `verify.yaml`) under the PR's review directory, in severity order, reading files that are not valid YAML tolerantly. |
| FR-20 | Must | The reviewer's include or skip decision shall be written onto the finding's own entry (`decision`, `decided_at`) with a line-preserving edit; a batch applies all or nothing, an unknown finding answers 404 and writes nothing, and a decision outside include or skip answers 400. |
| FR-21 | Should | The web app shall show the queue at `/reviews` as one row per pull request with a column per review step and the readiness light, filterable by status, drafts, approval, reviewed state, repository, author, and search, with those choices remembered on the device. |
| FR-22 | Should | The Share action shall list the PR's findings grouped by severity, preselect the actionable must and should findings with an earlier recorded decision winning, preview the prompt, and start an agent run on a linked task, offering to import a task when none is linked. |
| FR-23 | Should | The Settings review requests section shall edit the cadence, the app-wide default, the per-repository policies, and the review SLO durations, show the scan's last pass, and offer a Scan now button. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Performance | GitHub metadata lookups shall be cached in process (300 s on success, 60 s on failure) and fetched concurrently, and a task-scoped read shall enrich only that task's pull requests. |
| NFR-2 | Must | Resilience | A failed ghx lookup or a failed scan leaves the queue renderable from the store's snapshot; no failure empties the queue. |
| NFR-3 | Must | Security | Report reads resolve inside the PR directory only, and the app posts nothing to GitHub: decisions and findings travel through files and agent runs. |
| NFR-4 | Must | Data integrity | A stored scan row is unique per (repository, number), and `first_seen_at` survives every scan, which the review SLO depends on. |
| NFR-5 | Should | Usability | The queue, its filters, and the findings modal stay usable at phone widths, and filter choices persist in localStorage rather than in settings. |

## Constraints

- The report store is the user-global `AGENTIC_SDLC_DIR` tree shared with the review skills; the app reads and writes only what the skills' own conventions define.
- The scan goes through the `gh` CLI because ghx caches reads but has no search qualifiers.
- Scan rows live in the `reviewrequest` table; report state and findings are never copied into the database.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Two searches make one set
      Given a pull request with my review requested and another I already reviewed
      When the scan runs
      Then both are stored, the first as requested and the second as reviewed
      And a pull request both searches find is stored once as requested
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: The cadence decides
      Given a review scan interval of one hour
      When the background tick fires before the hour has passed
      Then the scan does not run
      When the interval is cleared or set to off
      Then the scan is skipped until a Scan now is pressed
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: A scan replaces the set
      Given a stored pull request the last scan found
      When a scan no longer finds it but finds a new one
      Then the old row is deleted and the new row is stored
      And a pull request both scans found keeps its first_seen_at
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: A broken gh never empties the queue
      Given gh is missing or not authenticated
      When the scan runs
      Then the stored set is unchanged and the error is recorded
      When only one of the two searches fails
      Then the other search's results are still stored
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Policies and excluded authors filter the scan
      Given a repository marked exclude, an unmarked repository, and an app default of include
      When the scan runs
      Then the excluded repository's pull requests are not stored and the rest are
      When a found pull request is authored by dependabot[bot]
      Then it is not stored
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: A newly excluded repository drops out at once
      Given stored scan rows for a repository
      When that repository's policy is set to exclude
      Then its rows stop appearing in the queue before the next scan runs
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: The scan state is readable
      Given a scan that last ran with an error
      When the scan state is read
      Then it carries the interval, the last and next run, the found and kept counts, and the error
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: Malformed scan settings are rejected
      Given the settings API
      When review_scan_interval is saved as "soon"
      Then the API answers 422 naming review_scan_interval
      When review_scan_default is saved as "maybe"
      Then the API answers 422 naming review_scan_default
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: Every store directory becomes a row
      Given review directories under owner/repo/pull-requests/7 and bare repo/pull-requests/8
      When the queue is read
      Then both pull requests appear, whatever the owner and repository casing
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: A step reports its newest run
      Given a review step with two reports on different commits
      When the queue is read
      Then the row shows the newest report's verdict, path, modified time, and reviewed commit
      And the assess step shows its risk and confidence
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: A running step shows a spinner
      Given an in-progress marker for the head commit
      When the queue is read
      Then the step shows as running with its start time
      When the marker names an older commit
      Then the step does not show as running
    ```

- [ ] **FR-12**

    ```gherkin
    @FR-12
    Scenario: Staleness cuts off the chain
      Given a verify-pr report that does not cover the newest reviewed commit
      When the queue is read
      Then verify-pr and review-pr are both stale, and the earlier steps are not
    ```

- [ ] **FR-13**

    ```gherkin
    @FR-13
    Scenario: The readiness light
      Given a PR whose validate-pr verdict is fail
      When the queue is read
      Then its light is red
      When a non-draft PR has no stale steps, a passing review, coverage not failing, and no decide or investigate route
      Then its light is green and its status is ready
      When a PR has no reports at all
      Then its light is yellow and its status is unreviewed
    ```

- [ ] **FR-14**

    ```gherkin
    @FR-14
    Scenario: Live fields win over snapshots
      Given a stored row whose title and state the review run wrote earlier
      When ghx answers with a new title, state, and draft flag
      Then the queue shows ghx's values and keeps the store's url where ghx has none
      When ghx cannot be read
      Then the queue still shows the store's snapshot
    ```

- [ ] **FR-15**

    ```gherkin
    @FR-15
    Scenario: A tracked PR carries its task links
      Given a PR the app tracks as a GitHub item associated to a task
      When the queue is read
      Then the row takes the item's title and state and lists the task id
    ```

- [ ] **FR-16**

    ```gherkin
    @FR-16
    Scenario: A scan find without reports still appears
      Given a pull request the scan found with no review directory
      When the queue is read
      Then it appears with empty steps, a yellow light, status unreviewed, and its request source
    ```

- [ ] **FR-17**

    ```gherkin
    @FR-17
    Scenario: Read a report safely
      Given a report of 2 MB in a PR's review directory
      When it is read through the report endpoint
      Then the content is truncated at 1 MB and flagged as truncated
      When the requested path escapes the PR directory
      Then the API answers 404
    ```

- [ ] **FR-18**

    ```gherkin
    @FR-18
    Scenario: A reload does not shell out again
      Given a queue read that fetched ghx metadata for its rows
      When the queue is read again within the cache window
      Then no new ghx lookup runs
      When the read asks for refresh
      Then the lookups run again
    ```

- [ ] **FR-19**

    ```gherkin
    @FR-19
    Scenario: Findings are collected in severity order
      Given a review.yaml with a must finding and a verify.yaml with a should and a may finding
      When the findings are read
      Then they arrive must, should, may, each named by the skill that recorded it
      When a state file holds a description that is not valid YAML
      Then its findings are still read
    ```

- [ ] **FR-20**

    ```gherkin
    @FR-20
    Scenario: Decisions land whole or not at all
      Given two decisions, one for a finding that exists and one that does not
      When the batch is recorded
      Then the API answers 404 and neither file changes
      When both findings exist
      Then each entry carries the decision and one shared decided_at, and the rest of each file is untouched
    ```

- [ ] **FR-21**

    ```gherkin
    @FR-21
    Scenario: The queue page filters and remembers
      Given the reviews page with a draft and an approved pull request
      When the drafts chip is set to only
      Then only drafts are listed and the choice survives leaving the page
      When the search box names one repository
      Then only that repository's rows are listed
    ```

- [ ] **FR-22**

    ```gherkin
    @FR-22
    Scenario: Share the findings with an agent
      Given a PR with an open must finding and no linked task
      When the Share modal opens
      Then the must finding is preselected and Import into a task is offered
      When a task is linked and Send to agent is pressed
      Then a run starts on the task with the prompt preview's content
      And unchecking a finding records skip on it in the state file
    ```

- [ ] **FR-23**

    ```gherkin
    @FR-23
    Scenario: The scan is configured from Settings
      Given the Review requests settings section
      When the cadence is saved as 30m and a repository is set to exclude
      Then the values persist and the scan status shows the last pass
      When Scan now is pressed
      Then a forced scan runs and its result is shown
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Lookups are cached and concurrent
      Given a queue of ten rows without cached metadata
      When the queue is read
      Then the ghx lookups run concurrently and are reused for the next five minutes
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: The queue survives a dead GitHub
      Given ghx unavailable and a store with reports
      When the queue is read
      Then the rows render from the store's snapshots and no error empties the list
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: Nothing is posted to GitHub
      Given any queue or findings action
      When it completes
      Then no write reached GitHub; the only writes are decisions into local state files
    ```

- [ ] **NFR-4**

    ```gherkin
    @NFR-4
    Scenario: First seen survives
      Given a scan row first seen two days ago
      When ten scans run without finding it removed
      Then its first_seen_at still reads two days ago
    ```

## Conflicts

None identified.

## Open Questions

1. Should the scan also recover dropped team review requests through the notifications API, the one part of the source script that was not ported?
2. Should the queue cache its parsed store rows across requests once stores grow past the size where re-parsing each report per request stays cheap?
