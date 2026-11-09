"""Sound sets: a sound when recording starts and one once the text is typed.

The built-in sets live in ``data/sounds/<set>/`` (made by ``scripts/make_sounds.py``). Pick one
in the menu, or point ``sounds`` in ``config.yaml`` at a folder of your own with ``start.wav``
and/or ``done.wav``; a missing file means silence for that moment. ``off`` is silence.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

BUILT_IN = Path(__file__).parent / "data" / "sounds"
SETS = ("soft", "tick", "drop", "chime")  # menu order; the first is the default
DEFAULT = SETS[0]
OFF = "off"


@dataclass(frozen=True)
class Sounds:
    start: Path | None = None
    done: Path | None = None


def resolve(choice: str) -> Sounds:
    """The files for a set name, ``off`` or a folder; unknown choices fall back to the default."""
    if choice == OFF:
        return Sounds()
    folder = BUILT_IN / choice if choice in SETS else Path(choice).expanduser()
    if not folder.is_dir():
        log.warning("sound set %r not found, using %r", choice, DEFAULT)
        folder = BUILT_IN / DEFAULT
    start, done = folder / "start.wav", folder / "done.wav"
    return Sounds(start if start.is_file() else None, done if done.is_file() else None)


def play(path: Path | None) -> None:
    if path is None or not path.is_file():  # e.g. a file of your own that was removed
        return
    try:
        subprocess.Popen(
            ["afplay", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except OSError as e:
        log.debug("afplay failed: %s", e)
