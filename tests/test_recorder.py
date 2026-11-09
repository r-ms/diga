"""Recorder without hardware: a scripted microphone and a fake recognizer."""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from diga.asr.base import Transcript
from diga.config import ChunkingConfig
from diga.recorder import Recorder

SR = 16_000
BLOCK = 512


class ScriptedMic:
    """Plays a given signal in 512-sample frames, then stays silent; counts openings."""

    def __init__(self, wave: np.ndarray) -> None:
        self.wave, self.pos, self.opened, self.is_open = wave, 0, 0, False

    def __call__(self) -> ScriptedMic:  # used as mic_factory
        return self

    def __enter__(self) -> ScriptedMic:
        self.opened += 1
        self.is_open = True
        return self

    def __exit__(self, *exc: object) -> None:
        self.is_open = False

    @property
    def done(self) -> bool:
        return self.pos >= len(self.wave)

    def read(self, timeout: float):
        if self.done:
            if timeout > 0:
                time.sleep(0.01)
            return None
        frame = self.wave[self.pos : self.pos + BLOCK]
        self.pos += BLOCK
        return frame


class FakeASR:
    name = "fake"

    def __init__(self) -> None:
        self.lengths: list[int] = []

    def transcribe(self, audio: np.ndarray) -> Transcript:
        self.lengths.append(len(audio))
        return Transcript(f"chunk{len(self.lengths)}")

    def warmup(self) -> None:
        pass


class FakeUI:
    def __init__(self) -> None:
        self.phases: list[str] = []

    def recording_state(self, phase: str) -> None:
        self.phases.append(phase)


def speech(seconds: float, rng: np.random.Generator) -> np.ndarray:
    return (0.3 * rng.standard_normal(int(seconds * SR))).astype(np.float32)


def silence(seconds: float) -> np.ndarray:
    return np.full(int(seconds * SR), 0.001, dtype=np.float32)


def wait_for(cond, timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end and not cond():
        time.sleep(0.01)
    return cond()


class Harness:
    def __init__(
        self, wave: np.ndarray, send_after_hold: bool = True, log_text: bool = True
    ) -> None:
        self.mic, self.asr, self.ui = ScriptedMic(wave), FakeASR(), FakeUI()
        self.typed: list[str] = []
        self.returns: list[list[str]] = []
        self.rec = Recorder(
            self.asr,
            self.typed.append,
            ui=self.ui,
            chunking=ChunkingConfig(min_chunk_s=10, max_chunk_s=20, pause_s=0.25, min_record_s=0.1),
            press_return=lambda: self.returns.append(list(self.typed)),
            send_after_hold=send_after_hold,
            log_text=log_text,
            mic_factory=self.mic,
        )
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.rec.run, args=(self.stop,), daemon=True)
        self.thread.start()

    def finish(self) -> None:
        assert wait_for(lambda: "idle" in self.ui.phases), self.ui.phases
        self.stop.set()
        self.thread.join(timeout=2)


@pytest.fixture
def rng():
    return np.random.default_rng(1)


def test_cuts_at_first_pause_after_10s_and_types_before_stop(rng):
    #        speech 6 s, pause (before the minimum: no cut), speech 6 s, pause, speech 5 s
    wave = np.concatenate(
        [speech(6, rng), silence(0.4), speech(6, rng), silence(0.4), speech(5, rng)]
    )
    h = Harness(wave)
    time.sleep(0.2)
    assert h.mic.opened == 0 and h.asr.lengths == []  # nothing before the press
    h.rec.toggle()
    assert wait_for(lambda: h.mic.done)
    assert wait_for(lambda: h.typed == ["chunk1"])  # typed while still recording
    assert h.mic.is_open
    h.rec.toggle()
    h.finish()
    first_pause_mid = (6 + 0.4 + 6 + 0.2) * SR
    assert len(h.asr.lengths) == 2
    assert 10 * SR <= h.asr.lengths[0] < 20 * SR
    assert abs(h.asr.lengths[0] - first_pause_mid) <= 0.25 * SR
    assert sum(h.asr.lengths) == len(wave)  # nothing lost
    assert h.typed == ["chunk1", "chunk2"]
    assert h.returns == []  # toggle recordings never press Return
    assert not h.mic.is_open and h.mic.opened == 1


def test_no_pause_forces_cut_at_20s(rng):
    wave = speech(45, rng)
    h = Harness(wave)
    h.rec.toggle()
    assert wait_for(lambda: h.mic.done)
    h.rec.toggle()
    h.finish()
    assert all(n <= 20 * SR for n in h.asr.lengths)
    assert all(n >= 10 * SR for n in h.asr.lengths[:-1])
    assert sum(h.asr.lengths) == len(wave)


def test_hold_types_then_presses_return_once(rng):
    h = Harness(speech(3, rng))
    h.rec.hold_start()
    assert wait_for(lambda: h.mic.done)
    h.rec.hold_end()
    h.finish()
    assert h.typed == ["chunk1"]
    assert h.returns == [["chunk1"]]  # once, after the text
    assert h.ui.phases == ["rec", "asr", "done", "idle"]  # "done": the success sound


def test_hold_cancelled_by_shortcut_types_nothing(rng):
    h = Harness(speech(3, rng))
    h.rec.hold_start()
    assert wait_for(lambda: h.mic.done)
    h.rec.hold_end(cancel=True)
    h.finish()
    assert h.typed == [] and h.returns == []


def test_return_can_be_switched_off(rng):
    h = Harness(speech(3, rng), send_after_hold=False)
    h.rec.hold_start()
    assert wait_for(lambda: h.mic.done)
    h.rec.hold_end()
    h.finish()
    assert h.typed == ["chunk1"] and h.returns == []


def test_hold_ignored_during_toggle_recording(rng):
    h = Harness(speech(3, rng))
    h.rec.toggle()
    assert wait_for(lambda: h.mic.is_open)
    h.rec.hold_start()  # ⌘ held while a long dictation runs: no effect
    h.rec.hold_end()
    assert h.mic.is_open
    assert wait_for(lambda: h.mic.done)
    h.rec.toggle()
    h.finish()
    assert h.returns == []


def test_dictated_text_can_be_kept_out_of_the_log(rng, caplog):
    caplog.set_level("INFO")
    h = Harness(np.concatenate([speech(2, rng), silence(0.5)]), log_text=False)
    h.rec.toggle()
    assert wait_for(lambda: h.mic.done)
    h.rec.toggle()
    h.finish()
    assert h.typed == ["chunk1"] and "chunk1" not in caplog.text


def test_an_empty_tail_chunk_is_not_logged(rng, caplog):
    caplog.set_level("INFO")
    h = Harness(np.concatenate([speech(2, rng), silence(0.5)]))
    h.asr.transcribe = lambda audio: Transcript("")  # type: ignore[method-assign]
    h.rec.toggle()
    assert wait_for(lambda: h.mic.done)
    h.rec.toggle()
    h.finish()
    assert "«»" not in caplog.text
