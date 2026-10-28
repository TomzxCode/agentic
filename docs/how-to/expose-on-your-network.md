# How to expose Agentic on your network

## Problem

You want to drive Agentic from another device, such as a phone or a laptop, over your local network or a VPN.

## Prerequisites

- A running API and frontend (see the [tutorial](../tutorials/getting-started.md)).

## Steps

1. Start the API bound to all interfaces, which is what the tutorial command already does:

   ```bash
   uv run agentic-server serve --host 0.0.0.0 --port 8600 --reload
   ```

2. Open the frontend dev server from the other device at `http://<host>:5173`.
   The Vite config exposes `host: true`, so the dev server listens on all interfaces.
3. If you reach it through a hostname rather than an IP address, add that hostname to `server.allowedHosts` in `frontend/vite.config.js`.
   IP addresses are always allowed.
4. Bind the frontend dev server the same way, or build the SPA and let the API serve it on `http://<host>:8600`.
5. If ghx or slackx runs on the `managed` transport, the server starts it on all interfaces too; Settings → Local tools shows the port each one answers on.

## Verification

The app loads from the other device and its API calls succeed.
The built app installs as a PWA from the same URL.

## Keep it on a trusted network

Agentic has no authentication and no multi-tenant isolation.
Anyone who can reach the port can read and change everything, and can trigger agent runs.
The same applies to a managed tool's web UI: it has no login either, so anyone who can reach its port can read what it cached (its JSON-RPC endpoint does require the token the server generates).
Expose it only on a trusted network, or over a private VPN such as Tailscale.

## Related

- [Why Agentic is local-first](../explanation/local-first.md) explains these constraints and their trade-offs.
- [Configuration reference](../reference/configuration.md) lists the binding-related variables.
