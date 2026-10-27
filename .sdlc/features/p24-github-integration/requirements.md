---
title: "GitHub read surface: issues, pull requests, My PRs"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: GitHub read surface: issues, pull requests, My PRs

## Overview

The app reads GitHub through the `ghx` CLI for listings, single objects, the viewer's own pull requests, and their individual checks, and keeps one `gh` GraphQL exception for the data `ghx` does not carry (a pull request item's reviewer list and the cycle-time reads).
This feature is the read surface on top of that access: a repository's issue and pull request panels, standalone issue and pull request pages, the task page's issue and PR modes, the My PRs page for the viewer's own open pull requests, and the reviewer reads and Slack pokes that chase a review.
The My PRs list is read-only over GitHub and stores nothing, so a pull request that merges leaves the page on the next refresh.
Importing GitHub issues and pull requests as source items is a separate feature (p2) and out of scope here.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | See a repository's issues and PRs, and which of their own pull requests need action, without opening GitHub tabs |
| Coding agent | Work an issue or PR through the task page's agent panel with the live object as context |
| Reviewers | Receive one clear Slack request per review they owe |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall fetch a single GitHub issue or pull request from its URL through `ghx`, returning number, title, url, state, draft and merge flags, review decision, head commit, creation time, author, labels, body, and the people it names. |
| FR-2 | Must | The system shall list a repository's issues through `ghx`, selecting the repository by registered repository id or by explicit owner and repo, with a state filter and a clamped limit. |
| FR-3 | Should | The system shall create an issue in a repository from a title and body through `gh`, returning the new issue's number, url, and state. |
| FR-4 | Must | The system shall list a repository's complete issue and pull request set through `ghx`, all states by default, each row tagged with its kind, running the two listings together, and reporting each kind that failed instead of reading as an empty section. |
| FR-5 | Must | The system shall re-fetch a repository through `ghx` before listing when `refresh` is set, and write the listing's state fields back onto the stored items the listing names, so an item never reads staler than the repository view. |
| FR-6 | Must | The system shall list the open pull requests authored by the configured GitHub login through `ghx`, one listing per registered GitHub repository read together, newest update first, each row carrying its repository, check rollup, review decision, approvers, review thread counts, whether anyone but the author reviewed it, the requested reviewers, and the tasks its stored item is associated with. |
| FR-7 | Must | The system shall report why the My PRs list is empty when no GitHub login is configured, no registered repository carries a GitHub remote, or `ghx` could not read any repository, rather than reading as no open work. |
| FR-8 | Should | The system shall refresh only those registered repositories whose ghx cache a completed `ghx cache` run has already warmed, using a pull-request-only delta (`ghx cache --repo --type prs`, never `--force`), at most once per repository every 300 seconds (900 after a failed refresh). A repository without a completed cache shall never be refreshed, because `ghx cache` would walk its whole history; its rows come from `ghx pr list` instead. The system shall cache the answer per login and repository set for 60 seconds (a failed lookup for 30) and bypass that cache on `refresh`. |
| FR-9 | Should | The system shall send a review-request DM to a pull request's named reviewers on Slack, resolving each GitHub login through the people directory, deduplicating logins, and reporting each reviewer's outcome separately. |
| FR-10 | Must | The system shall serve a standalone page per issue and per pull request (`/issue/owner/repo/number`, `/pr/owner/repo/number`) that renders the object read fresh from GitHub, falls back to the stored item, offers the agent panel, and adopts an existing linked task when there is one. |
| FR-11 | Must | The repository view shall list the repository's issues and pull requests as a grid with kind, number, title, state, author, linked tasks, changes, and links out to GitHub, ghx, and the app's own pages (the title opens the app's issue or PR page, and a Links column carries ghx and GitHub), with a refresh that forces `ghx` to re-fetch and a separate refresh of the linked items. |
| FR-12 | Should | The system shall list a pull request item's reviewers live from GitHub through `gh`, one row per reviewer with their latest decisive review state, last review time, and pending review requests, skipping team requests. |
| FR-13 | Should | The system shall poke one reviewer of a pull request item by Slack DM through the people directory, explaining what is missing when the login or a Slack id cannot be resolved. |
| FR-14 | Should | The system shall list one pull request's individual checks on demand, failing first, when its CI badge's popover opens, each carrying its name, state, description, and detail URL, and report why when the read could not run instead of reading as a pull request with no checks. |
| FR-15 | Should | The system shall link each My PRs row to the app's PR page, to the pull request on GitHub, and to the local ghx web UI when configured (the external links before the number), to each task the pull request's stored item is associated with, and shall link each GitHub repository in the repository list's own Links column to GitHub and to the ghx web UI when configured. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Reliability | A GitHub read failure shall surface as an explicit error (400 for bad coordinates, 502 when `ghx` or `gh` could not run), never as a silent empty list. |
| NFR-2 | Should | Performance | A My PRs reload shall answer from the short cache rather than re-query GitHub, and one lookup shall read at most 500 pull requests; the checks popover shall reuse a 30-second cache and list at most 100 checks per read. |
| NFR-3 | Should | Data integrity | The listing sync shall write only the state fields (state, is_draft, merged_at, created_at, author) and only when something changed; bodies and people stay with full fetches. |
| NFR-4 | Should | Maintainability | The My PRs page logic (labels, attention ranking, grouping, filters, search, counts) shall live in pure helpers tested without rendering the view. |
| NFR-5 | Should | Security | Issue and pull request bodies shall render through the shared sanitized Markdown renderer, and review-request DMs shall be sent without link previews. |

## Constraints

- GitHub access goes through `ghx` for listings and single objects; `gh` is used only where `ghx` does not reach (reviews, check rollups, review threads, issue creation).
- `ghx` and `gh` must be installed and authenticated on the host; there are no OAuth flows or webhooks.
- The My PRs read stores nothing; its task links are read from the stored GitHub items, and the only writes are the repository listing's state fields onto those items.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Fetch one issue by URL
      Given ghx can read the repository
      When the client asks GET /api/github/issue with a GitHub issue URL
      Then the response carries the issue's number, title, state, author, labels, and body

    @FR-1
    Scenario: A PR read carries the pull-request fields
      Given ghx returns a merged pull request payload
      When the client asks for that pull request's URL
      Then the response carries state MERGED, the merged_at time, the review decision, and the head commit
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: List issues for a registered repository
      Given a registered repository whose remote is github.com/o/r
      When the client asks GET /api/github/issues with repository_id
      Then the issues are listed through ghx for o/r

    @FR-2
    Scenario: Coordinates are required
      When the client asks GET /api/github/issues with neither repository_id nor owner and repo
      Then the response is 400
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Create an issue from a task
      Given a repository and a task title
      When the client posts POST /api/github/issues with the title and body
      Then `gh` creates the issue and the response carries its number and URL

    @FR-3
    Scenario: A blank title is rejected
      When the client posts POST /api/github/issues with a whitespace title
      Then the response is 400
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: List the whole repository
      Given ghx can list both kinds
      When the client asks GET /api/github/repository
      Then every issue and pull request is returned, each tagged with its kind, and the failed list is empty

    @FR-4
    Scenario: One kind failing stays visible
      Given the issue listing fails and the pull request listing succeeds
      When the client asks GET /api/github/repository
      Then the pull requests are returned and the failed list names "issues"
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Refresh forces a ghx re-fetch
      When the client asks GET /api/github/repository with refresh=true
      Then `ghx cache --force` runs before the listing

    @FR-5
    Scenario: The listing updates a stale stored item
      Given a stored item for an issue now closed on GitHub
      When the repository listing is read
      Then the item's state metadata reads CLOSED and the other repositories' items are untouched
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: One listing per repository answers the page
      Given a configured GitHub login and two registered GitHub repositories with open pull requests authored by that login
      When the client asks GET /api/my-pulls
      Then each row carries its repository, number, check rollup state, review decision, approvers, open thread count, reviewed flag, requested reviewers, and linked tasks
      And the rows are ordered newest update first across both repositories

    @FR-6
    Scenario: A repository that cannot be read does not hide the rest
      Given two registered GitHub repositories, one of which ghx cannot list
      When the client asks GET /api/my-pulls
      Then the rows of the readable repository return and the failed one is left out

    @FR-6
    Scenario: Only opinionated reviews approve
      Given a pull request whose latest opinionated reviews are one approval and one dismissal
      When the row is built
      Then only the approval's author is an approver
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: No login configured
      Given no GitHub login is configured
      When the client asks GET /api/my-pulls
      Then the response carries the "no login" message and no pull requests

    @FR-7
    Scenario: No repositories registered
      Given a login is configured and no registered repository carries a GitHub remote
      When the client asks GET /api/my-pulls
      Then the response carries the no-repositories message and no pull requests

    @FR-7
    Scenario: GitHub unreachable
      Given a login is configured but `ghx` cannot run
      When the client asks GET /api/my-pulls
      Then the response carries the unreachable message and no pull requests
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: A reload reuses the cache
      Given a My PRs read answered within the last 60 seconds
      When the client asks again without refresh
      Then GitHub is not queried and the same answer returns

    @FR-8
    Scenario: Refresh bypasses the cache
      When the client asks GET /api/my-pulls?refresh=true
      Then ghx refreshes each repository's cache and the rows are read again

    @FR-8
    Scenario: A read refreshes with the delta, not a full re-fetch
      Given a registered repository whose cache a `ghx cache` run has completed
      When the client asks GET /api/my-pulls
      Then the repository is refreshed with `ghx cache --repo owner/name --type prs` without `--force`

    @FR-8
    Scenario: A repository with no completed cache is never refreshed
      Given a registered repository that no `ghx cache` run has warmed
      When the client asks GET /api/my-pulls
      Then no cache refresh runs for that repository and its rows come from `ghx pr list`

    @FR-8
    Scenario: A reload does not refresh a repository again within the window
      Given a repository refreshed by a My PRs read 10 seconds ago
      When the client asks GET /api/my-pulls?refresh=true
      Then the repository is not refreshed again

    @FR-8
    Scenario: Registering a repository bypasses the previous list
      Given a cached My PRs answer for one repository
      When a second repository is registered and the client asks again
      Then both repositories are read instead of answering from the cached list
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: DM each requested reviewer once
      Given two reviewer logins, one repeated in different case, and one with no person behind it
      When the client posts POST /api/my-pulls/poke with those logins
      Then one DM is sent to the resolvable reviewer and the other is reported with the reason

    @FR-9
    Scenario: No logins given
      When the client posts POST /api/my-pulls/poke with an empty login list
      Then the response is 400
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: A standalone issue page reads GitHub
      Given the route /issue/o/r/9
      When the page loads
      Then the issue's title, state, author, labels, and body are shown from the live read, with an agent panel beside it

    @FR-10
    Scenario: Fall back to the stored item
      Given GitHub cannot be read for the issue
      When the page loads
      Then the stored item's fields are shown and the page says it is showing the stored copy
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: The repository grid lists every issue and PR
      Given a registered repository with issues and pull requests on GitHub
      When the repository view loads
      Then the grid shows one row per issue and PR with kind, number, title, state, author, and linked tasks
      And the title opens the row in the app's issue or PR page
      And the Links column carries ghx and GitHub links

    @FR-11
    Scenario: Refresh all re-fetches the repository
      When the user clicks the repository's refresh all button
      Then the listing is re-read with refresh and the stored items are reloaded
    ```

- [ ] **FR-12**

    ```gherkin
    @FR-12
    Scenario: Each reviewer appears once
      Given a pull request item whose reviews include repeats and a later comment
      When the client asks GET /api/items/{id}/reviewers
      Then each reviewer appears once with their latest decisive state and last review time, and a still-requested reviewer is marked PENDING

    @FR-12
    Scenario: Team requests are skipped
      Given a review request naming a team
      When the reviewers are read
      Then the team produces no reviewer row
    ```

- [ ] **FR-13**

    ```gherkin
    @FR-13
    Scenario: Poke a reviewer through their person record
      Given a person carrying the reviewer's GitHub login as an alias and a Slack id
      When the client posts POST /api/items/{id}/poke with that login
      Then the review-request DM is sent without a preview and the poke is reported

    @FR-13
    Scenario: Explain what is missing
      Given no person carries the login, or the person has no Slack alias
      When the poke is attempted
      Then the response is 400 and names exactly what to add
    ```

- [ ] **FR-14**

    ```gherkin
    @FR-14
    Scenario: Open a pull request's checks
      Given a pull request whose head commit has failing, running, and passing checks
      When the client asks GET /api/my-pulls/checks for its repository and number
      Then the checks are returned failing first, each with its name, state, description, and detail URL
      And the response's total is the number of checks on the commit, even beyond the first hundred listed

    @FR-14
    Scenario: A failed checks read
      Given `gh` cannot read the pull request
      When the client asks GET /api/my-pulls/checks
      Then the response carries the checks error and no checks
    ```

- [ ] **FR-15**

    ```gherkin
    @FR-15
    Scenario: A My PRs row's links
      Given a pull request with a GitHub URL and a configured ghx URL
      Then ghx opens the pull request's page in the ghx web UI
      And gh opens the pull request on GitHub
      And both external links come before the number, which opens /pr/{owner}/{repo}/{number} in the app

    @FR-15
    Scenario: A My PRs row's task link
      Given a pull request whose stored item is associated with a task
      Then the row links the task after its title
      And a pull request the app does not store shows no task link

    @FR-15
    Scenario: The repository list's links
      Given a registered repository with a GitHub remote and a configured ghx URL
      Then its Links cell offers ghx and gh links
      And a repository whose remote is not GitHub offers neither
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: ghx missing reads as a gateway error
      Given ghx is not installed or not authenticated
      When a GitHub listing or fetch endpoint is called
      Then the response is 502 with a detail that names `ghx`
      And no endpoint returns an empty list as if the repository had no issues
    ```

## Conflicts

None identified.

## Open Questions

None.
