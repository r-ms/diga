"""Start diga at login with a per-user LaunchAgent."""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

LABEL = "io.github.diga"
PLIST = Path("~/Library/LaunchAgents").expanduser() / f"{LABEL}.plist"
LOG = Path("~/Library/Logs/diga.log").expanduser()


def _program() -> list[str]:
    exe = shutil.which("diga")
    return [exe] if exe else [sys.executable, "-m", "diga"]


def install(extra_args: list[str] | None = None) -> Path:
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": LABEL,
        "ProgramArguments": [*_program(), *(extra_args or [])],
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},  # restart after a crash, not after Quit
        "ThrottleInterval": 30,
        "ProcessType": "Interactive",
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"},
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
    }
    uninstall(quiet=True)
    with PLIST.open("wb") as f:
        plistlib.dump(plist, f)
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(PLIST)], check=False)
    return PLIST


def uninstall(quiet: bool = False) -> bool:
    if not PLIST.exists():
        return False
    subprocess.run(
        ["launchctl", "bootout", f"gui/{os.getuid()}", str(PLIST)],
        check=False,
        capture_output=quiet,
    )
    PLIST.unlink()
    return True
