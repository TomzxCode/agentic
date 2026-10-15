# Why Agentic is local-first

Agentic is a single-user, local-first tool.
It runs on your machine, stores its data on your machine, and assumes one person is using it.

## What that means

- The default database and worktrees live under `~/.agentic`.
- Persistence is SQLite through SQLModel, and the schema is created and migrated in place rather than by a migration tool.
- There is no authentication and no multi-tenant isolation.
- Integrations are lightweight and metadata-only: GitHub uses `ghx` and Slack uses `slackx` when those CLIs are on your `PATH`.
- Agent runs go through a durable queue, so the API only enqueues and a worker executes.

## Why this design

The problem Agentic solves is scattered context for one person's work.
The threads, issues, and checkouts relevant to a piece of work live in many systems, and re-reading them to resume is slow.
Keeping the data local removes the OAuth flows, webhooks, and continuous two-way sync that a hosted, multi-tenant version would need, and it keeps the tool fast and private.

The cost is explicit. There is no hosted deployment, no shared team workspace, and no continuous sync with external systems; content is pulled on demand or on a refresh schedule.

## What it does not do

- No multi-user access, authentication, or tenancy isolation.
- No OAuth flows, webhooks, or continuous two-way sync with external systems.
- No hosted or cloud deployment.
- No interactive agent permission approval; requests are auto-approved.

## Security consequence

Because there is no authentication, anyone who can reach the port can read and change everything and can trigger agent runs.
Run Agentic only on a trusted network, or over a private VPN such as Tailscale.

## Related

- [How to expose Agentic on your network](../how-to/expose-on-your-network.md) covers the practical setup.
- [How agents are wired](../explanation/how-agents-are-wired.md) explains the queue and worker.
