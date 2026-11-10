"""Push-to-talk recording: the microphone is open only while you dictate.

Two ways to record:

* **hold** right ⌘ — release to stop; the text is typed and (optionally) Return is pressed;
* **toggle** — double-tap right ⌘ (or click the menu) to start and again to stop.

While recording, audio is cut into chunks (see ``chunking``); each chunk is recognized on a
background thread and typed into the focused app right away, so a long dictation appears
piece by piece. After the stop only the last chunk is left to recognize. Nothing is
recorded or recognized outside a recording.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from typing import Protocol

import numpy as np

from .asr.base import Transcriber
from .audio import BLOCK, SAMPLE_RATE, Microphone
from .chunking import find_pause, frame_rms, quiet_cut, reframe
from .config import ChunkingConfig
from .i18n import t
from .terms import Corrector, prefetch

log = logging.getLogger(__name__)


class MicrophoneLike(Protocol):
    def __enter__(self) -> MicrophoneLike: ...

    def __exit__(self, *exc: object) -> None: ...

    def read(self, timeout: float) -> np.ndarray | None: ...


class RecorderUI(Protocol):
    def recording_state(self, phase: str) -> None:
        """``rec`` (recording), ``asr`` (finishing), ``idle``."""


class _ChunkWorker:
    """Recognizes chunks in order on a background thread and types each result at once."""

    def __init__(
        self,
        recognize: Callable[[np.ndarray], str],
        deliver: Callable[[str], None],
        log_text: bool = True,
    ) -> None:
        self._recognize = recognize
        self._deliver = deliver
        self._log_text = log_text
        self._q: queue.Queue[np.ndarray | None] = queue.Queue()
        self._texts: list[str] = []
        self._thread = threading.Thread(target=self._loop, name="diga-asr", daemon=True)
        self._thread.start()

    def submit(self, chunk: np.ndarray) -> None:
        self._q.put(chunk)

    def _loop(self) -> None:
        while (chunk := self._q.get()) is not None:
            t0 = time.monotonic()
            try:
                text = self._recognize(chunk)
                self._texts.append(text)
                fields = {"i": len(self._texts), "audio": len(chunk) / SAMPLE_RATE}
                fields["asr"] = time.monotonic() - t0
                log.log(
                    logging.INFO if text else logging.DEBUG,  # an empty tail is just noise
                    t("status.chunk", **fields, text=text if self._log_text else "⋯"),
                    extra={"redacted": t("status.chunk", **fields, text="⋯")},  # for the log file
                )
                if text:
                    self._deliver(text)
            except Exception:  # one bad chunk must not lose the others
                log.exception("chunk failed — skipped")

    def finish(self, stop: threading.Event) -> list[str]:
        """Wait for every submitted chunk; texts in recording order."""
        self._q.put(None)
        while self._thread.is_alive() and not stop.is_set():
            self._thread.join(0.1)
        return list(self._texts)


class Recorder:
    def __init__(
        self,
        transcriber: Transcriber,
        type_text: Callable[[str], None],
        *,
        corrector: Corrector | None = None,
        ui: RecorderUI | None = None,
        chunking: ChunkingConfig | None = None,
        press_return: Callable[[], None] | None = None,
        send_after_hold: bool = True,
        log_text: bool = True,
        mic_factory: Callable[[], MicrophoneLike] = Microphone,
    ) -> None:
        c = chunking or ChunkingConfig()
        self.transcriber = transcriber
        self.corrector = corrector
        self._type_text = type_text
        self._press_return = press_return
        self._send_after_hold = send_after_hold
        self._log_text = log_text  # False: the log may end up in a file; keep dictation out
        self._ui = ui
        self._max_n = int(c.max_chunk_s * SAMPLE_RATE)
        self._min_n = min(int(c.min_chunk_s * SAMPLE_RATE), self._max_n)
        self._pause_frames = max(1, round(c.pause_s * SAMPLE_RATE / BLOCK))
        self._max_record_s = c.max_record_s
        self._min_record_s = c.min_record_s
        self._mic_factory = mic_factory
        self._lock = threading.Lock()
        self._want = False  # the user wants a recording to be running
        self._hold = False  # the current / pending recording was started by holding ⌘
        self._discard = False  # the hold turned out to be a shortcut (⌘ + key): type nothing
        self._wake = threading.Event()

    # --- called from the hotkey / menu / stdin thread: never blocks ---

    def toggle(self) -> None:
        with self._lock:
            self._want = not self._want
        self._wake.set()

    def hold_start(self) -> None:
        """Right ⌘ held past the threshold. Ignored if a toggle recording is running."""
        with self._lock:
            if self._want:
                return
            self._want, self._hold, self._discard = True, True, False
        self._wake.set()

    def hold_end(self, cancel: bool = False) -> None:
        """Right ⌘ released; ``cancel`` — another key was pressed meanwhile (a shortcut)."""
        with self._lock:
            if not self._hold:
                return
            self._want = False
            if cancel:
                self._discard = True
        self._wake.set()

    @property
    def recording(self) -> bool:
        with self._lock:
            return self._want

    # --- worker thread ---

    def run(self, stop: threading.Event) -> None:
        """Serve recordings until ``stop`` is set."""
        while not stop.is_set():
            if not self._wake.wait(0.2):
                continue
            self._wake.clear()
            if self._wanted():
                self._session(stop)
            else:  # the hold was released before the recording could start
                self._reset_hold()

    def _wanted(self) -> bool:
        with self._lock:
            return self._want

    def _reset_hold(self) -> None:
        with self._lock:
            if not self._want:
                self._hold = self._discard = False

    def _recognize(self, chunk: np.ndarray) -> str:
        with self._lock:
            transcriber, corrector = self.transcriber, self.corrector
        if corrector is not None:
            prefetch(corrector, chunk)  # e.g. the acoustic spotter's model, in parallel
        transcript = transcriber.transcribe(chunk)
        text = transcript.text
        if corrector is not None and text:
            try:  # fail open: a correction error must not lose the dictation
                text = corrector.correct(chunk, transcript)
            except Exception as e:
                log.warning("term correction failed, keeping the raw text: %s", e)
        return text.strip()

    def _session(self, stop: threading.Event) -> None:
        with self._lock:
            hold = self._hold
        typed: list[str] = []

        def deliver(text: str) -> None:
            with self._lock:
                if self._discard:
                    return
            self._type_text(text)
            typed.append(text)

        try:
            if self._ui:
                self._ui.recording_state("rec")
            log.info(t("status.recording_hold" if hold else "status.recording_toggle"))
            worker = _ChunkWorker(self._recognize, deliver, self._log_text)
            total_n = self._record(stop, worker)
            t_stop = time.monotonic()
            if self._ui:
                self._ui.recording_state("asr")
            log.info(t("status.stopped"))
            texts = worker.finish(stop)
            if stop.is_set():
                return
            with self._lock:
                discard, send = self._discard, self._send_after_hold
            if discard:
                log.info(t("status.cancelled"))
                return
            seconds = total_n / SAMPLE_RATE
            if seconds < self._min_record_s:
                log.info(t("status.too_short"))
                return
            if not any(texts):
                log.info(t("status.nothing"))
            log.info(
                t("status.done", audio=seconds, chunks=len(texts), after=time.monotonic() - t_stop)
            )
            if hold and send and typed and self._press_return:
                self._press_return()  # only if something was actually typed
                log.info(t("status.sent"))
            if typed and self._ui:
                self._ui.recording_state("done")  # the success sound: the text is in place
        except Exception:
            log.exception("recording failed")
        finally:
            self._reset_hold()
            if self._ui:
                self._ui.recording_state("idle")

    def _record(self, stop: threading.Event, worker: _ChunkWorker) -> int:
        """Record until stopped, handing chunks to ``worker``; returns the sample count."""
        frames: list[np.ndarray] = []
        rms: list[float] = []
        pending_n = total_n = 0
        cap = int(self._max_record_s * SAMPLE_RATE)
        with self._mic_factory() as mic:
            while self._wanted() and not stop.is_set():
                f = mic.read(0.1)
                if f is None:
                    continue
                frames.append(f)
                rms.append(frame_rms(f))
                pending_n += len(f)
                total_n += len(f)
                if pending_n >= self._min_n:
                    j = find_pause(rms, self._pause_frames)
                    if j is not None:  # a pause after the minimum: cut in its middle
                        worker.submit(np.concatenate(frames[:j]))
                        frames, rms = frames[j:], rms[j:]
                        pending_n = sum(len(x) for x in frames)
                if pending_n >= self._max_n:  # no pause: cut at the quietest spot
                    wave = np.concatenate(frames)
                    cut = quiet_cut(wave, self._min_n, self._max_n)
                    worker.submit(wave[:cut])
                    frames, rms = reframe(wave[cut:])
                    pending_n = len(wave) - cut
                if total_n >= cap:
                    log.info(t("status.limit", seconds=self._max_record_s))
                    with self._lock:
                        self._want = False
                    break
            while (f := mic.read(0)) is not None:  # whatever arrived before the stream closed
                frames.append(f)
                pending_n += len(f)
                total_n += len(f)
        if pending_n and total_n >= int(self._min_record_s * SAMPLE_RATE):
            worker.submit(np.concatenate(frames))  # the tail
        return total_n
