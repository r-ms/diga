"""Where to cut a live recording into chunks — by frame energy, without a VAD model.

* Once a chunk has ``min_chunk_s`` of audio and its tail is a pause of ``pause_s``, cut in
  the middle of that pause (``find_pause``).
* If no pause comes before ``max_chunk_s``, cut at the quietest 20 ms frame of the
  ``min_chunk_s…max_chunk_s`` window (``quiet_cut``), so a word is rarely split in half.

Chunks stay under 25 s because the ASR models we use do not accept longer clips.
"""

from __future__ import annotations

import numpy as np

from .audio import BLOCK

FRAME = 320  # 20 ms at 16 kHz — resolution of the forced cut


def quiet_cut(wave: np.ndarray, min_n: int, max_n: int) -> int:
    """Sample index of the quietest 20 ms frame inside ``[min_n, max_n)``."""
    win = wave[min_n:max_n]
    k = len(win) // FRAME
    if k == 0:
        return min(max_n, len(wave))
    rms = np.sqrt((win[: k * FRAME].reshape(k, FRAME) ** 2).mean(axis=1))
    return min_n + int(np.argmin(rms)) * FRAME + FRAME // 2


def find_pause(rms: list[float], pause_frames: int) -> int | None:
    """Frame index to cut at (middle of the pause) if the last ``pause_frames`` are silent.

    The silence threshold is relative: 20% of the way from the quietest frame of the chunk
    (the pause itself always lands there) to the 90th-percentile "speech" level. Without
    enough contrast between the two we don't guess and return None.
    """
    if len(rms) < pause_frames:
        return None
    arr = np.asarray(rms, dtype=np.float64)
    floor, loud = float(arr.min()), float(np.percentile(arr, 90))
    if loud < 2 * floor + 1e-4:
        return None
    threshold = floor + 0.2 * (loud - floor)
    if (arr[-pause_frames:] < threshold).all():
        return len(arr) - pause_frames // 2
    return None


def frame_rms(frame: np.ndarray) -> float:
    return float(np.sqrt(np.mean(frame * frame))) if len(frame) else 0.0


def reframe(wave: np.ndarray) -> tuple[list[np.ndarray], list[float]]:
    """Split audio back into BLOCK-sized frames with their RMS values."""
    frames = [wave[i : i + BLOCK] for i in range(0, len(wave), BLOCK)]
    return frames, [frame_rms(f) for f in frames]
