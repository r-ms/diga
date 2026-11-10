"""diga's own log file: always written, never with what you dictated.

``~/Library/Logs/diga/diga.log`` (1 MB, three old copies kept), whether diga runs in a terminal,
as a Homebrew service or at login. Menu → Show log opens it in Console; ``diga logs`` prints it.
Lines that carry dictated text are written with the text replaced by "⋯" (the recorder passes
the redacted version in the record's ``redacted`` attribute).
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILE = Path("~/Library/Logs/diga/diga.log").expanduser()


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        redacted = getattr(record, "redacted", None)
        if redacted is None:
            return super().format(record)
        clean = logging.makeLogRecord(record.__dict__)
        clean.msg, clean.args = redacted, ()
        return super().format(clean)


def attach(path: Path = LOG_FILE) -> logging.Handler | None:
    """Add the file handler to the root logger (INFO and up; debug lines may hold text)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    except OSError:
        return None  # a read-only home must not stop dictation
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        RedactingFormatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    logging.getLogger().addHandler(handler)
    return handler
