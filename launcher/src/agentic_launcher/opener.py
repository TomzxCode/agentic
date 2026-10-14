"""Open the stack page, preferring a browser app window over a browser tab.

A Chromium-based browser opens ``--app=<url>`` as a chromeless window (no tabs
or address bar), which is the closest a browser gets to a native window and
keeps the target URL. Set ``AGENTIC_STACK_OPEN`` to a shell command template
(with ``{url}``) to override this, for example ``open -a Agentic`` to launch the
installed PWA instead.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser

_MAC_APPS = (
    "/Applications/Google Chrome.app",
    "/Applications/Chromium.app",
    "/Applications/Microsoft Edge.app",
    "/Applications/Brave Browser.app",
    "/Applications/Vivaldi.app",
    os.path.expanduser("~/Applications/Google Chrome.app"),
    os.path.expanduser("~/Applications/Chromium.app"),
    os.path.expanduser("~/Applications/Microsoft Edge.app"),
)
_LINUX_BINARIES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
    "brave-browser",
)
_WINDOWS_BINARIES = ("chrome.exe", "msedge.exe", "brave.exe")


def app_mode_command(url: str) -> list[str] | None:
    """A command that opens ``url`` in a browser app window, or None if no
    Chromium-based browser is found."""
    if sys.platform == "darwin":
        for app in _MAC_APPS:
            if os.path.isdir(app):
                return ["open", "-na", app, "--args", f"--app={url}"]
    elif sys.platform == "win32":
        for name in _WINDOWS_BINARIES:
            binary = shutil.which(name)
            if binary:
                return [binary, f"--app={url}"]
    else:
        for name in _LINUX_BINARIES:
            binary = shutil.which(name)
            if binary:
                return [binary, f"--app={url}"]
    return None


def open_url(url: str, template: str | None = None) -> None:
    """Open ``url``, preferring an app window.

    ``template`` is a shell command with ``{url}`` substituted; when set it is
    used as-is. Otherwise a detected Chromium browser opens an app window, and
    if none is found the system default browser opens a normal tab.
    """
    if template:
        subprocess.Popen(template.replace("{url}", url), shell=True)
        return
    command = app_mode_command(url)
    if command is not None:
        try:
            subprocess.Popen(command)
            return
        except OSError:
            pass
    webbrowser.open(url)
