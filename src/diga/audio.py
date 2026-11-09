"""Microphone capture: 16 kHz mono float32 frames.

The stream is opened only for the duration of a recording (see ``Recorder``), so the
microphone is closed — and the macOS orange dot is off — whenever you are not dictating.
"""

from __future__ import annotations

import logging
import queue

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
BLOCK = 512  # frames per callback (32 ms)


class Microphone:
    """Context manager around a sounddevice input stream; ``read()`` pulls queued frames."""

    def __init__(self, sample_rate: int = SAMPLE_RATE, block: int = BLOCK) -> None:
        self.sample_rate = sample_rate
        self.block = block
        self._q: queue.Queue[np.ndarray] = queue.Queue()
        self._stream = None

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            log.debug("mic status: %s", status)
        self._q.put(indata[:, 0].copy())

    def __enter__(self) -> Microphone:
        import sounddevice as sd

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.block,
            callback=self._callback,
        )
        self._stream.start()
        log.debug("mic open: %d Hz, block %d", self.sample_rate, self.block)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def read(self, timeout: float) -> np.ndarray | None:
        """Next frame, or None if nothing arrived within ``timeout`` (``<= 0``: don't wait)."""
        try:
            return self._q.get_nowait() if timeout <= 0 else self._q.get(timeout=timeout)
        except queue.Empty:
            return None
