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
| `POST` | `/api/tasks/bulk` | Update several tasks at once (status, priority, tags). |
| `DELETE` | `/api/tasks/bulk` | Delete several tasks at once, by `ids`. |
| `GET` / `PATCH` / `DELETE` | `/api/tasks/{id}` | Read, update, and delete a task. |
| `POST` | `/api/tasks/{id}/items` | Associate an item, by `item_id` or URL. |
| `DELETE` | `/api/tasks/{id}/items/{item_id}` | Remove an association. |
| `GET` | `/api/tasks/{id}/timeline` | The task's timeline events. |
| `GET` / `POST` | `/api/tasks/{id}/dependencies` | List and add task links. `POST` takes `related_id` and a `relation` of `before`, `after`, or `related`; a `related` link is symmetric and unconstrained by the dependency cycle check. |
| `DELETE` | `/api/tasks/{id}/dependencies/{related_id}` | Remove a link of either kind. |

`POST` and `PATCH` accept `waiting_on_person_id`, `follow_up_at`, and `snoozed_until`; a waiting task is marked blocked, and a task with an active snooze or wait is parked off the stack until the date passes.
The task representation returns those fields plus `waiting_on_name`.

The task detail (`GET /api/tasks/{id}`) also returns `checklist`, a list of the task's checklist items.

## Checklists

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` / `POST` | `/api/checklist-templates` | List and create checklist templates. |
| `PATCH` / `DELETE` | `/api/checklist-templates/{id}` | Update or delete a template. Deleting a template also removes the items it put on tasks. |
| `POST` | `/api/checklist-templates/{id}/apply` | Add the template's missing items to every task that currently matches it. |
| `POST` | `/api/tasks/{id}/checklist` | Add a manual item. |
| `POST` | `/api/tasks/{id}/checklist/apply` | Add missing items from templates already applied to the task. |
| `POST` | `/api/tasks/{id}/checklist/reorder` | Apply a new display order; the body is `{"item_ids": [...]}` in the wanted order. Listed items get positions `0..n-1`, unlisted ones keep their relative order after them, and ids from another task are ignored. |
| `PATCH` / `DELETE` | `/api/tasks/{id}/checklist/{item_id}` | Check or uncheck, rename, or remove an item. |

A template has a `name`, an optional `description`, a list of `rules`, and a list of `items`.
Every rule must match for the template to apply.
A rule is `{"field": ..., "op": ..., "values": [...]}`.

- Fields: `status`, `priority`, `waiting_on`, `tags`, `people`, `requested_by`, `repositories`, `before`, `after`, `related`.
- Operators: `is_any` / `is_not_any` for `status` and `priority`; `has_any` / `has_all` / `has_none` for the list fields; `is_set` / `is_not_set` for `waiting_on`.
- `before` means the task has a prerequisite task in `values`; `after` means it has a following task in `values`; `related` means a related task in `values`.

The first time a task matches, the template's items are copied onto it and recorded, so editing the task later does not duplicate them.
Each item in the task detail carries `applicable`, which is false when its template no longer matches the task; the item stays but the UI disables it.
A manual item has no template and always applies.


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
| `GET` | `/api/stack/stream` | Server-sent events carrying the whole stack, sent on connect, on every write, and when a parked task's date passes. The tray follows this instead of polling. |
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
| `GET` | `/api/items/{id}/reviewers` | The PR's reviewers and pending review requests, one row each, read live from GitHub through `ghx`. |
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
| `GET` | `/api/reviews` | Every pull request with review reports in the store, with its review-step state and, for a row past the review SLO, `slo_wait_seconds` and `slo_seconds` (`?refresh=true` re-reads each PR's GitHub fields). |
| `GET` | `/api/reviews/task/{task_id}` | The same rows, scoped to the pull requests a task is linked to. |
| `GET` | `/api/reviews/findings/{number}` | The must/should/may findings the review skills recorded, by `repository` (`owner/name`). |
| `POST` | `/api/reviews/findings/{number}/decisions` | Record the reviewer's `include`/`skip` decision on each named finding in its skill's state file; returns the updated findings. |
| `GET` | `/api/reviews/report/{number}/{name}` | Read one review report, by `repository` (`owner/name`) and its path. |
| `GET` | `/api/reviews/scan` | The review scan's last pass and how many pull requests it holds. |
| `POST` | `/api/reviews/scan` | Run the review scan now, without waiting for the next cache refresh. |

## My PRs

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/my-pulls` | The open pull requests the configured GitHub login authored across the registered GitHub repositories, with each PR's check rollup, review decision, approvers, unresolved review threads, whether anyone but the author has reviewed it, the requested reviewers, and the tasks its stored item is associated with. Each read lists them together from ghx's cache; a background job refreshes that cache, never this read, and `?refresh=true` only bypasses the short answer cache. |
| `GET` | `/api/my-pulls/checks` | One pull request's individual checks, failing first, read on demand through `ghx pr checks` for its CI badge's popover (query `repository` as `owner/name` and `number`; `refresh=true` bypasses the 30-second cache); each check carries its name, state, description, and detail URL, plus the rollup and the total check count. A read that could not run returns the error instead of an empty list. |
| `POST` | `/api/my-pulls/poke` | DM each named reviewer of a pull request on Slack, asking for their review. Names the PR by fields (`repository`, `number`, `title`, `url`) and takes `logins`; each login is reported as poked or failed with its reason. |

## PR feedback

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/feedback` | Every reviewer-comment analysis file in the store, with its recommendation and decision state (`?refresh=true` re-reads each PR's GitHub state). `repo` (`owner/name`, case-insensitive) and `pr` narrow the read to one pull request, which is what the PR view's Feedback tab asks for. |
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

## Webhooks and event bus

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` / `POST` | `/api/webhooks/endpoints` | List and create entry points. `kind` is `generic` or `github`; the secret is the HMAC key on GitHub and an optional shared token on a generic endpoint. |
| `GET` / `PATCH` / `DELETE` | `/api/webhooks/endpoints/{id}` | Read, update, or delete one endpoint with its subscriptions and stored events. |
| `GET` / `POST` | `/api/webhooks/endpoints/{id}/subscriptions` | List or create the workflows wired to an endpoint. Each carries `events` (empty matches all) and `filters` (`path` plus `equals`, `contains`, or `exists`). |
| `GET` | `/api/webhooks/subscriptions` | Every subscription, optionally filtered by `endpoint_id`. |
| `PATCH` / `DELETE` | `/api/webhooks/subscriptions/{id}` | Update or remove one subscription. |
| `GET` | `/api/webhooks/events` | Stored deliveries, newest first; query `endpoint_id`, `event_type`, `limit`. |
| `GET` | `/api/webhooks/events/{id}` | One event with its payload and the workflows it started. |
| `POST` | `/api/webhooks/events/{id}/replay` | Deliver a stored event to the current subscriptions again. |
| `POST` | `/api/webhooks/endpoints/{id}/test` | Send a sample event through an endpoint, skipping its secret. |
| `POST` | `/api/hooks/{id}` | The generic inbound entry point. Optional secret in `X-Webhook-Secret`, `Authorization: Bearer`, or `?secret=`. Event type from `?event=` or `X-Event-Type`. |
| `POST` | `/api/hooks/github/{id}` | The GitHub inbound entry point. Verifies `X-Hub-Signature-256` against the endpoint secret; event type and delivery id come from GitHub's headers. |

Both inbound routes answer `202` with the stored event id, its type, and one delivery per matching workflow (`started`, `skipped`, or `failed`).

## Graph, Gantt, inbox, and operations

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/graph` | The whole before/after dependency DAG (nodes and edges). |
| `GET` | `/api/gantt` | Tasks in flight, one marker per timeline event. |
| `GET` | `/api/inbox` | Suggested next actions: reviews past the SLO, own unreviewed pull requests whose requested reviewers can each be poked (`reviewers`, with an `open_pr` action for the app's PR page), own unreviewed pull requests nobody was asked to review, closable tasks, missing change records, leftover worktrees. |
| `GET` | `/api/operations` | The provenance audit log. |

## Page visits

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/page-visits` | Record a batch of page visits (`{ "visits": [...] }`, each with `path`, `route_name`, `title`, `started_at`, and `ended_at`). Visits under a second or over a day are dropped, and recording one does not write an operations audit row. |
| `GET` | `/api/page-visits/report` | Time per page, per place, and per local day over a window. Accepts `days` (default 7) and `tz_offset` (the client's offset from UTC in minutes, east positive). |
| `GET` | `/api/page-visits/visits` | Every visit overlapping a time range, oldest first. Accepts `start` and `end` as ISO instants (defaulting to today's local day) and `tz_offset` for that default. A range may not exceed 366 days. |

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
| `GET` | `/api/settings/refresh-status` | When the background refresh job last ran for each source, and the ghx cache job. |
| `POST` | `/api/settings/ghx-cache/refresh` | Run the ghx cache pass now, ignoring its cadence and any repository's retry backoff. Waits for the pass. |
| `GET` | `/api/settings/diagnostics` | Presence and versions of the external commands and harnesses the app runs. |
| `GET` | `/api/github/issues` | Issue picker for import. |
| `POST` | `/api/github/issues` | Create an issue from a title and body. |
| `GET` | `/api/github/issue` | One issue by URL. |
| `GET` | `/api/github/pull/reviewers` | A pull request's reviewers, read from its `?url=` the way the item read does. Backs the standalone pull request page, which has no stored item to address. |
| `POST` | `/api/github/pull/poke` | Send a reviewer a Slack DM asking for their review, addressed by URL. The body is `{"url": "...", "title": "...", "login": "<github login>"}`. |
| `GET` | `/api/github/repository` | A repository's issues and pull requests (via `ghx`), all states by default, read from ghx's cache. The cache is refreshed by a background job, never by this endpoint, so it never waits on a delta fetch. |
| `GET` | `/api/slack/users` | Name the Slack user ids given (via `slackx`), fetching an uncached user from Slack. |
| `GET` | `/api/fs/list` | Server-side directory picker. |
