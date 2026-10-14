"""The menu-bar companion: a tray icon, a global hotkey, and Mark Done (pop).

The stack itself lives in the Agentic backend and PWA; this process is only a
native launcher. It shows the current task in the tray, opens the stack page on
the global hotkey, and pops the current task from the tray menu.
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
import threading
import webbrowser
from collections.abc import Callable

import pystray

from . import hotkey as hk
from .client import StackClient
from .icon import make_icon

# How often the tray re-reads the stack, so changes made in the PWA show up.
POLL_SECONDS = 30.0


def _on_main(fn: Callable[[], None]) -> None:
    """Run ``fn`` on the platform main thread when the backend requires it.

    AppKit (macOS) and the tray toolkits require UI updates on the main thread,
    but the tray is refreshed from a background poll thread and from the hotkey
    reader thread, so marshal the update.
    """
    if sys.platform == "darwin":
        try:
            from PyObjCTools import AppHelper

            AppHelper.callAfter(fn)
            return
        except Exception:
            pass
    fn()


class HotkeyListener:
    """Global hotkey that fires a callback when pressed.

    On macOS the pynput listener runs in a subprocess (see
    ``_hotkey_subprocess``) so it never shares an AppKit runloop with the tray.
    On other platforms it runs in-process on a background thread.
    """

    def __init__(self, callback: Callable[[], None], spec: hk.HotkeySpec) -> None:
        self._callback = callback
        self._spec = spec
        self._listener = None
        self._proc: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._held: dict[str, bool] = {"ctrl": False, "shift": False, "alt": False, "cmd": False}

    def start(self) -> None:
        if sys.platform == "darwin":
            self._start_subprocess()
        else:
            self._start_in_process()

    def stop(self) -> None:
        if self._proc is not None:
            self._stop_subprocess()
            return
        listener = self._listener
        if listener is None:
            return
        listener.stop()
        if listener.is_alive():
            with contextlib.suppress(RuntimeError):
                listener.join(timeout=2.0)
        self._listener = None

    # --- subprocess (macOS) ------------------------------------------------
    def _start_subprocess(self) -> None:
        proc = subprocess.Popen(
            [sys.executable, "-m", "agentic_launcher._hotkey_subprocess", self._spec.pretty.lower()],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            bufsize=1,
        )
        self._proc = proc
        self._reader = threading.Thread(target=self._read_subprocess, args=(proc,), name="hotkey-reader", daemon=True)
        self._reader.start()

    def _read_subprocess(self, proc: subprocess.Popen[str]) -> None:
        stdout = proc.stdout
        if stdout is None:
            return
        try:
            for line in stdout:
                if line.strip() == "FIRE":
                    self._fire()
        except Exception:
            pass

    def _stop_subprocess(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
            except (OSError, subprocess.TimeoutExpired):
                with contextlib.suppress(OSError):
                    proc.kill()
        reader = self._reader
        self._reader = None
        if reader is not None and reader.is_alive():
            reader.join(timeout=1.0)

    # --- in-process (Linux / Windows) --------------------------------------
    def _start_in_process(self) -> None:
        from pynput import keyboard

        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.daemon = True
        self._listener.start()

    @staticmethod
    def _modifier_for_key(key: object) -> str | None:
        for mod in ("ctrl", "shift", "alt", "cmd"):
            if key in hk.modifier_keys(mod):
                return mod
        return None

    def _on_press(self, key: object) -> None:
        mod = self._modifier_for_key(key)
        if mod is not None:
            self._held[mod] = True
            return
        active = {name for name, value in self._held.items() if value}
        if active == self._spec.modifiers and self._spec.matches_key(key):
            self._fire()

    def _on_release(self, key: object) -> None:
        mod = self._modifier_for_key(key)
        if mod is not None:
            self._held[mod] = False

    def _fire(self) -> None:
        try:
            self._callback()
        except Exception as exc:  # noqa: BLE001 - a bad callback must not kill the listener
            sys.stderr.write(f"[agentic-stack] hotkey callback error: {exc!r}\n")
            sys.stderr.flush()


class TrayApp:
    """The tray icon, its menu, and the periodic stack refresh."""

    def __init__(self, client: StackClient, stack_url: str, hotkey_label: str | None = None) -> None:
        self._client = client
        self._stack_url = stack_url
        self._hotkey_label = hotkey_label
        self._entries: list[dict] = []
        self._icon: pystray.Icon | None = None
        self._listener: HotkeyListener | None = None
        self._stop = threading.Event()

    # --- state -------------------------------------------------------------
    def _current_title(self) -> str:
        if self._entries:
            task = self._entries[0].get("task") or {}
            return task.get("title") or "Untitled task"
        return "No tasks"

    def _menu(self) -> pystray.Menu:
        open_label = "Open Stack"
        if self._hotkey_label:
            open_label = f"Open Stack ({self._hotkey_label})"
        return pystray.Menu(
            pystray.MenuItem(self._current_title(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(open_label, self._on_open),
            pystray.MenuItem("Mark Done (pop)", self._on_pop, enabled=bool(self._entries)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )

    def _apply(self, entries: list[dict]) -> None:
        self._entries = entries
        icon = self._icon
        if icon is None:
            return
        image = make_icon(len(entries))
        title = self._current_title()
        menu = self._menu()

        def update() -> None:
            icon.icon = image
            icon.title = title
            icon.menu = menu

        _on_main(update)

    def refresh(self) -> None:
        try:
            entries = self._client.list_stack()
        except Exception:
            return
        self._apply(entries)

    # --- menu actions ------------------------------------------------------
    def _on_open(self, _icon: pystray.Icon | None = None, _item: pystray.MenuItem | None = None) -> None:
        webbrowser.open(self._stack_url)

    def _on_pop(self, _icon: pystray.Icon | None = None, _item: pystray.MenuItem | None = None) -> None:
        try:
            entries = self._client.pop_stack()
        except Exception as exc:  # noqa: BLE001 - keep the tray alive on API errors
            sys.stderr.write(f"[agentic-stack] could not pop: {exc!r}\n")
            sys.stderr.flush()
            return
        self._apply(entries)

    def _on_quit(self, _icon: pystray.Icon | None = None, _item: pystray.MenuItem | None = None) -> None:
        self.stop()

    # --- lifecycle ---------------------------------------------------------
    def run(self, spec: hk.HotkeySpec) -> None:
        self.refresh()
        self._icon = pystray.Icon(
            "agentic-stack",
            make_icon(len(self._entries)),
            title=self._current_title(),
            menu=self._menu(),
        )
        self._listener = HotkeyListener(self._on_open, spec)
        # pystray runs `setup` on a background thread once the icon loop starts.
        self._icon.run(setup=self._setup)

    def _setup(self, icon: pystray.Icon) -> None:
        icon.visible = True
        if self._listener is not None:
            self._listener.start()
        threading.Thread(target=self._poll, name="agentic-stack-poll", daemon=True).start()

    def _poll(self) -> None:
        while not self._stop.wait(POLL_SECONDS):
            self.refresh()

    def stop(self) -> None:
        """Stop the listener, the poll thread, and the icon (idempotent)."""
        self._stop.set()
        if self._listener is not None:
            self._listener.stop()
        if self._icon is not None:
            with contextlib.suppress(Exception):
                self._icon.stop()
