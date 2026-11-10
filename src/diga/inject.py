# pyright: reportAttributeAccessIssue=false
# (PyObjC exposes macOS framework symbols dynamically, so static checkers cannot see them.)
"""Typing text into the focused app with synthesized Unicode key events.

Unlike paste-based tools, this never touches the clipboard and works in terminals and other
apps where ⌘V behaves differently. Every character is sent as a keyboard event carrying the
Unicode string, independent of the keyboard layout. Modifier flags are cleared explicitly,
so a character typed while you still hold ⌘ never turns into a shortcut (⌘W, ⌘Q…).

Every event carries ``INJECTED_EVENT_MARK`` in its source user-data field, so diga's own
hotkey listener can tell them apart from real key presses: while you hold ⌘ to dictate, a
chunk typed by diga must not look like "⌘ + another key" and cancel the recording.
"""

from __future__ import annotations

import time

RETURN_KEYCODE = 36
# Return must arrive on its own. Typed right after the last piece of text, a terminal can hand
# both to the app in one read, and Claude Code takes multi-character input as a paste, in which
# Return is a new line — the prompt was not sent.
RETURN_DELAY_S = 0.12
INJECTED_EVENT_MARK = 0x64696761  # "diga"
# One key event can carry up to 20 UTF-16 code units. Typing a letter per event (with the pause
# apps need between events) took ~0.8 s for a 250-character chunk; pieces make it ~20x faster.
MAX_UNITS_PER_EVENT = 20


def pieces(text: str, max_units: int = MAX_UNITS_PER_EVENT) -> list[str]:
    """Split ``text`` into runs of at most ``max_units`` UTF-16 code units, never inside a
    character (emoji and other astral characters take two units)."""
    out: list[str] = []
    current, units = "", 0
    for ch in text:
        n = 2 if ord(ch) > 0xFFFF else 1
        if units + n > max_units:
            out.append(current)
            current, units = "", 0
        current += ch
        units += n
    if current:
        out.append(current)
    return out


class KeystrokeTyper:
    def __init__(self, event_delay_s: float = 0.003, max_units: int = MAX_UNITS_PER_EVENT) -> None:
        from Quartz import CGEventSourceCreate, kCGEventSourceStateHIDSystemState

        self._source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
        self._delay = event_delay_s
        self._units = max_units

    def type_text(self, text: str, trailing_space: bool = True) -> None:
        from Quartz import CGEventKeyboardSetUnicodeString

        if trailing_space:
            text += " "
        for piece in pieces(text, self._units):
            units = len(piece.encode("utf-16-le")) // 2
            for down in (True, False):
                event = self._event(0, down)
                CGEventKeyboardSetUnicodeString(event, units, piece)
                self._post(event)
            if self._delay:
                time.sleep(self._delay)

    def press_return(self) -> None:
        time.sleep(RETURN_DELAY_S)
        for down in (True, False):
            self._post(self._event(RETURN_KEYCODE, down))

    def _event(self, keycode: int, down: bool):
        from Quartz import (
            CGEventCreateKeyboardEvent,
            CGEventSetFlags,
            CGEventSetIntegerValueField,
            kCGEventSourceUserData,
        )

        event = CGEventCreateKeyboardEvent(self._source, keycode, down)
        CGEventSetFlags(event, 0)
        CGEventSetIntegerValueField(event, kCGEventSourceUserData, INJECTED_EVENT_MARK)
        return event

    @staticmethod
    def _post(event) -> None:
        from Quartz import CGEventPost, kCGHIDEventTap

        CGEventPost(kCGHIDEventTap, event)
