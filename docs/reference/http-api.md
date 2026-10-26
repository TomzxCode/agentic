# HTTP API

The backend serves a JSON HTTP API under `/api`.
The web app and the `agentic` CLI both drive it.
There is no authentication, so expose it only on a trusted network.

## Health

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness check with the service name and status. |

## Tasks

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/tasks` | List tasks. Accepts `status`, `tag` (repeatable, AND), and `q`. |
| `GET` | `/api/tasks/deadlines` | Tasks with a deadline, overdue first, within a window. |
| `POST` | `/api/tasks` | Create a task. |
| `POST` | `/api/tasks/bulk` | Create or update several tasks at once. |
| `GET` / `PATCH` / `DELETE` | `/api/tasks/{id}` | Read, update, and delete a task. |
| `POST` | `/api/tasks/{id}/items` | Associate an item, by `item_id` or URL. |
| `DELETE` | `/api/tasks/{id}/items/{item_id}` | Remove an association. |
| `GET` | `/api/tasks/{id}/timeline` | The task's timeline events. |
| `GET` / `POST` | `/api/tasks/{id}/dependencies` | List and add before/after dependency links. |
| `DELETE` | `/api/tasks/{id}/dependencies/{related_id}` | Remove a dependency link. |

`POST` and `PATCH` accept `waiting_on_person_id`, `follow_up_at`, and `snoozed_until`; a waiting task is marked blocked, and a task with an active snooze or wait is parked off the stack until the date passes.
The task representation returns those fields plus `waiting_on_name`.

## Events

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/events` | Every task's timeline as one stream, newest first, with each event's task title and status. Accepts `task_id`, `type`, `actor`, `client`, `q`, `limit` (1-500, default 50), and the `before` / `before_id` cursor for older pages. |

## Worktrees, sessions, and runs

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` / `POST` | `/api/tasks/{id}/worktrees` | List and create worktrees. |
| `DELETE` | `/api/tasks/{id}/worktrees/{worktree_id}` | Remove a worktree. |
| `GET` / `POST` | `/api/tasks/{id}/sessions` | List and record agent sessions. |
| `GET` / `PATCH` / `DELETE` | `/api/tasks/{id}/sessions/{session_id}` | Read, update, and remove one recorded session. |
| `GET` / `POST` | `/api/tasks/{id}/runs` | List runs and enqueue a run (a `model` in the body overrides the harness's model for that run). |
| `POST` | `/api/tasks/{id}/context/refresh` | Enqueue a context-refresh run. |
| `GET` | `/api/tasks/{id}/context` | Preview the context a refresh would read. |
| `POST` | `/api/tasks/{id}/summary/refresh` | Enqueue a summary-refresh run. |
| `GET` | `/api/runs/{id}` | One run. |
| `GET` | `/api/runs/{id}/events` | The run's recorded events. |
| `POST` | `/api/runs/{id}/cancel` | Cancel a run. |
| `GET` | `/api/runs/{id}/stream` | Server-sent events for the agent transcript. |
| `GET` | `/api/tasks/{id}/stream` | Server-sent events for task changes. |

## Stack

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` / `POST` | `/api/stack` | List the focus queue and push a task onto it. A parked task is absent until its date passes; pushing it clears its snooze and wait. |
| `GET` | `/api/stack/history` | Soft-deleted entries, excluding those parked by a deferral. |
| `GET` | `/api/stack/current` | The current task. |
| `POST` | `/api/stack/pop` | Complete the current task and promote the next. |
| `POST` | `/api/stack/reorder` | Move an entry. |
| `POST` | `/api/stack/{id}/promote` | Make an entry current. |
| `PATCH` / `DELETE` | `/api/stack/{id}` | Edit the task or remove the entry. |

## Items, repositories, groups, and people

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` / `POST` | `/api/items` | List and create source items. A create takes `url`, `path`, or `content`; a filesystem path is stored as source `file` with kind `file` or `directory`. |
| `POST` | `/api/items/refresh-due` | Run one refresh pass immediately. |
| `POST` | `/api/items/refresh-source/{source}` | Re-fetch every item of one source now, ignoring the refresh policy. |
| `GET` / `PATCH` / `DELETE` | `/api/items/{id}` | Read, update, and delete an item. A Slack thread is marked done with `{"done": true}` and reopened with `{"done": false}`; `new_since_done` on the read says a message arrived after the decision. |
| `POST` | `/api/items/{id}/refresh` | Refresh one item now. A path is re-statted and its content is never stored. |
| `GET` | `/api/items/{id}/path` | Read a path item's current file preview or directory listing. The read does not write the content back to the item. |
| `GET` | `/api/items/{id}/reviews` | List the review reports a pull request item has on disk. |
| `GET` | `/api/items/{id}/reviews/{name}` | Read one review report. |
| `GET` | `/api/items/{id}/reviewers` | The PR's reviewers and pending review requests, one row each, read live from GitHub through `gh`. |
| `POST` | `/api/items/{id}/poke` | Send a reviewer a Slack DM asking for their review. The body is `{"login": "<github login>"}`. |
| `GET` / `POST` | `/api/repositories` | List and create registered repositories. The listing re-reads each checkout's `origin` and adopts a changed remote and derived name. |
| `POST` | `/api/repositories/bulk` | Add several repositories at once. |
| `GET` / `PATCH` / `DELETE` | `/api/repositories/{id}` | Read, update (its review-scan policy), and remove a repository. |
| `GET` / `POST` | `/api/groups` | List and create repository groups. |
| `GET` / `PATCH` / `DELETE` | `/api/groups/{id}` | Read, update, and remove a group. |
| `GET` / `POST` | `/api/people` | List and create people. |
| `GET` / `PATCH` / `DELETE` | `/api/people/{id}` | Read, update, and remove a person. |
| `POST` | `/api/people/{id}/merge` | Merge one person into another. |
| `POST` | `/api/tasks/{id}/people` | Link a person involved in a task. |
| `DELETE` | `/api/tasks/{id}/people/{person_id}` | Unlink a person from a task. |
| `POST` | `/api/tasks/{id}/requesters` | Link a person who requested a task. |
| `DELETE` | `/api/tasks/{id}/requesters/{person_id}` | Unlink a requester from a task. |
| `POST` | `/api/items/{id}/people` | Link a person on an item. |
| `DELETE` | `/api/items/{id}/people/{person_id}` | Unlink a person from an item. |
| `GET` | `/api/tags` | Tags in use, with counts. |

## Review queue

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/reviews` | Every pull request with review reports in the store, with its review-step state (`?refresh=true` re-reads each PR's GitHub fields). |
| `GET` | `/api/reviews/task/{task_id}` | The same rows, scoped to the pull requests a task is linked to. |
| `GET` | `/api/reviews/findings/{number}` | The must/should/may findings the review skills recorded, by `repository` (`owner/name`). |
| `POST` | `/api/reviews/findings/{number}/decisions` | Record the reviewer's `include`/`skip` decision on each named finding in its skill's state file; returns the updated findings. |
| `GET` | `/api/reviews/report/{number}/{name}` | Read one review report, by `repository` (`owner/name`) and its path. |
| `GET` | `/api/reviews/scan` | The review scan's cadence, its last pass, and how many pull requests it holds. |
| `POST` | `/api/reviews/scan` | Run the review scan now, ignoring its cadence. |

## My PRs

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/my-pulls` | The open pull requests the configured GitHub login authored, with each PR's check rollup, review decision, approvers, unresolved review threads, whether anyone but the author has reviewed it, the requested reviewers, and the tasks its stored item is associated with (`?refresh=true` re-queries GitHub instead of the short cache). |
| `GET` | `/api/my-pulls/checks` | One pull request's individual checks, failing first, read on demand for its CI badge's popover (query `repository` as `owner/name` and `number`; `refresh=true` bypasses the 30-second cache); each check carries its name, state, description, and detail URL, plus the rollup and the total check count. A read that could not run returns the error instead of an empty list. |
| `POST` | `/api/my-pulls/poke` | DM each named reviewer of a pull request on Slack, asking for their review. Names the PR by fields (`repository`, `number`, `title`, `url`) and takes `logins`; each login is reported as poked or failed with its reason. |

## PR feedback

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/feedback` | Every reviewer-comment analysis file in the store, with its recommendation and decision state (`?refresh=true` re-reads each PR's GitHub state). |
| `POST` | `/api/feedback/{feedback_id}/decision` | Record an `implement` / `decline` / `defer` decision, or `null` to reset it, in one analysis file's frontmatter. |

## Decisions

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/decisions` | Every colleague-decisions report under the configured notes root (`AGENTIC_NOTES_DIR` or `NOTES_DIR`, default `~/notes`), aggregated into decisions, headlines, not-heard names, and cross-cutting notes. Read-only; a missing root yields an empty payload with `root` null. |

## Scheduled tasks

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` / `POST` | `/api/schedules` | List and create cron-scheduled shell tasks. Each has a `timezone` (IANA name); omitted means the server's zone. |
| `GET` / `PATCH` / `DELETE` | `/api/schedules/{id}` | Read, update, and delete one scheduled task. |
| `POST` | `/api/schedules/{id}/run` | Run one now, ignoring its schedule. |
| `GET` | `/api/schedules/{id}/runs` | The task's run history, newest first. |
| `GET` | `/api/schedules/runs` | Every task's executions, newest first. |
| `GET` | `/api/schedules/runs/{id}` | One run, with its exit code and output. |
| `GET` | `/api/schedules/preview` | The next runs of a cron expression in a timezone (query `schedule`, optional `timezone`), plus the zone used. |

## Graph, Gantt, inbox, and operations

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/graph` | The whole before/after dependency DAG (nodes and edges). |
| `GET` | `/api/gantt` | Tasks in flight, one marker per timeline event. |
| `GET` | `/api/inbox` | Suggested next actions: reviews past the SLO, own unreviewed pull requests whose requested reviewers can each be poked (`reviewers`, with an `open_pr` action for the app's PR page), own unreviewed pull requests nobody was asked to review, closable tasks, missing change records, leftover worktrees. |
| `GET` | `/api/operations` | The provenance audit log. |

## Changes and metrics

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` / `POST` | `/api/changes` | List and record changes. |
| `GET` / `PATCH` / `DELETE` | `/api/changes/{id}` | Read, update, and delete a change. |
| `POST` | `/api/changes/{id}/status` | Move a change through its lifecycle. |
| `POST` | `/api/changes/{id}/interventions` | Record a human touch. |
| `GET` | `/api/metrics` | Autonomy rate and yield. |
| `GET` | `/api/metrics/cycle-time` | Issue-close and review cycle-time trends, per repository, read from GitHub. |
| `GET` | `/api/metrics/baselines` | List stored baselines. |
| `PUT` / `DELETE` | `/api/metrics/baselines/{metric}` | Set or clear one metric's baseline. |

## Harnesses, settings, and integrations

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/harnesses` | Harness availability and the default flag. |
| `GET` | `/api/harnesses/full` | Full harness rows. |
| `GET` | `/api/harnesses/{id}/models` | The models a harness offers, read from its ACP session. |
| `POST` | `/api/harnesses` | Create a harness. |
| `PATCH` / `DELETE` | `/api/harnesses/{id}` | Update or remove a harness. |
| `GET` / `PATCH` | `/api/settings` | Effective settings and overrides. |
| `POST` | `/api/settings/refresh-policy/preview` | Preview a refresh policy's schedule. |
| `GET` | `/api/settings/refresh-status` | When the background refresh job last ran for each source. |
| `GET` | `/api/settings/diagnostics` | Presence and versions of the external commands and harnesses the app runs. |
| `GET` | `/api/github/issues` | Issue picker for import. |
| `POST` | `/api/github/issues` | Create an issue from a title and body. |
| `GET` | `/api/github/issue` | One issue by URL. |
| `GET` | `/api/github/repository` | A repository's issues and pull requests (via `ghx`), all states by default. |
| `GET` | `/api/slack/users` | Name the Slack user ids given (via `slackx`), fetching an uncached user from Slack. |
| `GET` | `/api/fs/list` | Server-side directory picker. |
