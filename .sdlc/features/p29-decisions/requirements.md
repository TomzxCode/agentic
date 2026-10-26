---
title: "Colleague decisions page"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: Colleague decisions page

## Overview

Keeping up with a team means knowing what was decided, not reading every Slack thread.
The `extract-colleague-decisions` skill already turns a day of Slack into one Markdown report per day under the user's notes tree.
This feature aggregates those reports so the user can answer "what did Ana decide last week", "what did we defer", and "who opposed that" without opening the files.
The store reads the reports, parses each person's decisions with their supporters and opponents, and deduplicates repeats.
The SPA renders the decisions at `/decisions`, grouped by author, supporter, or opponent, with a support and opposition matrix over the same rows and filters for search, dates, and decision buckets.
The page is read-only; the reports belong to the skill that writes them.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | See what colleagues decided, who backed or opposed it, and filter to a person, day range, or bucket |
| Coding agent | Read `GET /api/decisions` for the same aggregation, or the Markdown files directly |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall discover decision reports at `{notes_dir}/decisions/YYYY/MM/DD.md` and as any `*.colleague-decisions.md` file under the notes root, skipping dotfiles and returning them oldest first. |
| FR-2 | Must | The system shall parse each report into decisions with author, bucket (Decided, Deferred, Open, or Committed), text, Slack permalink (from a Markdown link or a bare URL), supported-by and opposed-by names, plus the report's day, per-person headlines, the not-heard list, and cross-cutting notes. |
| FR-3 | Must | The system shall drop the author from their own support and opposition lists, split names on commas, semicolons, slashes, and "and", and strip an author's own name from being counted twice. |
| FR-4 | Must | The system shall aggregate the reports into counts of decisions, people, supporters, and opponents, the covered date range, and one deduplicated decision list sorted newest first, where a decision repeated across reports is kept once. |
| FR-5 | Must | `GET /api/decisions` shall return the aggregated payload with the notes root path and generation time, and shall return an empty payload with `root` null instead of an error when the notes directory is missing or not configured. |
| FR-6 | Must | The Decisions page shall list decisions grouped by author, supporter, or opponent, lead each group with the busiest person, show the per-person headline and the not-heard and cross-cutting footers, and navigate from a person list to the matching group. |
| FR-7 | Should | The page shall filter decisions by search text, a date range (a backwards range is swapped, presets cover the last 7, 30, and 90 days ending at the latest report day), and status bucket chips whose counts ignore the bucket filter. |
| FR-8 | Should | The page shall show a matrix of authors against supporters or opponents with per-cell counts and percentages, a received total, and clickable cells listing their decisions, and shall remember the chosen tab on the device. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Data integrity | The feature shall be read-only: it never writes to, moves, or deletes anything under the notes root. |
| NFR-2 | Should | Maintainability | The parser and aggregation shall be pure functions over paths and text, importing no FastAPI, so a router maps their result to a response. |
| NFR-3 | Should | Robustness | A report file that cannot be read shall be skipped rather than failing the page, and an unparseable day falls back to the file name. |

## Constraints

- The report format is owned by the `extract-colleague-decisions` skill; this feature mirrors `scripts/colleague_decisions_page.py` in the agents repository so the page and the script never disagree about what a report says.
- The notes root is `AGENTIC_NOTES_DIR` (or `NOTES_DIR`), defaulting to `~/notes`.
- People on the page are plain names from the reports, not records in the People directory.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Both report layouts are discovered, oldest first
      Given reports written for 2026-10-03, 2026-10-02, 2026-10-01, and an ad-hoc 2026-10-04.colleague-decisions.md
      When the reports are discovered
      Then the days come back as 2026-10-01, 2026-10-02, 2026-10-03, 2026-10-04
      And a dotfile such as .tmp.md is skipped
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Every section of a report is parsed
      Given a report with a headline, four buckets, supporters, opponents, permalinks, a not-heard list, and a cross-cutting note
      When the report is parsed
      Then each decision carries its author, bucket, cleaned text, permalink, supporters, and opponents
      And the headline, not-heard names, and cross-cutting note are returned
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: The author is dropped from their own support list
      Given a decision with "Supported by: Alice Smith, Bob Jones" in Alice's section
      When the report is parsed
      Then supported_by is ["Bob Jones"] only
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Repeated decisions are kept once
      Given the same decisions in a dated report and an ad-hoc report for the same day
      When the payload is built
      Then counts report 4 decisions, 2 people, 2 supporters, and 1 opponent
      And the decision list is newest first with bucket order reversed within a day
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: The endpoint aggregates the configured notes tree
      Given a notes directory holding one report
      When GET /api/decisions is called
      Then the response names the root, carries generated_at, reports 1, and the parsed decisions

    @FR-5
    Scenario: A missing notes directory is not an error
      Given a notes root that does not exist
      When GET /api/decisions is called
      Then the response has root null, no reports, no decisions, and no range
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: The page groups by author and closes with the shared sections
      Given a payload with decisions, a headline, a not-heard name, and a cross-cutting note
      When the Decisions page renders
      Then each author is a group with their decision cards
      And the headline, not-heard name, and cross-cutting note are shown
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: The search box and status chips narrow the list
      Given three decisions by two people
      When the user searches for a word from one decision
      Then only that decision card remains
      And selecting the Committed chip leaves one card
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: The matrix shows the support pattern and its decisions
      Given decisions where Bob supported one of Alice's two decisions
      When the Matrix tab is opened and Alice's diagonal cell is clicked
      Then the detail lists both of Alice's decisions
      And a remembered tab choice is restored on the next visit while an unknown one falls back to By author
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: The page never writes
      Given the Decisions page in use with any filters
      When requests are made
      Then every call is a read of GET /api/decisions and no notes file changes
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: An unreadable report does not fail the page
      Given one report that raises an OS error when read
      When the reports are discovered
      Then the other reports are returned and the page still renders
    ```

## Conflicts

None identified yet.

## Open Questions

None.
