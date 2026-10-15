# How agents are wired

Agentic does not know how to talk to any particular agent.
It speaks the **Agent Client Protocol (ACP) over stdio**, and each harness is just a command row in the `harness` table.
That abstraction is what lets you switch harnesses without changing app code.

## The run pipeline

Each agent run is a job on a queue (SAQ, backed by SQLite by default), not an in-process task.
The API only enqueues; one or more worker processes dequeue and run the harness.

```
FastAPI ──enqueue──▶ queue (SQLite) ◀──dequeue── worker ──spawn──▶ opencode acp   ┐
   ▲                                                                 pi-acp        ├── ACP JSON-RPC over stdio ──▶ agent
   │                                                               (your harness)  ┘
   └── SSE ◀── normalized events ──▶ UI
```

This design has three consequences:

- A long agent turn survives an API restart, because the job lives in the queue, not in the API process.
- A failed run can be retried, and the retry resumes the session it recorded, so it continues the conversation instead of starting over.
- Workers scale independently of the API.

Runs left queued or running with no live job are marked failed when the API starts.
You must run a worker (`agentic-server worker`) for runs to make progress.

## Default harnesses

Agentic seeds these harnesses automatically.

| Id | Command | Notes |
| --- | --- | --- |
| `opencode2` | `opencode2 acp` | OpenCode v2. Seeded as the default when installed. |
| `opencode` | `opencode acp` | OpenCode v1. The default when v2 is not installed. |
| `pi` | `pi-acp` | `pi` through the pi-acp adapter. |

The default harness runs when a task does not pick one.
Change it under **Settings → Agent harnesses**, where the default is marked with a badge.

## Model selection

A harness can carry a **model**.
The runner selects it over ACP with `session/set_config_option(config_id="model", ...)` after the session is created or resumed.
A blank model uses the harness's own default.
A harness that does not expose a model config option logs a warning and runs with its own default, and the run is not failed.

## Events

The worker normalizes the harness's ACP output into events: `message`, `thought`, `tool_call`, `tool_update`, `plan`, `usage`, `status`, and `error`.
The UI streams them over server-sent events.
Context refresh reads `message` events and falls back to `thought` events only when the agent produced no message text, so a thought and a message are never concatenated.

## Related

- [Concepts](../explanation/concepts.md) defines the run, session, and change records.
- [Run an agent against a task](../how-to/run-an-agent.md) is the practical guide.
