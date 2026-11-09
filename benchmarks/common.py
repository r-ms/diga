"""Shared helpers for the benchmarks: synthesized speech and WAV I/O."""

from __future__ import annotations

import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

SR = 16_000


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        if w.getframerate() != SR or w.getnchannels() != 1:
            raise ValueError(f"{path}: need 16 kHz mono WAV")
        return (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16) / 32768.0).astype(
            np.float32
        )


def write_wav(path: Path, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def say(text: str, voice: str) -> np.ndarray:
    """Speech from a macOS voice (a stand-in for real recordings: cleaner than a human)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "say.wav"
        cmd = ["say", "-v", voice, f"--data-format=LEI16@{SR}", "-o", str(out), text]
        for attempt in range(3):  # the macOS speech service occasionally hangs; retry
            try:
                subprocess.run(cmd, check=True, timeout=60)
                break
            except subprocess.TimeoutExpired:
                if attempt == 2:
                    raise
        return read_wav(out)


def _words(text: str) -> list[str]:
    import re

    return re.sub(r"[^\w]+", " ", text.lower().replace("ё", "е")).split()


def word_errors(reference: str, hypothesis: str) -> tuple[int, int]:
    """(edit distance in words, reference length) after lower-casing and dropping punctuation."""
    ref, hyp = _words(reference), _words(hypothesis)
    row = list(range(len(hyp) + 1))
    for i in range(1, len(ref) + 1):
        prev, row[0] = row[0], i
        for j in range(1, len(hyp) + 1):
            prev, row[j] = (
                row[j],
                min(row[j] + 1, row[j - 1] + 1, prev + (ref[i - 1] != hyp[j - 1])),
            )
    return row[len(hyp)], len(ref)
