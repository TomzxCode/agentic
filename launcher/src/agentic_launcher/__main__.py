"""Entry point for the Agentic stack menu-bar companion.

Environment:

- ``AGENTIC_API_URL``: base URL of the Agentic API (default ``http://127.0.0.1:8600``).
- ``AGENTIC_STACK_URL``: page to open on the hotkey (default ``<api_url>/stack``).
- ``AGENTIC_STACK_OPEN``: shell command template (with ``{url}``) used to open the
  page; default opens a Chromium browser app window, e.g. ``open -a Agentic``.
- ``AGENTIC_STACK_HOTKEY``: hotkey spec (default ``ctrl+shift+t``).
- ``AGENTIC_STACK_DEBUG_HOTKEY``: set to log hotkey events.
"""

from __future__ import annotations

import os
import sys

from . import hotkey as hk
from .app import TrayApp
from .client import DEFAULT_API_URL, StackClient
from .macos_permissions import diagnose_hotkey_environment, ensure_hotkey_permissions

DEFAULT_HOTKEY = "ctrl+shift+t"


def main() -> None:
    api_url = os.environ.get("AGENTIC_API_URL", DEFAULT_API_URL).rstrip("/")
    stack_url = os.environ.get("AGENTIC_STACK_URL") or f"{api_url}/stack"
    spec_str = os.environ.get("AGENTIC_STACK_HOTKEY", DEFAULT_HOTKEY)

    try:
        spec = hk.parse(spec_str)
    except hk.HotkeyParseError as exc:
        sys.stderr.write(f"agentic-stack: invalid hotkey {spec_str!r} ({exc}); falling back to {DEFAULT_HOTKEY!r}.\n")
        spec = hk.parse(DEFAULT_HOTKEY)

    if sys.platform == "darwin":
        ensure_hotkey_permissions()
        for warning in diagnose_hotkey_environment():
            sys.stderr.write(f"agentic-stack: {warning}\n")

    client = StackClient(api_url)
    tray = TrayApp(client, stack_url, hotkey_label=spec.pretty, open_template=os.environ.get("AGENTIC_STACK_OPEN"))
    try:
        tray.run(spec)
    finally:
        tray.stop()
        client.close()


if __name__ == "__main__":
    main()
