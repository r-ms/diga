# pyright: reportAttributeAccessIssue=false
# (PyObjC exposes macOS framework symbols dynamically, so static checkers cannot see them.)
"""macOS permission checks behind `diga doctor`, plus a Secure Keyboard Entry note.

Permissions belong to the app that *hosts* diga — your terminal (iTerm2, Terminal) when you
run it from a shell, or Python itself when it runs as a login item.
"""

from __future__ import annotations

import ctypes
import os
import re
import subprocess
from dataclasses import dataclass

_AX = "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
_CG = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
_SECURE_PID = re.compile(rb'"kCGSSessionSecureInputPID"=(\d+)')


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool | None  # None: could not be determined
    detail: str = ""


def _bool_fn(lib: str, name: str) -> bool | None:
    try:
        fn = getattr(ctypes.cdll.LoadLibrary(lib), name)
        fn.restype = ctypes.c_bool
        return bool(fn())
    except (OSError, AttributeError):
        return None


def accessibility() -> bool | None:
    return _bool_fn(_AX, "AXIsProcessTrusted")


def input_monitoring() -> bool | None:
    return _bool_fn(_CG, "CGPreflightListenEventAccess")


def can_post_events() -> bool | None:
    """Whether this process may send key events to other apps.

    macOS has two grants that allow it — "post events" and Accessibility — and typing works with
    either. Checking only the first gave a false "can't type" warning on Macs where diga (or the
    terminal) had Accessibility but no separate post-events entry.
    """
    post = _bool_fn(_CG, "CGPreflightPostEventAccess")
    if post:
        return True
    trusted = accessibility()
    if trusted:
        return True
    return False if (post is False or trusted is False) else None


# System Settings → Privacy & Security panes, opened from the menu warning. For the keyboard it is
# Accessibility, not Input Monitoring: Accessibility also lets an app see the keys (a terminal
# with Accessibility sees them while the Input Monitoring list is empty), it is the one pane
# macOS adds a background app to when it asks, and it is needed for typing anyway.
SETTINGS_URL = {
    "keyboard": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    "typing": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    "microphone": "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
}


def request_all() -> None:
    """Ask macOS for everything diga needs up front, so the prompts appear at start and not in
    the middle of the first dictation. Each prompt is shown once; after that these are no-ops."""
    _bool_fn(_CG, "CGRequestListenEventAccess")  # Input Monitoring: see the hotkey
    _bool_fn(_CG, "CGRequestPostEventAccess")  # Accessibility: type into other apps
    try:
        from AVFoundation import (  # type: ignore[import-not-found]
            AVCaptureDevice,
            AVMediaTypeAudio,
        )

        if int(AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)) == 0:
            AVCaptureDevice.requestAccessForMediaType_completionHandler_(
                AVMediaTypeAudio, lambda granted: None
            )
    except Exception:
        pass


def missing_all() -> list[str]:
    """Everything diga is not allowed to do, most important first."""
    out = []
    if input_monitoring() is False and accessibility() is not True:
        out.append("keyboard")
    if can_post_events() is False:
        out.append("typing")
    if microphone() is False:
        out.append("microphone")
    return out


def missing() -> str | None:
    """The first thing diga is not allowed to do: "keyboard", "typing", "microphone" — or None."""
    gaps = missing_all()
    return gaps[0] if gaps else None


def microphone() -> bool | None:
    """True granted, False denied/restricted, None not asked yet (or unknown)."""
    try:
        from AVFoundation import (  # type: ignore[import-not-found]
            AVCaptureDevice,
            AVMediaTypeAudio,
        )
    except ImportError:
        return None
    status = int(AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio))
    return {3: True, 1: False, 2: False}.get(status)  # 0 = not determined


def secure_input_holder() -> tuple[int, str] | None:
    """(pid, app name) of the process that turned on Secure Keyboard Entry, if any.

    Informational only: it hides key presses from other apps, but in our tests diga kept typing
    while iTerm2 or the macOS login window held it.
    """
    try:
        out = subprocess.run(
            ["ioreg", "-l", "-w", "0", "-d", "1"], capture_output=True, timeout=2, check=False
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = _SECURE_PID.search(out)
    if not m:
        return None
    pid = int(m.group(1))
    try:
        comm = subprocess.run(
            ["ps", "-o", "comm=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        comm = ""
    name = comm.split(".app/")[0].rsplit("/", 1)[-1] if ".app/" in comm else os.path.basename(comm)
    return pid, name or f"pid {pid}"


def host_app() -> str:
    """Best guess of the app the permissions must be granted to."""
    if os.environ.get("DIGA_APP"):  # started by diga.app (the Homebrew service)
        return "diga"
    term = os.environ.get("TERM_PROGRAM", "")
    return {
        "iTerm.app": "iTerm2",
        "Apple_Terminal": "Terminal",
        "vscode": "Visual Studio Code",
        "WarpTerminal": "Warp",
        "ghostty": "Ghostty",
    }.get(term, term or "Python")


def run_checks() -> list[Check]:
    host = host_app()
    privacy = "System Settings → Privacy & Security"
    checks = [
        Check("Microphone", microphone(), f"{privacy} → Microphone → enable {host}"),
        Check("Accessibility", accessibility(), f"{privacy} → Accessibility → enable {host}"),
        Check(
            "Input Monitoring", input_monitoring(), f"{privacy} → Input Monitoring → enable {host}"
        ),
    ]
    checks.append(
        Check(
            "Typing into other apps",
            can_post_events(),
            f"{privacy} → Accessibility → enable {host}, then restart diga",
        )
    )
    holder = secure_input_holder()
    if holder:  # informational only (ok=None prints "?"), never a failure
        checks.append(
            Check("Secure Keyboard Entry", None, f"on in {holder[1]} — usually harmless for diga")
        )
    return checks
