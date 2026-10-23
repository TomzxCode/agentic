<!-- session_link: http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl -->
# Observability

## Monitoring Pillars

| Pillar | System | Status |
|---|---|---|
| Metrics | none | Not configured |
| Logging | structlog (stdout) | In use |
| Tracing | none | Not configured |
| Profiling | none | Not configured |

## Instrumentation Libraries

| Library | Pillar | Configuration |
|---|---|---|
| structlog | Logging | `structlog.get_logger(__name__)`; key/value structured events stamped to the millisecond (`log_setup.configure_logging`); output goes to the process stdout via uvicorn |
| uvicorn | Logging | Access and startup logs at default level |

## Log Aggregation

Logs are emitted to stdout as structured events and are not shipped anywhere.
Notable events: `agentic ready`, `tool call` (carries `cmd` and the `mode` transport), `cli fetch failed`, `fetch_source failed`, `failed to persist agent event`, `agent run failed`.

## Tracing

None.
An agent run's transcript (`AgentEvent` rows, streamed over SSE) is the closest thing to a trace of a run.

## Alerting

| Alert | Source | Routing | Severity |
|---|---|---|---|
| (none) | — | — | — |

No alerting is configured.

## Dashboards

| Dashboard | Location | Purpose |
|---|---|---|
| (none) | — | — |

No dashboards exist.

## SLO Reference

No service-level objectives are defined.
`service-levels.md` is not present.
