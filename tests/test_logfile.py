"""The log file never holds dictated text; permissions are reported in a fixed order."""

from __future__ import annotations

import logging

from diga import permissions
from diga.logfile import attach


def test_dictated_text_is_replaced_in_the_log_file(tmp_path):
    handler = attach(tmp_path / "diga.log")
    assert handler is not None
    try:
        log = logging.getLogger("diga.test")
        log.setLevel(logging.INFO)
        log.info("✓ chunk 1: «секретный текст»", extra={"redacted": "✓ chunk 1: «⋯»"})
        log.info("Ready.")
        handler.flush()
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()
    text = (tmp_path / "diga.log").read_text(encoding="utf-8")
    assert "секретный" not in text and "«⋯»" in text and "Ready." in text


def test_missing_reports_the_keyboard_first(monkeypatch):
    monkeypatch.setattr(permissions, "input_monitoring", lambda: False)
    monkeypatch.setattr(permissions, "can_post_events", lambda: False)
    monkeypatch.setattr(permissions, "microphone", lambda: False)
    assert permissions.missing() == "keyboard"
    monkeypatch.setattr(permissions, "input_monitoring", lambda: True)
    assert permissions.missing() == "typing"
    monkeypatch.setattr(permissions, "can_post_events", lambda: True)
    assert permissions.missing() == "microphone"
    monkeypatch.setattr(permissions, "microphone", lambda: None)  # not asked yet is not missing
    assert permissions.missing() is None
    assert set(permissions.SETTINGS_URL) == {"keyboard", "typing", "microphone"}
