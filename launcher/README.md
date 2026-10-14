# agentic-stack (launcher)

A small menu-bar / system-tray companion for Agentic's **stack**. The stack
itself lives in the Agentic backend and PWA; this process only adds the two
things a browser cannot provide: a **global hotkey** and a **tray icon**.

- Tray icon with the current task as the tooltip and a coloured badge for the
  stack depth.
- **Open Stack (Ctrl+Shift+T)** brings the stack page forward from anywhere.
- **Mark Done (pop)** pops the current task without opening the app.

## Requirements

Python 3.12+. On macOS, Tk is not needed, but the global hotkey uses `pynput`,
which needs **Accessibility** and **Input Monitoring** access (the app prompts
on first launch). Permissions are tied to the interpreter binary, not to
`agentic-stack`.

## Install and run

`uv sync` at the repository root installs the launcher into the shared
virtualenv. Run it alongside the API:

```bash
uv run agentic-stack
```

`make run` (and `make run-dev`) start it too, pointed at the Vite dev server's
stack page; `make dev-tray` runs it on its own. When it is stopped (Ctrl+C or a
signal), the hotkey listener it spawned exits with it.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `AGENTIC_API_URL` | `http://127.0.0.1:8600` | Base URL of the Agentic API. |
| `AGENTIC_STACK_URL` | `<api_url>/stack` | Page opened by the hotkey. |
| `AGENTIC_STACK_HOTKEY` | `ctrl+shift+t` | Global hotkey spec. |
| `AGENTIC_STACK_DEBUG_HOTKEY` | (unset) | Log hotkey events. |

The hotkey spec is a `+`-separated list of tokens, case-insensitive:
modifiers `ctrl`, `shift`, `alt`/`option`, `cmd`/`command`/`super`/`win`/`meta`,
plus one key (a single character, `f1`–`f24`, or a named key such as `space`,
`enter`, `esc`, `up`, `down`).
