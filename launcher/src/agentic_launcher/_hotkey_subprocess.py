"""Standalone pynput hotkey listener executed as a subprocess.

On macOS, running a pynput keyboard listener in the same process as another
AppKit runloop (pystray's NSStatusItem) can crash inside CFRunLoop with
"PyEval_RestoreThread: ... GIL is released". The crash happens in C, so a
join-on-shutdown approach is not enough. Instead the parent spawns this module
via ``python -m agentic_launcher._hotkey_subprocess <spec>``; the child has no
other runloop, runs the pynput listener, and prints one line per hotkey press
that the parent reads from a small thread.
"""

from __future__ import annotations

import os
import sys
import threading
import time

from . import hotkey as hk


def _watch_parent() -> None:
    """Exit when the parent process is gone, so a dead parent leaves no orphan.

    On POSIX a dead parent reparents us to init/launchd, so our parent pid
    changes. On Windows the hotkey runs in-process, so this never runs there.
    """
    parent = os.getppid()
    while True:
        time.sleep(1.0)
        if os.getppid() != parent:
            os._exit(0)


def _run(spec_str: str) -> int:
    try:
        spec = hk.parse(spec_str)
    except hk.HotkeyParseError as exc:
        sys.stderr.write(f"[agentic-stack hotkey] invalid spec {spec_str!r}: {exc}\n")
        return 2

    from pynput import keyboard

    held: dict[str, bool] = {"ctrl": False, "shift": False, "alt": False, "cmd": False}
    debug = bool(os.environ.get("AGENTIC_STACK_DEBUG_HOTKEY"))

    def modifier_for(key: object) -> str | None:
        for mod in ("ctrl", "shift", "alt", "cmd"):
            if key in hk.modifier_keys(mod):
                return mod
        return None

    def emit() -> None:
        try:
            sys.stdout.write("FIRE\n")
            sys.stdout.flush()
        except (BrokenPipeError, ValueError):
            os._exit(0)

    def on_press(key: object) -> None:
        if debug:
            sys.stderr.write(f"[agentic-stack hotkey] press: {key!r}\n")
            sys.stderr.flush()
        mod = modifier_for(key)
        if mod is not None:
            held[mod] = True
            return
        active = {m for m, value in held.items() if value}
        if active != spec.modifiers:
            return
        if not spec.matches_key(key):
            return
        if debug:
            sys.stderr.write("[agentic-stack hotkey] fired\n")
            sys.stderr.flush()
        emit()

    def on_release(key: object) -> None:
        mod = modifier_for(key)
        if mod is not None:
            held[mod] = False

    if debug:
        sys.stderr.write(f"[agentic-stack hotkey] subprocess listening for {spec.pretty}\n")
        sys.stderr.flush()

    threading.Thread(target=_watch_parent, name="parent-watch", daemon=True).start()
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.run()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        sys.stderr.write("usage: python -m agentic_launcher._hotkey_subprocess <hotkey-spec>\n")
        return 2
    return _run(args[0])


if __name__ == "__main__":
    raise SystemExit(main())
