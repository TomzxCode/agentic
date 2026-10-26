---
title: "Repository navigation"
status: done
revision: 1
---

# Test Plan: Repository navigation

## Scope

Covers the pure grouping and parsing helpers, the two grid components, the column chooser and the shared value filter, and the two views' states (loading, empty, not found, error, loaded).
Out of scope: the live ghx listing itself (stubbed in the view tests) and real AG Grid popup positioning, which jsdom cannot do (filtering is driven through the grid api).

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | `parseRemote` normalizes https, ssh, and `ssh://` remotes to owner/repo | each remote form, with `.git` and trailing slash | lowercased owner/repo; null for a non-GitHub remote |
| TC-2 | `remoteLabel` keeps the remote's own casing for display | `git@github.com:TomzxCode/agentic.git` | `TomzxCode/agentic`; null for GitLab or empty |
| TC-3 | `parseGithubUrl` reads owner, repo, kind, and number from issue and PR URLs | issue and PR URLs | the parsed parts; null for other paths |
| TC-4 | `itemKind`, `itemNumber`, `itemState`, `itemStatus`, `itemAuthor` derive row fields | stored item with URL, metadata, author | kind from the URL path first, number from the URL or external id, state and author from metadata |
| TC-5 | `groupItemsByRepository` groups task-associated GitHub items under the matching repository | repositories and items, including non-matching and unassociated ones | one summary per repository with issue and PR counts; unmatched items excluded |
| TC-6 | `itemsForRepository` returns one repository's associated items | a repository and the item list | only its items |
| TC-7 | `repositoryRows` overlays the live ghx listing with the stored, linked items | ghx items plus stored items | one row per issue or PR, linked rows carrying their task ids |
| TC-8 | `sortItems`, `sortRepositories`, `filterRepositories`, `repositoryRows` order and narrow rows | unsorted mixed rows | deterministic order |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-9 | The repositories page lists summaries and reports totals and the shown count | mocked repositories, items, settings | rows in the grid; the header totals line; the `count` event updates "X of Y" |
| TC-10 | Add a repository by path and remove one | mocked create and remove | the grid reloads; removal asks for confirmation |
| TC-11 | The repositories page renders loading, empty, and error states | pending, empty, and failing loads | spinner, empty message, error panel with Retry |
| TC-12 | The detail view renders not found and empty states | unknown id; repository with no rows | not-found message with a back link; empty message |
| TC-13 | The detail view overlays the ghx listing and reports a failed or partial listing | stubbed `api.github.repository` | stored items still render on a ghx failure; `failed` kinds get a note |
| TC-14 | New task from an unassociated row and record-change from a merged PR | stubbed `api.tasks.create`, `api.changes.create`, `api.items.refresh` | the actions emit to the view; the store reloads; a busy row shows its spinner |

## End-to-End Tests

| ID | Description | Steps | Expected Outcome |
|---|---|---|---|
| TC-15 | The items grid renders and behaves | mount `RepositoryItemsGrid` with enriched rows | kind and state badges, title link, number, author link (person or prefilled creation page), task chips, statuses; header click sorts; the value filter narrows rows after `settleGrid` |
| TC-16 | The column chooser hides and shows a column | mount `GridColumnChooser` with a grid api | unchecked columns hide; the choice persists in `localStorage` under `agentic.gridColumns.<key>` |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-17 | A remote that is not GitHub, or missing | the repository lists zero counts |
| TC-18 | An item with no derivable number | the row omits it; the rest renders |
| TC-19 | A row's tasks reference a deleted task | unknown ids are dropped from the chips |
| TC-20 | A filter click in jsdom | never done: tests drive `setFilterModel` through the api instead, because AG Grid's popup positioning throws in jsdom |

## Test Infrastructure

- Vitest under jsdom with `pool: 'vmThreads'`; shared stubs in `src/test-setup.js`.
- `RouterLink` is stubbed by name and handed to the grids through the `context` prop.
- Grid assertions that narrow rows wait on the `settleGrid()` helper in `views2.test.js`.

## Test Files

| File | Covers |
|---|---|
| `frontend/src/__tests__/repositoriesParse.test.js` | TC-1 to TC-4 |
| `frontend/src/__tests__/repositoriesRows.test.js` | TC-5 to TC-8 |
| `frontend/src/__tests__/repositoriesView.test.js` | TC-9 to TC-11 |
| `frontend/src/__tests__/repositoryDetailView.test.js` | TC-12 to TC-14, TC-18, TC-19 |
| `frontend/src/__tests__/RepositoryItemsGrid.test.js` | TC-15 |
| `frontend/src/__tests__/gridColumnChooser.test.js` | TC-16 |
| `frontend/src/__tests__/ValuesFilter.test.js` | the shared value filter's model and matching |
| `frontend/src/__tests__/views2.test.js` | the `settleGrid` helper the grid tests share |

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-9 |
| FR-2 | TC-10 |
| FR-3 | TC-5, TC-7, TC-13 (drift: the view now also lists unassociated items from the live listing) |
| FR-4 | TC-15, TC-18, TC-19 |
| FR-5 | TC-5 |
| FR-6 | TC-11, TC-12 |
| FR-7 | TC-15 (drift: one grid with a Kind column and per-column filters, not sections) |
| FR-8 | TC-15 (task chips and links) |
| FR-9 | TC-9 |
| NFR-1 | TC-5 (no new persistence) |
| NFR-2 | TC-13 (stored items render without GitHub) |
| NFR-4 | Not automated (manual phone-width check) |
| NFR-5 | TC-15, TC-16 (labels and keyboard-reachable controls) |
