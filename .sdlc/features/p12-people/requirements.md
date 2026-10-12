---
title: "People: associate tasks and items with specific individuals"
status: draft
session_link: "http://localhost:10000/?session=ses_ed1c7d2feffevews1ZEr34mSZC"
---

# Requirements: People: associate tasks and items with specific individuals

## Overview

Work is not only tasks and artifacts: it also belongs to people.
Today a task records what it is about (tags) and what feeds it (items), but nothing records who it involves.
This feature adds a first-class **person** and links people to tasks and to items, so a task shows who is involved and an item (a Slack thread, a GitHub issue) shows the people behind it.
A person carries a name and optional email, handle, and notes; the links are many-to-many on both sides.
The people list is the directory the task page, the items list, and the CLI draw on.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Record who a task or an item involves, and find everything a person is attached to |
| Coding agent | Read and set a task's or an item's people through the API or CLI |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall record a person with a name, an optional email, an optional handle, and optional notes. |
| FR-2 | Must | The system shall associate a person with a task (many-to-many), and remove that association. |
| FR-3 | Must | The system shall associate a person with a source item (many-to-many), and remove that association. |
| FR-4 | Must | The system shall list people, each with the number of tasks and items they are associated with. |
| FR-5 | Must | The system shall expose people and their associations over HTTP and through the CLI. |
| FR-6 | Must | The web app shall let the user add and remove people on a task and show the task's people. |
| FR-7 | Must | The web app shall show each item's people on the Items page and let the user link a person to an item. |
| FR-8 | Must | The web app shall provide a People page listing people with the tasks and items each is attached to. |
| FR-9 | Should | Associating or removing a person on a task shall be recorded as a timeline event. |
| FR-10 | Should | Deleting a person shall remove their associations; deleting a task or an item shall remove its person links. |
| FR-11 | Must | The system shall auto-populate people from a GitHub item's metadata when it is fetched: the issue or PR author, its assignees, and its comment authors, each keyed by login. |
| FR-12 | Must | The system shall auto-populate people from a Slack item's metadata when it is fetched: the distinct participants of the cached thread, each keyed by Slack user id. |
| FR-13 | Must | The system shall link the people auto-populated on an item to a task when that item is linked to the task. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Data integrity | People shall be stored in their own `person` table, and the links in `taskperson` and `itemperson` join tables with unique constraints, so the same person cannot be linked twice. |
| NFR-2 | Should | Consistency | The association semantics (exact person id, idempotent link) shall be identical across the API, the CLI, and the web UI. |
| NFR-3 | Should | Usability | The People page and the people controls shall stay usable and legible at phone widths, per the project's mobile-first design. |
| NFR-4 | Should | Reliability | Linking a person already linked to a task or an item shall be a no-op, not an error or a duplicate row. |
| NFR-5 | Should | Performance | Listing a few hundred people with their counts shall respond in under 200 ms on a local machine. |
| NFR-6 | Should | Reliability | Auto-population shall be best effort: when `ghx` or `slackx` is missing, fails, or returns no people, the fetch still succeeds and no person is created. |
| NFR-7 | Should | Data integrity | Auto-populated people shall be de-duplicated by handle (a GitHub login or a Slack user id), so the same person is one directory entry across items. |

## Constraints

- Persistence is SQLite via SQLModel; new tables are created by `create_all`, and new columns (none expected) are added in `db._ensure_columns()`.
- No authentication; the app assumes a trusted, single-user environment.
- A person's name is required and is not unique: two people may share a name.
- The web app is designed with mobile in mind, so the People page and people controls are checked at phone widths.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Record a person
      Given no people exist
      When a person is created with the name "Ada Lovelace"
      Then the person is listed with that name and no associations

    @FR-1
    Scenario: A name is required
      Given no people exist
      When a person is created with an empty name
      Then the request is rejected as invalid input
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Associate and unassociate a person on a task
      Given a task and a person
      When the person is associated with the task
      Then the task's people include the person
      When the person is unassociated from the task
      Then the task's people are empty

    @FR-2
    Scenario: A person spans several tasks
      Given two tasks and one person
      When the person is associated with both tasks
      Then the person is listed with a task count of two
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Associate a person with an item
      Given an item and a person
      When the person is associated with the item
      Then the item's people include the person

    @FR-3
    Scenario: A person spans several items and tasks
      Given two items and one task linked to one person
      When the person is associated with both items
      Then the person is listed with an item count of two and a task count of one
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: List people with their counts
      Given one person on two tasks and one item, and one person on nothing
      When the people list is requested
      Then the first person is listed with a task count of two and an item count of one
      And the second person is listed with a task count of zero and an item count of zero
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: Linking a person is recorded
      Given a task with no people
      When a person is associated with the task
      Then a "person_added" timeline event records the person's name

    @FR-9
    Scenario: Unlinking a person is recorded
      Given a task with one person
      When the person is unassociated from the task
      Then a "person_removed" timeline event is recorded
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: Deleting a person detaches them everywhere
      Given a person linked to a task and an item
      When the person is deleted
      Then the person no longer exists
      And the task and item no longer reference them

    @FR-10
    Scenario: Deleting a task drops its people links
      Given a task linked to a person
      When the task is deleted
      Then the person still exists with a task count of zero
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: A GitHub item brings its author, assignees, and commenters
      Given a GitHub issue whose author is "a", assignees are ["b"], and commenters are ["c"]
      When the item is fetched
      Then people "a", "b", and "c" exist, each with its login as handle
      And the item is linked to all three

    @FR-11
    Scenario: The same login is one person
      Given a GitHub issue whose author and a commenter share the login "a"
      When the item is fetched
      Then exactly one person "a" exists
      And the item has exactly one link to it
    ```

- [ ] **FR-12**

    ```gherkin
    @FR-12
    Scenario: A Slack thread brings its participants
      Given a Slack thread with messages from users U1 and U2
      When the item is fetched
      Then a person exists for U1 and for U2, each keyed by its user id
      And the item is linked to both

    @FR-12
    Scenario: A repeated participant is one person
      Given a Slack thread where U1 posted three messages
      When the item is fetched
      Then exactly one person exists for U1
    ```

- [ ] **FR-13**

    ```gherkin
    @FR-13
    Scenario: Linking an item links its people to the task
      Given a GitHub item already linked to people "a" and "b"
      When the item is linked to a task
      Then the task's people include "a" and "b"
      And a "person_added" timeline event is recorded for each
    ```

- [ ] **NFR-6**

    ```gherkin
    @NFR-6
    Scenario: A failing source CLI does not break the fetch
      Given ghx is unavailable
      When a GitHub item is fetched
      Then the item is still stored
      And no person is created
    ```

- [ ] **NFR-7**

    ```gherkin
    @NFR-7
    Scenario: The same handle is one person across items
      Given a GitHub issue and a pull request by the same author "a"
      When both items are fetched
      Then the directory has exactly one person with handle "a"
      And both items link to it
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Manage a task's people
      Given a task with no people
      When the user adds a person on the task page
      Then the person appears on the task
      When the user removes the person
      Then the task has no people

    @FR-6
    Scenario: Add a new person from the task page
      Given a person is not in the directory
      When the user types a new name and adds it
      Then the person is created and linked to the task
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Show and link people on an item
      Given an item with no people
      When the user links a person to the item
      Then the item shows that person
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: Open the People page
      Given people exist with links to tasks and items
      When the user navigates to the People page
      Then each person is shown with links to their tasks and items
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Use people from the CLI
      Given a task and a person
      When the user runs `agentic person link <person> --task <task>`
      Then `agentic task get <task>` lists the person
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Links are unique rows
      Given a person already linked to a task
      When the same person is linked to the task again
      Then the task still has exactly one link to that person

    @NFR-1
    Scenario: A fresh database has the people tables
      Given a new database
      When the app starts
      Then the person, taskperson, and itemperson tables exist
    ```

- [ ] **NFR-4**

    ```gherkin
    @NFR-4
    Scenario: Linking twice is a no-op
      Given a person linked to a task
      When the link is requested again
      Then the response still reports one association and no new row is created
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: People controls fit a phone
      Given a viewport 375 px wide
      When the People page and the task's people panel are shown
      Then the names and the add control are visible without horizontal scrolling
    ```

## Conflicts

- FR-8 says the People page shows the tasks and items a person is attached to, which exposes per-person work groupings.
  This does not conflict with FEAT-p11 NFR-5 (metrics are never computed per person): the People page shows links, not measurements.

## Open Questions

1. Should a person be searchable by email or handle in the people list, or is name search enough for the first iteration?
2. Should auto-population also resolve a GitHub login to a real name and email (a profile lookup), or is the login enough?
3. Should a task expose a "primary" (owner) person distinct from the other people, or is a flat set enough?
4. Should removing an item's link to a task also remove the people it auto-added to that task, or do they stay?
