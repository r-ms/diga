"""The interface every speech recognizer implements."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class Word:
    text: str
    start: float  # seconds from the start of the chunk
    end: float
    confidence: float = 1.0  # 0..1; the lowest confidence of the word's tokens


@dataclass(frozen=True)
class Transcript:
    text: str
    words: tuple[Word, ...] = field(default=())
    # Language of the chunk when the recognizer decided it (``auto`` mode), e.g. "ru".
    language: str | None = None


class Transcriber(Protocol):
    """Turns one chunk (1-D float32, 16 kHz mono, ≤ 25 s) into text with word timings."""

    name: str

    def transcribe(self, audio: np.ndarray) -> Transcript: ...

    def warmup(self) -> None: ...


def words_from_tokens(tokens: Sequence[tuple], marker: str = " ") -> list[Word]:
    """Group sub-word tokens ``(text, start, end[, confidence])`` into words.

    A token that starts with ``marker`` (a space, or SentencePiece's ``▁``) begins a new word.
    A word's confidence is the lowest confidence of its tokens.
    """
    words: list[Word] = []
    text, start, end, conf = "", 0.0, 0.0, 1.0
    for tok in tokens:
        piece, t0, t1 = tok[0], tok[1], tok[2]
        c = float(tok[3]) if len(tok) > 3 else 1.0
        if piece.startswith(marker) and text.strip():
            words.append(Word(text.strip(), start, end, conf))
            text, conf = "", 1.0
        if not text.strip():
            start = t0
        text += piece.replace(marker, " ") if marker != " " else piece
        end = t1
        conf = min(conf, c)
    if text.strip():
        words.append(Word(text.strip(), start, end, conf))
    return words
