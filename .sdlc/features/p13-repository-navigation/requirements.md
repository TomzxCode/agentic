---
title: "Repository navigation"
status: draft
revision: 1
session_link: "http://localhost:10000/?session=ses_ed1823a65ffe7LJmF4SEXBZr08"
---

# Requirements: Repository navigation

## Overview

The app organizes work as tasks, associates GitHub issues and PRs to those tasks as source items, and works against local git checkouts registered as repositories.
Today the repository list lives under Settings, and the only place a repository's issues are grouped is the task-creation import picker, which lists live open issues rather than the ones already tied to tasks.
There is no way to open a repository, see the issues and PRs that are already associated with tasks, and move from there to the task that uses them.
This feature adds a top-level Repositories page and a per-repository detail view that group the GitHub issues and PRs already associated with tasks by the repository they belong to, and link each one to its tasks and to GitHub.
It turns the repository list from a settings concern into a navigation surface that connects repositories, their issues and PRs, and the tasks that use them.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Open a repository, see the issues and PRs tied to tasks, and jump straight to the task |
| Coding agent | A grouped view of a repository's issues and PRs is not consumed by the agent, which reads associations from the task (no interest beyond not breaking the item model) |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The app shall provide a top-level Repositories page at `/repositories` that lists every registered repository with its name, path, remote URL, and default branch, and the count of associated issues and PRs it has. |
| FR-2 | Must | The Repositories page shall be where repositories are added (single path and bulk via the directory picker) and removed; the Settings repositories management section shall be removed with no replacement link, while repository groups shall stay under Settings. |
| FR-3 | Must | Opening a repository shall show a detail view at `/repositories/:id` listing that repository's GitHub issues and PRs that are associated with at least one task. |
| FR-4 | Must | Each item row shall show its kind (issue or PR), its title, a link to open it on GitHub, and the tasks it is associated with, and selecting a task shall open that task's detail view; the row shall also show the issue or PR number when one can be derived from the item's URL or external id. |
| FR-5 | Must | A GitHub issue or PR item shall be grouped under the repository whose GitHub owner and repo match the item's URL, and an item of another kind (for example a GitHub commit or a plain URL) or one whose URL matches no registered repository shall not appear on the Repositories page or on any repository detail view. |
| FR-6 | Must | The Repositories page and the repository detail view shall render an empty state when there are no repositories or no associated items respectively, and an error state with a retry action when the load fails. |
| FR-7 | Should | The repository detail view shall list its items in separate Issues and Pull requests sections, each with a heading and count, and shall filter them by a text query over title and number. |
| FR-8 | Should | On a task's detail view, each of the task's repositories shall link to that repository's detail page. |
| FR-9 | Should | The Repositories page shall show totals across all repositories: the number of repositories, plus the number of associated issues and associated PRs, counted as the sum of the per-repository (grouped) counts and excluding items with no matching repository. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Data integrity | The views shall be derived from the existing Repository, SourceItem, and Association records, adding no table and no column, so existing databases keep working. |
| NFR-2 | Must | Reliability | Rendering the page shall rely on stored item metadata, so no GitHub call is required to render it and a failed item refresh shall not blank the view. |
| NFR-3 | Should | Performance | The Repositories page and a repository detail view shall render from loaded data in under 300 ms locally with 50 repositories and 500 associated items. |
| NFR-4 | Should | Usability | The views shall stay usable and legible at phone widths, per the project's mobile-first design, with no horizontal scrolling. |
| NFR-5 | Should | Accessibility | Icon-only controls shall carry `aria-label`s, item kind shall be shown as text (not color alone), and every row and link shall be reachable and activatable from the keyboard. |

## Constraints

- Reuses the existing `/api/repositories` and `/api/items` endpoints (the items list already carries each item's `task_ids`); repository matching derives owner and repo from the item URL and the repository remote URL, with no live GitHub call.
- The SPA cannot call the backend's `parse_github` / `github_owner_repo` helpers, so it parses the URL and remote itself and normalizes both remote forms (`https://github.com/o/r` and `git@github.com:o/r.git`); deriving the match server-side instead is left to the specification.
- No new persistence is required: `SourceItem` stores title, kind, URL, and external id, but not open/closed state, so the views show stored fields and link out to GitHub.
- At the target scale (tens of repositories, hundreds of items) the client computes the grouping from the items list; if that puts the 300 ms target at risk, a server-side count or a repository id on the item read is a specification decision.
- The SPA route list in FEAT-p7 FR-1 is extended with `/repositories` and `/repositories/:id`; the Settings repositories management UI is removed by FR-2, while the repository CRUD API in FEAT-p3 FR-3 is unchanged (FEAT-p3 FR-3 names no SPA placement).
- The app is designed with mobile in mind, so the views are checked at phone widths as well as on a desktop.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: List repositories with their item counts
      Given a repository whose remote is github.com/acme/api
      And an issue and a PR associated to tasks whose URLs point at github.com/acme/api
      When the user opens the Repositories page
      Then the repository is listed with its name, path, remote, and default branch
      And it shows 1 issue and 1 PR

    @FR-1
    Scenario: A repository with no associated items shows zero counts
      Given a registered repository with no associated GitHub items
      When the user opens the Repositories page
      Then the repository is listed with 0 issues and 0 PRs

    @FR-1
    Scenario: Reach the page from the app's navigation
      Given the app is open on another view
      When the user selects the Repositories entry in the navigation
      Then the Repositories page opens
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Add a repository from the Repositories page
      Given a directory containing .git
      When the user adds it as a repository from the Repositories page
      Then a repository is created and listed on the page
      And the Settings page no longer offers repository add or remove

    @FR-2
    Scenario: Remove a repository from the Repositories page
      Given a listed repository
      When the user removes it
      Then the repository is no longer listed
      And no files on disk are deleted
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: A repository shows only items tied to tasks
      Given a repository with one issue associated to a task and one issue associated to no task
      When the user opens the repository's detail view
      Then the associated issue is shown
      And the unassociated issue is not shown

    @FR-3
    Scenario: Issues and PRs are both listed
      Given a repository with an associated issue and an associated PR
      When the user opens the repository's detail view
      Then both the issue and the PR are shown
      And each is labelled as an issue or a PR
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: An item links to GitHub and to its tasks
      Given a repository detail view showing an issue associated to two tasks
      When the user inspects the issue's row
      Then the row shows the issue number (derived from its URL or external id), its title, and a link to GitHub
      And the row lists both tasks

    @FR-4
    Scenario: A row without a derivable number
      Given a repository detail view showing a GitHub issue or PR item stored without a parseable number
      When the user inspects the item's row
      Then the number is omitted
      And the kind, title, GitHub link, and tasks still render

    @FR-4
    Scenario: Selecting a task opens it
      Given a repository detail view showing an item associated to a task
      When the user selects that task in the row
      Then the task's detail view opens
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: An item groups under its matching repository
      Given a repository whose remote is github.com/acme/api
      And a GitHub issue item whose URL is github.com/acme/api/issues/42
      When the repository's detail view is shown
      Then the item appears under that repository

    @FR-5
    Scenario: An item with no matching repository is excluded
      Given no registered repository has the remote github.com/acme/other
      And a GitHub issue item whose URL is github.com/acme/other/issues/7 is associated to a task
      When the Repositories page and its detail views are shown
      Then the item appears on none of them
      And the item is still shown on the Items page

    @FR-5
    Scenario: A non-issue GitHub item is excluded
      Given a repository whose remote is github.com/acme/api
      And a GitHub commit item whose URL points at github.com/acme/api is associated to a task
      When the repository's detail view is shown
      Then the commit item is not shown
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: No repositories registered
      Given no repositories are registered
      When the user opens the Repositories page
      Then a message explains that no repositories are registered
      And it offers a way to add one

    @FR-6
    Scenario: A repository with nothing associated
      Given a repository with no associated issues or PRs
      When the user opens its detail view
      Then a message explains that no issues or PRs are associated to tasks yet

    @FR-6
    Scenario: A failed load offers a retry
      Given the repositories or items fail to load
      When the user opens the Repositories page
      Then an error state with a retry action is shown
      When the user triggers the retry and the load succeeds
      Then the page is shown

    @FR-6
    Scenario: An unknown repository id
      Given no repository has the id "does-not-exist"
      When the user opens /repositories/does-not-exist
      Then a not-found state is shown
      And it offers a link back to the Repositories page
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Issues and PRs are separated
      Given a repository detail view with an associated issue and an associated PR
      When the view is shown
      Then the issue is listed under an "Issues" heading with its count
      And the PR is listed under a "Pull requests" heading with its count

    @FR-7
    Scenario: Filter by a query
      Given a repository detail view with issues #12 "Fix login" and #40 "Update docs"
      When the user filters by "login"
      Then only #12 is shown
      When the user filters by "40"
      Then only #40 is shown
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: Reach a repository from a task
      Given a task that references a repository
      When the user opens the task's detail view
      Then the repository links to that repository's detail page
      And selecting it opens the repository detail view
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: Totals across repositories
      Given two repositories with one associated issue and one associated PR in total
      When the user opens the Repositories page
      Then the page shows 2 repositories, 1 associated issue, and 1 associated PR
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: No new persistence
      Given an existing database
      When the Repositories page and a repository detail view are shown
      Then the views are derived from the existing repository, source item, and association records
      And no new table or column is created
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: Renders without GitHub
      Given GitHub is unreachable (ghx is missing)
      When the user opens the Repositories page and a repository detail view
      Then both render from stored item metadata
      And no error blocks the view

    @NFR-2
    Scenario: A failed item refresh does not blank the view
      Given a repository detail view is shown
      When refreshing one item fails
      Then the item keeps its stored data
      And the rest of the view stays rendered
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: The page stays fast at scale
      Given 50 repositories and 500 associated items
      And the app is served from its production build against a warm local API on a developer machine
      When the user opens the Repositories page and a repository detail view
      Then each view is interactive in under 300 ms from the click
      And the measurement excludes the initial API fetch
    ```

- [ ] **NFR-4**

    ```gherkin
    @NFR-4
    Scenario: The views fit a phone
      Given a viewport 375 px wide and the default text size
      When the Repositories page and a repository detail view are shown
      Then each repository row shows its name untruncated
      And each item row shows its kind and number untruncated
      And no horizontal scrolling is needed to read a row
    ```

- [ ] **NFR-5**

    ```gherkin
    @NFR-5
    Scenario: Controls are labelled and reachable
      Given the Repositories page
      When the page is inspected
      Then every icon-only control has an `aria-label`
      And the item kind is shown as text, not color alone
      And the repository rows and item links can be reached and activated with the keyboard
    ```

## Conflicts

None identified yet.
This feature refines two existing concerns rather than contradicting them:
FEAT-p7 FR-1 (the SPA route list) gains `/repositories` and `/repositories/:id`, and the FEAT-p3 FR-3 repository CRUD API is unchanged (FEAT-p3 FR-3 names no SPA placement; the Settings surface it currently drives is code, and FR-2 moves that management to the new page).

## Open Questions

1. Should the repository detail view let the user import a new task from an issue or PR that is not yet associated (reusing the task-creation import), or is navigation of already-associated items enough for this feature?

Resolved during review: the live open/closed state question is settled by NFR-2 (the views render from stored data), repositories with no GitHub remote appear as zero-count rows per FR-1, and the Settings repositories management section is removed per FR-2.
