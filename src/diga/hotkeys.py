# pyright: reportAttributeAccessIssue=false
# (PyObjC exposes macOS framework symbols dynamically, so static checkers cannot see them.)
"""Global hotkeys on one modifier key — right ⌘ by default — via a listen-only CGEventTap.

* **hold** the key longer than ``hold_s`` → ``on_hold_start()``; release → ``on_hold_end(cancel)``.
  If another key is pressed while it is down, it was a shortcut (⌘C, ⌘Tab…): ``cancel=True``.
* **double-tap** the key within ``double_tap_s`` → ``on_toggle()``. A tap is a press and
  release with no other key in between and shorter than the hold threshold.

Keys (``KEYS``): right ⌘ (rarely used, on every Mac keyboard), right ⌥, and Fn/🌐 (not on
every external keyboard; macOS may also use it for emoji or its own dictation). Left ⌘ is
deliberately not offered: ⌘-click and ⌘-drag press no other key, so they would start
recordings that cannot be told apart from dictation.

Requires the Accessibility / Input Monitoring permission for the hosting process. The event
tap is attached to the main run loop (the menu-bar app runs it).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from .inject import INJECTED_EVENT_MARK

log = logging.getLogger(__name__)

RIGHT_CMD_MASK = 0x10  # NX_DEVICERCMDKEYMASK
RIGHT_OPTION_MASK = 0x40  # NX_DEVICERALTKEYMASK
FN_MASK = 0x800000  # kCGEventFlagMaskSecondaryFn
KEYS = {"right_cmd": RIGHT_CMD_MASK, "right_option": RIGHT_OPTION_MASK, "fn": FN_MASK}
DEFAULT_KEY = "right_cmd"


class HotkeyManager:
    def __init__(
        self,
        hold_s: float = 0.3,
        double_tap_s: float = 0.4,
        timer_factory: Callable[..., Any] = threading.Timer,
        key: str = DEFAULT_KEY,
    ) -> None:
        self._mask = KEYS.get(key, RIGHT_CMD_MASK)
        self._hold_s = hold_s
        self._double_tap_s = double_tap_s
        self._timer_factory = timer_factory
        self._on_toggle: Callable[[], None] | None = None
        self._on_hold_start: Callable[[], None] | None = None
        self._on_hold_end: Callable[[bool], None] | None = None
        self._lock = threading.Lock()  # the hold timer fires on its own thread
        self._down = False
        self._used = False  # another key was pressed while ours was down
        self._holding = False
        self._hold_timer: Any = None
        self._last_tap = float("-inf")
        self._tap = None

    def bind(
        self,
        *,
        toggle: Callable[[], None] | None = None,
        hold_start: Callable[[], None] | None = None,
        hold_end: Callable[[bool], None] | None = None,
    ) -> None:
        if toggle is not None:
            self._on_toggle = toggle
        if hold_start is not None:
            self._on_hold_start = hold_start
        if hold_end is not None:
            self._on_hold_end = hold_end

    def set_key(self, key: str) -> None:
        """Switch to another key (from the menu); a press in progress is forgotten."""
        with self._lock:
            self._mask = KEYS[key]
            self._cancel_timer()
            self._down = self._used = self._holding = False
            self._last_tap = float("-inf")

    # --- pure logic, driven by the event tap (and by tests) ---

    def _cancel_timer(self) -> None:
        if self._hold_timer is not None:
            self._hold_timer.cancel()
            self._hold_timer = None

    def _hold_fired(self) -> None:
        with self._lock:
            self._hold_timer = None
            if not self._down or self._used:
                return
            self._holding = True
        if self._on_hold_start:
            self._on_hold_start()

    def on_key_down(self, source_user_data: int = 0) -> None:
        if source_user_data == INJECTED_EVENT_MARK:
            return  # diga typing a chunk while you hold the key is not "key + another key"
        end: bool | None = None
        with self._lock:
            if self._down:
                self._used = True
                self._cancel_timer()
                if self._holding:
                    self._holding = False
                    end = True  # key + another key while recording: it was a shortcut
        if end is not None and self._on_hold_end:
            self._on_hold_end(end)

    def on_flags(self, flags: int, now: float) -> None:
        down = bool(flags & self._mask)
        end: bool | None = None
        tap = False
        with self._lock:
            if down and not self._down:
                self._down, self._used = True, False
                if self._on_hold_start:
                    self._cancel_timer()
                    self._hold_timer = self._timer_factory(self._hold_s, self._hold_fired)
                    self._hold_timer.daemon = True
                    self._hold_timer.start()
            elif not down and self._down:
                self._down = False
                self._cancel_timer()
                if self._holding:
                    self._holding = False
                    end = self._used
                elif not self._used:
                    tap = True
        if end is not None and self._on_hold_end:
            self._on_hold_end(end)
        if tap:
            self._tapped(now)

    def _tapped(self, now: float) -> None:
        if now - self._last_tap <= self._double_tap_s:
            self._last_tap = float("-inf")
            if self._on_toggle:
                self._on_toggle()
        else:
            self._last_tap = now

    # --- CGEventTap ---

    def _callback(self, proxy, type_, event, refcon):
        from Quartz import (
            CGEventGetFlags,
            CGEventGetIntegerValueField,
            CGEventTapEnable,
            kCGEventKeyDown,
            kCGEventSourceUserData,
            kCGEventTapDisabledByTimeout,
            kCGEventTapDisabledByUserInput,
        )

        if type_ in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
            CGEventTapEnable(self._tap, True)
        elif type_ == kCGEventKeyDown:
            self.on_key_down(int(CGEventGetIntegerValueField(event, kCGEventSourceUserData)))
        else:  # kCGEventFlagsChanged
            self.on_flags(CGEventGetFlags(event), time.monotonic())
        return event

    @property
    def started(self) -> bool:
        return self._tap is not None

    def start(self) -> bool:
        """Install the event tap on the main run loop; False without the permission.

        Safe to call again (the app retries until Input Monitoring is granted)."""
        if self._tap is not None:
            return True
        from Quartz import (
            CFMachPortCreateRunLoopSource,
            CFRunLoopAddSource,
            CFRunLoopGetMain,
            CGEventMaskBit,
            CGEventTapCreate,
            CGEventTapEnable,
            kCFRunLoopCommonModes,
            kCGEventFlagsChanged,
            kCGEventKeyDown,
            kCGEventTapOptionListenOnly,
            kCGHeadInsertEventTap,
            kCGSessionEventTap,
        )

        mask = CGEventMaskBit(kCGEventFlagsChanged) | CGEventMaskBit(kCGEventKeyDown)
        self._tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly,
            mask,
            self._callback,
            None,
        )
        if not self._tap:
            self._tap = None
            return False
        source = CFMachPortCreateRunLoopSource(None, self._tap, 0)
        CFRunLoopAddSource(CFRunLoopGetMain(), source, kCFRunLoopCommonModes)
        CGEventTapEnable(self._tap, True)
        return True
