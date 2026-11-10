"""Fixing technical terms the recognizer gets wrong ("гит" → git, "оллама" → ollama)."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from ..asr.base import Transcript
from .glossary import GlossaryFile, Term, ensure_glossary, load_glossary, merge_terms

__all__ = [
    "ByLanguage",
    "ChainCorrector",
    "Corrector",
    "GlossaryFile",
    "Term",
    "ensure_glossary",
    "load_glossary",
    "merge_terms",
]


class Corrector(Protocol):
    @property
    def language(self) -> str: ...

    def correct(self, audio: np.ndarray, transcript: Transcript) -> str: ...


def prefetch(corrector: object, audio: np.ndarray) -> None:
    """Let a corrector start on ``audio`` while the recognizer is still busy, if it can."""
    start = getattr(corrector, "prefetch", None)
    if start is not None:
        start(audio)


class ChainCorrector:
    """Run correctors in order; each sees the text the previous one produced."""

    def __init__(self, *correctors: Corrector) -> None:
        if not correctors:
            raise ValueError("ChainCorrector needs at least one corrector")
        self._correctors = correctors

    @property
    def language(self) -> str:
        return self._correctors[0].language

    def prefetch(self, audio: np.ndarray) -> None:
        for corrector in self._correctors:
            prefetch(corrector, audio)

    def correct(self, audio: np.ndarray, transcript: Transcript) -> str:
        text = self._correctors[0].correct(audio, transcript)
        for corrector in self._correctors[1:]:
            text = corrector.correct(audio, Transcript(text))
        return text


class ByLanguage:
    """Pick the corrector for the language the recognizer reported for a chunk (``auto`` mode).

    ``ByLanguage(text_fixer, ru=russian_chain)``: chunks marked ``language="ru"`` go to the
    Russian chain (acoustic + text), everything else to ``default``.
    """

    def __init__(self, default: Corrector, **by_language: Corrector) -> None:
        self._default, self._by_language = default, by_language
        self._last = default

    def prefetch(self, audio: np.ndarray) -> None:
        # The language is known only after recognition; people mostly keep to one, so get
        # the corrector of the previous chunk going.
        prefetch(self._last, audio)

    @property
    def language(self) -> str:
        return self._default.language

    def correct(self, audio: np.ndarray, transcript: Transcript) -> str:
        corrector = self._by_language.get(transcript.language or "", self._default)
        self._last = corrector
        return corrector.correct(audio, transcript)
