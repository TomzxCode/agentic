# How to send events to Slack

## Problem

You want Agentic's events (timeline activity, test notifications) delivered to you in Slack instead of checking the app.

## Prerequisites

- A running API (see the [tutorial](../tutorials/getting-started.md)).
- A Slack workspace where you can install an app.

## Create a Slack app and bot token

1. Open [https://api.slack.com/apps](https://api.slack.com/apps) and click **Create New App** → **From scratch**.
2. Name the app (for example `Agentic`) and pick your workspace.
3. Under **Features → OAuth & Permissions**, scroll to **Scopes → Bot Token Scopes** and add:
   - `chat:write` (post messages)
   - `im:write` (open DMs with users)
   - `users:read` (optional, to resolve user names)
4. Click **Install to Workspace** and approve.
5. Copy the **Bot User OAuth Token** (it starts with `xoxb-`). This is your `SLACK_BOT_TOKEN`.

A bot token needs no cookie. Leave `SLACK_COOKIE` unset.

## Configure Agentic

Set the token in your environment:

```bash
export SLACK_BOT_TOKEN=xoxb-...
```

Or in `.env`:

```text
SLACK_BOT_TOKEN=xoxb-...
```

Set where notifications go. Either an environment variable:

```bash
export SLACK_USER_ID=U0123ABCDEF
# or a channel:
export SLACK_EVENTS_CHANNEL=C0123ABCDEF
```

Or under **Settings → Slack** in the web UI, where the same fields are editable and saved to the database. `SLACK_EVENTS_USER_ID` and `SLACK_NOTIFY_USER_ID` override `SLACK_USER_ID` when set.

## Send a test notification

Open **Settings → Slack** and click **Send test notification**. A message should arrive from the bot in Slack. If it fails, the error from Slack is shown next to the button and in the toast.

If you see `not_in_channel`, the bot is not a member of the target channel. Either:
- invite the bot to that channel (`/invite @Agentic` in the channel), or
- send to a user instead by setting `SLACK_USER_ID` to your own Slack user id (a `U...` value), which the bot can DM directly.

## Send events from the CLI

```bash
agentic events send-slack --user-id U0123ABCDEF
agentic events send-slack <event-id> --user-id U0123ABCDEF
```

Omit `--user-id` to use the configured default recipient.

## Related

- [Configuration reference](../reference/configuration.md) lists `SLACK_BOT_TOKEN`, `SLACK_USER_ID`, `SLACK_EVENTS_USER_ID`, `SLACK_EVENTS_CHANNEL`, and `SLACK_NOTIFY_USER_ID`.
- The item view's poke action still uses `SLACK_TOKEN` (and `SLACK_COOKIE` for a web token).