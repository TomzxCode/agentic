# How to schedule a shell command

## Problem

You have a script you run on a regular cadence (a backup, a report, a cleanup) and you want the app to run it for you and keep the output.

## Prerequisites

- A running API (see the [tutorial](../tutorials/getting-started.md)). The scheduler runs inside the API process, so it only fires while `agentic-server` is running.

## Steps

1. Open **Schedules** (`/schedules`) and click **New scheduled task** to reveal the form.
   - **Name**: a label for the task.
   - **Schedule**: a 5-field cron expression, `minute hour day-of-month month day-of-week`. For example `0 9 * * *` is daily at 09:00 and `*/15 * * * *` is every 15 minutes. While you type, the form lists the next 5 runs so you can check the expression before saving.
   - **Timezone**: the IANA zone the cron is read in (for example `Europe/Paris` or `America/New_York`). It defaults to your browser's zone.
   - **Shell command**: what to run. It goes through the shell, so pipes, redirects, and `&&` work as written.
   - **Working directory**: optional; leave it empty to run in the server's own directory.
2. Keep **Enabled** checked and click **Create scheduled task**.
   The row shows the next run time in the task's timezone (with your local time beside it when they differ).
3. Use **Run now** to execute it immediately, **Pause** to stop the schedule, or **Edit** to change it.
   **Edit** opens that row's form in place. Each form keeps its own draft, so opening one never clears what you typed in another, including a half-finished new task.
4. Open **Run history** on a row to see each run's status, exit code, duration, and combined output.
5. Open the **Executions** tab to see every scheduled task's runs, newest first.
   Use **Show output** on a row to read what the command printed.

Cron expressions are read in the task's timezone, which defaults to your browser's zone (the server's own zone when a task has none, such as one created from the CLI without `--timezone`). The form's preview lists each upcoming run in that zone, with your local time beside it when they differ. The preview is computed in your browser, so it updates as you type with no round trip; the server is still what decides when a task really runs, and inside the repeated hour of a daylight-saving fall-back the two can differ by one run.

`/api/schedules/preview` returns the same list from the server, evaluated with the same cron engine the scheduler uses, when you want the exact answer.

## Do it from the CLI

```bash
agentic schedule create --name backup --schedule "0 3 * * *" --command "make backup"
agentic schedule list
agentic schedule run <schedule>
agentic schedule runs <schedule>
```

## Behavior to know

- A run starts in the background, so the API returns at once and the run history fills in when it finishes.
- The scheduler wakes every `AGENTIC_SCHEDULED_TASK_TICK` seconds (default `30`), so a run starts within that window of its scheduled minute and the Schedules list refreshes on its own to show it.
- The next occurrence is advanced before the command starts, so a slow run is never started twice for the same occurrence.
- A command is stopped and marked failed after `AGENTIC_SCHEDULED_TASK_TIMEOUT` seconds (default `3600`; `0` disables the timeout).
- A run interrupted by a server restart is marked failed the next time the API starts.

## Verification

The run history shows a `succeeded` or `failed` status with the command's exit code and output, and `agentic schedule list` reports the last status and the next run time.

## Related

- [Configuration reference](../reference/configuration.md) lists `AGENTIC_SCHEDULED_TASK_TICK` and `AGENTIC_SCHEDULED_TASK_TIMEOUT`.
- [CLI reference](../reference/cli.md) and [HTTP API reference](../reference/http-api.md) cover the `schedule` commands and `/api/schedules` endpoints.
