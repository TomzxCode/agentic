---
title: "Task dependencies and the dependency graph"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: Task dependencies and the dependency graph

## Overview

Tasks can be linked with directed before/after edges: an edge `before -> after` means the `before` task must be done before the `after` task.
The links are kept acyclic, because a link that would close a cycle is refused, so the whole set always forms a DAG.
The task page edits a task's links inline with before and after chip selectors, and the Graph page draws the whole graph, laying each task in a column by how far it sits along its dependency chain, so a blocked chain is visible as a pattern rather than a list.
The CLI can read the graph and link or unlink tasks for agents.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | See prerequisites and follow-ups together, and record an order without deadlines |
| Coding agent | Read the whole graph as nodes and edges to reason about ordering through the CLI |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall link two tasks with a directed before/after edge, where relation "before" means the related task must be done first and "after" means it follows this one, and the link shall read symmetrically from both tasks. |
| FR-2 | Must | The system shall refuse a link between a task and itself, and refuse any link that would close a cycle, leaving the stored edges unchanged. |
| FR-3 | Must | The system shall treat a repeated link as a no-op and store at most one edge per task pair. |
| FR-4 | Must | The system shall report a task's before and after neighbours resolved to full task reads, oldest link first. |
| FR-5 | Must | The system shall remove the edge between two tasks from either side of the pair, and report 404 when no edge exists. |
| FR-6 | Should | The system shall record a `dependency_added` or `dependency_removed` timeline entry on both tasks and publish a `dependencies_changed` event to both tasks' event channels. |
| FR-7 | Should | The system shall drop a task's edges when the task is deleted, leaving the other task without dangling links. |
| FR-8 | Must | The system shall return the whole dependency graph as task nodes (oldest first) plus the edges between them, hiding done and archived tasks and their edges unless `include_done` is set. |
| FR-9 | Should | The task page shall edit the links inline with before and after chip selectors that offer every task except the task itself and the tasks already linked either way. |
| FR-10 | Should | The Graph page shall draw the DAG with a layered layout (longest path from a source), support left-to-right and top-to-bottom directions remembered per device, open a task on node click, link two tasks by dragging between handles, and remove a link by clicking its edge. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Correctness | Acyclicity shall be enforced at write time with a forward reachability walk, so every read sees a DAG without repair passes. |
| NFR-2 | Should | Maintainability | The graph layout shall be a pure function over nodes and edges, testable without rendering. |
| NFR-3 | Should | Performance | The edge table shall index both endpoints and enforce a unique (before_id, after_id) pair, so neighbour, duplicate, and cycle queries stay bounded. |
| NFR-4 | Should | Usability | A filtered graph shall drop edges whose endpoints are hidden rather than drawing dangling arrows. |

## Constraints

- An edge is an ordering statement only; completing or deleting a task never changes another task's status.
- Dependencies live in their own table, not on the task row, so they survive task edits and disappear with task deletion.
- The edge endpoints are foreign keys to `task.id`; SQLite enforces them, so a link between unknown tasks is impossible.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Link with relation after
      Given tasks A and B
      When A links B with relation "after"
      Then A's dependencies list B under "after"
      And B's dependencies list A under "before"

    @FR-1
    Scenario: Link with relation before
      Given tasks A and B
      When B links A with relation "before"
      Then B's dependencies list A under "before"
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: A self link is refused
      Given task A
      When A links itself
      Then the response is 400 and no edge is stored

    @FR-2
    Scenario: A cycle is refused
      Given edges A -> B and B -> C
      When C links A
      Then the response is 400 with a cycle message
      And the A -> B edge still holds and nothing new was written
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: A duplicate link is idempotent
      Given an edge A -> B
      When the same link is posted again
      Then A still lists exactly one edge to B
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Read a task's neighbours
      Given edges A -> B and B -> C
      When B's dependencies are read
      Then the before list carries A and the after list carries C, both as full task reads
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Unlink from either side
      Given an edge A -> B
      When B unlinks A
      Then the edge is gone from both tasks

    @FR-5
    Scenario: Unlink a missing edge
      When A unlinks a task it is not linked to
      Then the response is 404
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Linking records on both tasks
      Given two unlinked tasks
      When they are linked
      Then each task's timeline carries a dependency_added entry naming the other

    @FR-6
    Scenario: Unlinking records on both tasks
      Given an edge between two tasks
      When it is removed
      Then each task's timeline carries a dependency_removed entry
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Deleting a task drops its links
      Given an edge A -> B
      When A is deleted
      Then B survives and lists no before link
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: The graph returns nodes and edges
      Given an edge A -> B
      When GET /api/graph is read
      Then the nodes carry A and B and the edges carry the pair

    @FR-8
    Scenario: Done tasks are hidden with their edges
      Given an edge A -> B and B is done
      When the graph is read without include_done
      Then B is absent and no edge names B
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: The selectors exclude impossible candidates
      Given task B linked before task A
      When A's dependency selector is opened
      Then the candidates exclude A itself and B
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: The graph draws the DAG
      Given a chain A -> B -> C
      When the Graph page loads
      Then each task is a node in successive columns with an arrow from each task to the one that follows

    @FR-10
    Scenario: Link and unlink from the drawing
      Given two unlinked nodes on the Graph page
      When the user drags from one node's handle to the other, then clicks the new edge
      Then the link is created and then removed through the dependency endpoints
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: A cycle can never be stored
      Given any set of stored edges
      When links are added one at a time
      Then every refused link is one that would close a cycle
      And no stored set of edges ever contains a cycle
    ```

## Conflicts

None identified.

## Open Questions

None.
