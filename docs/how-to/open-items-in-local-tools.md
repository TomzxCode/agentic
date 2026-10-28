# How to open items in ghx and slackx

## Problem

A GitHub issue or a Slack thread opens on github.com or in the Slack app.
When you already run `ghx serve` or `slackx serve`, you want the item to open in that local UI instead, where the cached copy and its comments are a click away.

## Prerequisites

- `ghx` and/or `slackx` installed, with a warm cache.
- A running server, for example `ghx serve` (default port 8080) or `slackx serve` (default port 8280).

## Steps

1. Open **Settings → Local tools**.
2. Set **ghx server URL** to the base URL `ghx serve` prints, for example `http://localhost:8080`.
3. Set **slackx server URL** to the base URL `slackx serve` prints, for example `http://localhost:8280`.
4. Open an item.

Each GitHub item now shows **Open in ghx**, and each Slack thread shows **Open in slackx**, next to the link to the original service.
The same compact links appear in the items list and in a task's items panel.

The repository view also links into ghx: **Open in ghx** in the header opens the repository's listing, and each issue or PR row has a small **ghx** link next to its title.
The Repositories list does the same for each registered repository, from the **ghx** link next to its name.

Leave a field blank to hide that link.
A stored setting on this page wins over `AGENTIC_GHX_URL` or `AGENTIC_SLACKX_URL`.
On the `managed` transport the host still comes from that setting, but the port is the one the serve process bound, so item links follow it.

A tool on the `managed` transport needs no URL here: the server starts `ghx serve` or `slackx serve` itself, and the page shows the URL and port it answers on as a link.
That URL also stands in for a blank field, so the link appears without setting one.

## Verification

Open a GitHub issue and confirm **Open in ghx** lands on that issue in the ghx UI.
Open the repository view and confirm **Open in ghx** in the header lists the repository, and a row's **ghx** link opens that issue or PR.
Open a Slack thread and confirm **Open in slackx** opens the thread panel in the slackx UI.

## Related

- [Configuration reference](../reference/configuration.md) lists `AGENTIC_GHX_URL` and `AGENTIC_SLACKX_URL`.
- [Import a GitHub issue or Slack thread](import-work.md) describes how items are created.
