"""Hotkey logic with a fake timer the test fires by hand."""

from __future__ import annotations

from diga.hotkeys import RIGHT_CMD_MASK, HotkeyManager

DOWN, UP = RIGHT_CMD_MASK, 0


class FakeTimer:
    last: FakeTimer | None = None

    def __init__(self, delay: float, fn) -> None:
        self.fn, self.cancelled, self.daemon = fn, False, False
        FakeTimer.last = self

    def start(self) -> None:
        pass

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        if not self.cancelled:
            self.fn()


def last_timer() -> FakeTimer:
    assert FakeTimer.last is not None
    return FakeTimer.last


def make() -> tuple[HotkeyManager, list[str]]:
    events: list[str] = []
    hk = HotkeyManager(timer_factory=FakeTimer)
    hk.bind(
        toggle=lambda: events.append("toggle"),
        hold_start=lambda: events.append("hold_start"),
        hold_end=lambda cancel: events.append(f"hold_end(cancel={cancel})"),
    )
    return hk, events


def test_long_hold_starts_and_release_ends():
    hk, ev = make()
    hk.on_flags(DOWN, 0.0)
    last_timer().fire()
    hk.on_flags(UP, 1.5)
    assert ev == ["hold_start", "hold_end(cancel=False)"]


def test_short_taps_are_not_a_hold_and_double_tap_toggles():
    hk, ev = make()
    hk.on_flags(DOWN, 0.0)
    hk.on_flags(UP, 0.1)
    assert last_timer().cancelled
    hk.on_flags(DOWN, 0.2)
    hk.on_flags(UP, 0.3)
    assert ev == ["toggle"]


def test_slow_taps_do_not_toggle():
    hk, ev = make()
    hk.on_flags(DOWN, 0.0)
    hk.on_flags(UP, 0.1)
    hk.on_flags(DOWN, 1.0)
    hk.on_flags(UP, 1.1)
    assert ev == []


def test_quick_shortcut_never_starts_recording():
    hk, ev = make()
    hk.on_flags(DOWN, 0.0)
    hk.on_key_down()  # ⌘C before the hold threshold
    last_timer().fire()
    hk.on_flags(UP, 0.5)
    assert ev == []


def test_shortcut_during_hold_cancels():
    hk, ev = make()
    hk.on_flags(DOWN, 0.0)
    last_timer().fire()
    hk.on_key_down()  # then ⌘Tab / ⌘V: it was a shortcut after all
    hk.on_flags(UP, 2.0)
    assert ev == ["hold_start", "hold_end(cancel=True)"]


def test_without_hold_binding_no_timer_is_started():
    hk = HotkeyManager(timer_factory=FakeTimer)
    FakeTimer.last = None
    hk.on_flags(DOWN, 0.0)
    hk.on_flags(UP, 1.0)
    assert FakeTimer.last is None


def test_diga_typing_a_chunk_during_hold_does_not_cancel():
    # Regression: the first chunk (typed by diga after ~10–15 s) looked like "⌘ + another key"
    # and stopped long hold-to-talk dictations.
    from diga.inject import INJECTED_EVENT_MARK

    hk, ev = make()
    hk.on_flags(DOWN, 0.0)
    last_timer().fire()
    for _ in range(20):  # diga types "chunk1 " while ⌘ is still held
        hk.on_key_down(INJECTED_EVENT_MARK)
    hk.on_flags(UP, 30.0)
    assert ev == ["hold_start", "hold_end(cancel=False)"]


def test_real_key_during_hold_still_cancels():
    hk, ev = make()
    hk.on_flags(DOWN, 0.0)
    last_timer().fire()
    hk.on_key_down(0)  # a key from the keyboard
    assert ev == ["hold_start", "hold_end(cancel=True)"]


def test_other_keys_can_be_chosen_and_right_cmd_then_does_nothing():
    from diga.hotkeys import FN_MASK, RIGHT_OPTION_MASK

    for key, mask in (("right_option", RIGHT_OPTION_MASK), ("fn", FN_MASK)):
        events: list[str] = []
        hk = HotkeyManager(timer_factory=FakeTimer, key=key)
        hk.bind(
            hold_start=lambda e=events: e.append("hold_start"),
            hold_end=lambda cancel, e=events: e.append(f"hold_end(cancel={cancel})"),
        )
        hk.on_flags(RIGHT_CMD_MASK, 0.0)  # right ⌘ is no longer the dictation key
        assert FakeTimer.last is None or FakeTimer.last.cancelled or events == []
        hk.on_flags(0, 0.1)
        hk.on_flags(mask, 1.0)
        last_timer().fire()
        hk.on_flags(0, 2.0)
        assert events == ["hold_start", "hold_end(cancel=False)"], key


def test_switching_the_key_forgets_a_press_in_progress():
    hk, events = make()
    hk.on_flags(DOWN, 0.0)
    hk.set_key("fn")
    last_timer().fire()  # the old key's hold timer was cancelled
    hk.on_flags(UP, 0.5)
    assert events == []
