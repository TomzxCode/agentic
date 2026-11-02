<!-- session_link: http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl -->
# Observability

## Monitoring Pillars

| Pillar | System | Status |
|---|---|---|
| Metrics | none | Not configured |
| Logging | structlog (stdout plus a local log file) | In use |
| Tracing | none | Not configured |
| Profiling | per-request debug middleware, in memory | In use |
| Audit trail | `Operation` rows in SQLite | In use |
| Run history | `AgentRun` and `ScheduledTaskRun` rows in SQLite | In use |
| Alerting | none | Not configured |

No Prometheus, OpenTelemetry, Sentry, or Datadog client appears in any pyproject file.
The only instrumentation dependency is structlog.
The `metrics.py` module and the `/metrics` page are product metrics (autonomy rate and yield), not monitoring instrumentation.

## Instrumentation Libraries

| Library | Pillar | Configuration |
|---|---|---|
| structlog | Logging | `structlog.get_logger(__name__)`; console renderer stamped to the millisecond (`log_setup.configure_logging`), with a file sink appending every rendered line to the log file |
| uvicorn | Logging | Access lines rerouted through structlog by `request_logging.configure_request_logging` |

## Log Aggregation

Logs are not shipped anywhere.
Each structlog event renders to the process stdout through uvicorn.
The same rendered lines are appended, with ANSI codes stripped, to a log file.
The default path is `<data_dir>/agentic.log`, and `AGENTIC_LOG_FILE` overrides it or disables the file with `none` or `off` (`config.log_path`).
The file rotates at 10 MB and keeps 5 backups (`log_setup.py`).
The level comes from `AGENTIC_LOG_LEVEL` (default `info`, applied by `log_setup.configure_logging` to structlog and by `agentic-server serve` to uvicorn).
Notable events: `agentic ready`, `tool call` (carries `cmd` and the `mode` transport), `cli fetch failed`, `fetch_source failed`, `failed to persist agent event`, `agent run failed`.
`RequestErrorMiddleware` adds a `request failed` event for every 4xx or 5xx with method, path, status, duration, and the API error detail, logged at error level for 5xx and warning otherwise.
At `debug` level, each request is followed by the breakdown the `DebugMiddleware` collected, as separate lines: `request phase` for each named step a handler timed, a `request db` summary (`queries`, `time_ms`), and a `request tools` summary (`calls`, `time_ms`, `slowest`) for the helper CLI calls (`ghx`, `slackx`).
The review queue times its store scan as `review store dirs` (finding the PR directories) and `review store check` (the per-directory mtime check), with `review store view`, `review store reports`, and `review store state` appearing only for the directories that changed.
`review_store._DIR_CACHE` keeps each PR directory's parsed state keyed by the name, mtime, and size of its report files and in-progress markers, so an unchanged directory is not read again; the `calls` count on those lines says how many directories were read.
A step that repeats (once per pull request) folds into one line carrying its summed `duration_ms` and a `calls` count.
`run_parallel` copies the requesting context into its worker threads, so a CLI call made there is still charged to the request that caused it.

## Operation Audit Trail

`ProvenanceMiddleware` writes one `Operation` row per mutating `/api/` request (POST, PUT, PATCH, DELETE).
Each row records the method, path, status code, client, actor, and timestamp (`models/system.py`).
The client (`web`, `cli`, or `api`) and actor (`human` or `agent`) come from the `x-agentic-client` and `x-agentic-actor` headers, falling back to `api` and `human`.
`GET /api/operations` reads rows back, newest first, filterable by client and actor, with a limit of up to 500.
The CLI exposes it as `agentic operation list`, and the SPA has an `api.operations.list` client but no page for it yet.

## Run History

Agent runs execute as SAQ jobs in a worker process, and each run's status, start and end times, and error land on its `AgentRun` row.
`reconcile_runs()` marks queued or running runs whose job is gone as failed on startup (`jobs.py`).
Each scheduled task execution gets a `ScheduledTaskRun` row with its exit code and the last 20,000 characters of output.
`reconcile_scheduled_runs()` marks runs left running by a restart as failed (`schedules.py`).

## Tracing

None.
No tracer is configured and no trace ids are propagated.
An agent run's transcript (`AgentEvent` rows, streamed over SSE) is the closest thing to a trace of a run.

## Alerting

| Alert | Source | Routing | Severity |
|---|---|---|---|
| (none) | — | — | — |

No alerting is configured.
The review SLO and inbox nudge settings (`review_slo`, `review_nudge_slo`) are product features that surface overdue reviews inside the app, not alerting infrastructure.

## Dashboards

| Dashboard | Location | Purpose |
|---|---|---|
| Diagnostics | Settings page (`SettingsDiagnostics.vue`, `GET /api/settings/diagnostics`) | Presence, path, and version of Python, git, ghx, gh, slackx, and each ACP harness, plus the ghx and slackx cache contents |
| Debug bar | Status bar (`StatusBar.vue`, fed by `GET /api/debug/requests` and `GET /api/debug/cli`) | Recent requests with duration, database query count and time, and helper CLI calls |
| Events | `/events` | Every task's timeline in one stream, filterable by actor and client |
| Process | `/process` | Pipeline queues and cycle-time distributions from `GET /api/process` |
| Schedules | `/schedules` | Scheduled task definitions and their run history |

No external dashboards exist, and the operations audit log has no SPA page.

## SLO Reference

No service-level objectives are defined.
