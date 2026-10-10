# agentic-cli

Command-line client for the [Agentic](../README.md) app. It talks to a running
API over HTTP, so agents (and people) can create and maintain the app's content
without touching the database.

This is the user-facing client. The separate backend command that runs the
server lives with the backend package (`agentic-server`).

## Install

Installed with the workspace:

```bash
uv sync            # from the repository root
```

## Usage

```bash
agentic --help
agentic task create --title "Fix flaky tests"
agentic link add <task> --url https://github.com/o/r/issues/1
agentic worktree create <task>
agentic context refresh <task>
agentic run create <task> --prompt "Investigate the failure"
agentic run wait <run-id>
```

Output is JSON when piped (or with `--format json`), text otherwise. Point it at
another instance with `--api-url` or `AGENTIC_API_URL`.
