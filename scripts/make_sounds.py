"""Generate diga's sound sets (our own synthesis, so no third-party audio licences).

    uv run python scripts/make_sounds.py            # write src/diga/data/sounds/<set>/*.wav
    uv run python scripts/make_sounds.py preview    # play every set, announced by name

Each set has ``start.wav`` (recording began) and ``done.wav`` (the text has been typed). The
sounds confirm without demanding attention: short, quiet, mostly below 1 kHz, soft attacks
(a sharp onset is what makes a sound feel intrusive) and no long ring.
"""

from __future__ import annotations

import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

SR = 44_100
OUT = Path(__file__).resolve().parents[1] / "src" / "diga" / "data" / "sounds"


def _env(n: int, attack_s: float, tau_s: float) -> np.ndarray:
    t = np.arange(n) / SR
    return np.minimum(1.0, t / attack_s) * np.exp(-t / tau_s)


def tone(freq: float, dur: float, tau: float, attack: float = 0.012, warmth: float = 0.12):
    """A soft sine with a little second harmonic."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    wave_ = np.sin(2 * np.pi * freq * t) + warmth * np.sin(4 * np.pi * freq * t)
    return wave_ * _env(n, attack, tau)


def mallet(freq: float, dur: float = 0.35, tau: float = 0.11) -> np.ndarray:
    """Marimba-like: the fundamental plus two quickly fading upper partials."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for ratio, amp, tau_k in ((1.0, 1.0, tau), (3.93, 0.2, tau / 4), (9.2, 0.04, tau / 10)):
        out += amp * np.sin(2 * np.pi * freq * ratio * t) * _env(n, 0.004, tau_k)
    return out


def tick(freq: float = 1200.0) -> np.ndarray:
    """A tiny wooden tap: a very short damped sine with a breath of noise."""
    n = int(0.05 * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(7)
    body = np.sin(2 * np.pi * freq * t) * _env(n, 0.001, 0.006)
    return body + 0.15 * rng.standard_normal(n) * _env(n, 0.0005, 0.002)


def drop(f0: float, f1: float, dur: float = 0.12) -> np.ndarray:
    """A water drop: a quick upward sweep with a short tail."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    freq = f0 * (f1 / f0) ** np.minimum(1.0, t / 0.04)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    return np.sin(phase) * _env(n, 0.004, 0.03)


def seq(*notes: tuple[float, np.ndarray]) -> np.ndarray:
    """Mix notes starting at the given offsets (seconds)."""
    end = max(int(at * SR) + len(x) for at, x in notes)
    out = np.zeros(end)
    for at, x in notes:
        i = int(at * SR)
        out[i : i + len(x)] += x
    return out


G4, C5, E5, A5, E6, A6 = 392.0, 523.3, 659.3, 880.0, 1318.5, 1760.0

# set → (start, done, peak level); the first set is the default
SETS: dict[str, tuple[np.ndarray, np.ndarray, float]] = {
    "soft": (
        tone(C5, 0.16, 0.05),
        seq((0.0, tone(G4, 0.25, 0.07)), (0.09, tone(C5, 0.35, 0.11))),
        0.12,
    ),
    "tick": (tick(1100), seq((0.0, tick(1000)), (0.07, tick(1400))), 0.10),
    "drop": (drop(300, 600), seq((0.0, drop(330, 660)), (0.09, drop(440, 880))), 0.12),
    "chime": (
        drop(420, 900),
        seq((0.0, mallet(E6, tau=0.08)), (0.075, mallet(A6, tau=0.14))),
        0.14,
    ),
}


def write(path: Path, x: np.ndarray, peak: float) -> None:
    x = x / np.max(np.abs(x)) * peak
    fade = int(0.005 * SR)  # no click at the end
    x[-fade:] *= np.linspace(1, 0, fade)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())


def main() -> None:
    for name, (start, done, peak) in SETS.items():
        write(OUT / name / "start.wav", start, peak)
        write(OUT / name / "done.wav", done, peak)
    if sys.argv[1:] == ["preview"]:
        for name in SETS:
            subprocess.run(["say", name], check=False)
            for f in ("start", "done"):
                subprocess.run(["afplay", str(OUT / name / f"{f}.wav")], check=False)
        return
    print(f"wrote {len(SETS)} sets to {OUT}")


if __name__ == "__main__":
    main()
