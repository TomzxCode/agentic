# How to refresh items on a schedule

## Problem

Slack threads and GitHub issues go stale at different rates, and you do not want to re-fetch every one by hand.

## Prerequisites

- A running API (see the [tutorial](../tutorials/getting-started.md)).
- `slackx` and/or `ghx` on your `PATH` for the sources you want refreshed.

## Steps

1. Open **Settings → Refresh**.
   Each source has a live preview of its policy as you type.
2. Set a policy for Slack and a policy for GitHub.
   A policy is a comma-separated list of `age=interval` bands, with an optional `*` fallback:

   ```text
   1d=1h,7d=6h,30d=1d,*=7d
   ```

   This reads: refresh hourly while the item is under a day old, every 6 hours under a week, daily under 30 days, and weekly after that.
3. Omit the `*` band, or write `*=never`, to stop refreshing once an item outgrows the last band.
   An empty policy disables that source.
4. Set the check tick, the number of seconds between checks for items that are due.
   A tick of `0` disables the loop.

An item's age is its upstream creation time when known (a GitHub `createdAt`, a Slack thread timestamp), and otherwise the time it was recorded.

## Do it from the CLI

```bash
agentic settings set \
  --slack-refresh-policy "1d=1h,*=7d" \
  --github-refresh-policy "1d=1h,30d=1d"
agentic item refresh-due
```

`agentic item refresh-due` runs one pass immediately instead of waiting for the tick.

## Verification

After a pass, the refreshed items carry newer fetched content, and items whose policy has expired are left untouched.

## Related

- [Configuration reference](../reference/configuration.md) lists `AGENTIC_SLACK_REFRESH_POLICY`, `AGENTIC_GITHUB_REFRESH_POLICY`, and `AGENTIC_ITEM_REFRESH_TICK`.
