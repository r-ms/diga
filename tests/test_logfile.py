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
    monkeypatch.setattr(permissions, "accessibility", lambda: False)
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


def test_started_by_the_app_diga_names_itself(monkeypatch):
    monkeypatch.setenv("DIGA_APP", "1")
    assert permissions.host_app() == "diga"
    monkeypatch.delenv("DIGA_APP")
    monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")
    assert permissions.host_app() == "Terminal"


def test_diga_restarts_once_a_lacking_permission_is_granted_but_not_mid_dictation():
    from diga.app import newly_granted

    granted, lacked = newly_granted(set(), ["keyboard", "typing"], busy=False)
    assert granted == set() and lacked == {"keyboard", "typing"}  # first look: nothing granted
    granted, lacked = newly_granted(lacked, ["typing"], busy=True)
    assert granted == set() and lacked == {"keyboard", "typing"}  # dictating: wait
    granted, lacked = newly_granted(lacked, ["typing"], busy=False)
    assert granted == {"keyboard"} and lacked == {"typing"}  # now: restart
    granted, _ = newly_granted({"keyboard"}, ["keyboard"], busy=False)
    assert granted == set()  # still lacking after a restart: no restart loop


def test_typing_is_allowed_with_either_macos_grant(monkeypatch):
    calls = {"CGPreflightPostEventAccess": False}
    monkeypatch.setattr(permissions, "_bool_fn", lambda lib, name: calls.get(name))
    monkeypatch.setattr(permissions, "accessibility", lambda: True)
    assert permissions.can_post_events() is True  # Accessibility alone is enough
    monkeypatch.setattr(permissions, "accessibility", lambda: False)
    assert permissions.can_post_events() is False
    calls["CGPreflightPostEventAccess"] = True
    assert permissions.can_post_events() is True


def test_accessibility_alone_is_enough_to_see_the_keyboard(monkeypatch):
    monkeypatch.setattr(permissions, "input_monitoring", lambda: False)  # the list is empty
    monkeypatch.setattr(permissions, "accessibility", lambda: True)
    monkeypatch.setattr(permissions, "can_post_events", lambda: True)
    monkeypatch.setattr(permissions, "microphone", lambda: True)
    assert permissions.missing() is None
    assert permissions.SETTINGS_URL["keyboard"].endswith("Privacy_Accessibility")
