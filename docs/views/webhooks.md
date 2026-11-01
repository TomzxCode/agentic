# Webhooks

`/webhooks` is the event bus surface: the entry points an outside system posts to, the execution graphs each one triggers, and the deliveries that arrived.

## Problem

Reacting to the outside world usually means a webhook receiver you cannot see, a script nobody owns, and a log you never read.
This page keeps the endpoint, its secret, the workflows it feeds, and every delivery in one place, so a broken automation is a row you can inspect rather than a silence you have to guess about.

## How to use it

### The page

The header reads `Webhooks` with a count and a `Refresh` button, and there are two tabs:

| Tab | What it shows |
| --- | --- |
| `Endpoints` | One card per entry point: kind, inbound URL, secret state, workflow count, stored event count, and its actions. |
| `Events` | Every stored delivery, newest first, expandable into its payload and the workflows it started. |

### Endpoints

| Field | Notes |
| --- | --- |
| `Name` | A label, for example `GitHub pull requests`. |
| `Kind` | `Generic JSON webhook` or `GitHub webhook`. |
| `Description` | Optional. |
| `Secret` | On GitHub this is the HMAC key used to verify the signature; on a generic endpoint it is an optional shared token. |
| `Enabled` | Unchecking it (or `Pause`) makes the endpoint refuse new deliveries. |

An inbound URL is one of:

| Kind | URL |
| --- | --- |
| Generic | `<origin>/api/hooks/<endpoint-id>` |
| GitHub | `<origin>/api/hooks/github/<endpoint-id>` |

`Copy URL` copies the exact address for the current origin.

### Row actions

| Action | What it does |
| --- | --- |
| `Test` | Sends a sample event through the endpoint, skipping the secret. |
| `Workflows (n)` | Opens the subscriptions for that endpoint, with their form. |
| `Pause` / `Resume` | Stops or resumes accepting deliveries. |
| `Edit` | Opens the endpoint's form in place. |
| `Delete` | Deletes the endpoint with its subscriptions and stored events, after a confirmation. |

### Workflows

A workflow is an execution graph wired to an endpoint.
The editor's **Event trigger** step is what receives the payload; its event fields are JSON paths into the event, and downstream steps read them like any other input.

| Field | Notes |
| --- | --- |
| `Workflow` | The execution graph to run. |
| `Label` | Optional name for this subscription. |
| `Event types` | Comma separated, for example `pull_request, issues`. Empty means every event. |
| `Payload filters` | Each condition is a JSON path plus `equals`, `contains`, or `exists`. All conditions must hold. |

A matching event starts one execution of the graph. The execution's trigger step receives the whole payload, and each event field resolves its path to text (an object or list becomes JSON, a missing path becomes empty text).

### Events

Each row shows the event type, the endpoint, when it arrived, its delivery count, and GitHub's delivery id when there is one.

`Payload` expands the row into the stored body and one line per workflow delivery:

| Status | Meaning |
| --- | --- |
| `started` | The workflow's execution started; its id is linked. |
| `skipped` | The graph is paused, so nothing ran. |
| `failed` | The graph is missing, invalid, or already running; the reason is shown. |

`Replay` delivers the stored event to the current subscriptions again, which starts another execution.
There is no per-event delete; clearing history means deleting the endpoint.

## Authentication

- A GitHub endpoint requires a secret. Every delivery is checked against `X-Hub-Signature-256` (HMAC-SHA256 of the raw body) and a mismatch is rejected with `401`. Without a configured secret the endpoint returns `400`.
- A generic endpoint with a secret accepts either `X-Webhook-Secret: <secret>` or `Authorization: Bearer <secret>`, and also the `?secret=` query parameter. A wrong or missing secret is rejected with `401`.
- A disabled endpoint is rejected with `403`.
- An event type comes from `X-GitHub-Event`, `X-Event-Type`, or the `?event=` query parameter, in that order of specificity, falling back to `event`.

## CLI and agent interface

| Operation | CLI | HTTP |
| --- | --- | --- |
| List endpoints | `agentic webhooks list` | `GET /api/webhooks/endpoints` |
| Read one | `agentic webhooks get <endpoint>` | `GET /api/webhooks/endpoints/{id}` |
| Create | `agentic webhooks create --name "GitHub PRs" --kind github --secret <secret>` | `POST /api/webhooks/endpoints` |
| Update or pause | `agentic webhooks update <endpoint> …` | `PATCH /api/webhooks/endpoints/{id}` |
| Delete | `agentic webhooks delete <endpoint>` | `DELETE /api/webhooks/endpoints/{id}` |
| List workflows | `agentic webhooks subscriptions <endpoint>` | `GET /api/webhooks/endpoints/{id}/subscriptions` |
| Wire a graph | `agentic webhooks subscribe <endpoint> <graph> --event pull_request --filter action=opened` | `POST /api/webhooks/endpoints/{id}/subscriptions` |
| Remove a workflow | `agentic webhooks unsubscribe <subscription>` | `DELETE /api/webhooks/subscriptions/{id}` |
| List events | `agentic webhooks events <endpoint>` | `GET /api/webhooks/events` |
| Read one event | `agentic webhooks event <event>` | `GET /api/webhooks/events/{id}` |
| Replay | `agentic webhooks replay <event>` | `POST /api/webhooks/events/{id}/replay` |
| Send a sample | `agentic webhooks test <endpoint> --event pull_request --payload payload.json` | `POST /api/webhooks/endpoints/{id}/test` |
| Receive (generic) | the sender posts directly | `POST /api/hooks/{id}` |
| Receive (GitHub) | the sender posts directly | `POST /api/hooks/github/{id}` |

## Related

- [How to trigger a workflow from a webhook](../how-to/trigger-workflows-from-webhooks.md).
- [HTTP API](../reference/http-api.md) for the `/api/webhooks` and `/api/hooks` endpoints.
- [CLI reference](../reference/cli.md) for the `webhooks` commands.
