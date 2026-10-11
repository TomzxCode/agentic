---
title: "Repositories, groups, and directory picker"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: Repositories, groups, and directory picker

## Overview

Tasks work against local git checkouts.
This feature registers repositories by path, groups them into named sets that tell a task's agent which checkouts may be relevant, and provides a server-side directory picker so the user can select folders on the machine rather than typing absolute paths.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Point tasks at the right checkouts without typing paths |
| Coding agent | Know which repositories may contain relevant information |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall register a local git repository by path, detecting its remote URL and default branch, and reject a path that is not a git repository. |
| FR-2 | Must | The system shall add several repositories at once and report per-path errors. |
| FR-3 | Must | The system shall list, read, and delete repositories; deleting removes their worktrees and memberships but never touches files on disk. |
| FR-4 | Must | The system shall create a repository group with a name, description, and member repositories, and update its members. |
| FR-5 | Must | The system shall list, read, update, and delete groups; deleting a group detaches tasks rather than deleting them. |
| FR-6 | Must | The system shall browse the server filesystem for the picker, confined to the configured root, marking which folders are git repositories. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Security | Directory browsing shall refuse any path outside the configured root (`AGENTIC_FS_ROOT`). |
| NFR-2 | Should | Reliability | Bulk add shall continue past a bad path and report every failure. |
| NFR-3 | Should | Usability | Directory listings shall be alphabetical and optionally include hidden folders. |

## Constraints

- Repository paths are resolved to absolute paths and must contain `.git`.
- Group membership and task associations reference repositories by foreign key, so deleting a repository must clean those up first.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Register a git repository
      Given a directory containing .git
      When the user adds it as a repository
      Then a repository is created with its path, remote_url, and default_branch detected
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Refuse to browse outside the root
      Given a configured root of /home/user
      When the picker requests /etc
      Then the response is 403
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Mark git folders
      Given a root with one git checkout and one plain folder
      When the picker lists the root
      Then the checkout entry has is_git true and the plain folder has is_git false
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should deleting a repository be blocked while tasks still reference it, or always detach as it does now?
