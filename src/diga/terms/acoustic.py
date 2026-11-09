"""Acoustic term correction: listen for glossary terms in the audio, then fix the text.

1. A CTC model scores the chunk frame by frame; the spotter finds where each term (in any of
   its spellings and pronunciation variants) was most likely said.
2. Around each spot (±0.4 s) we pick the 1–3 recognized words whose text is closest to the
   term or one of its variants.
3. Guards against false fixes: the words already are the term (or an inflected form of it),
   the match is weak, or the words are only stop-words.

Works with any recognizer that returns word timings; the CTC model must speak the language
(the bundled one is Russian: Latin terms are also searched in Cyrillic transliteration).
"""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Protocol

import numpy as np

from ..asr.base import Transcript
from .glossary import GlossaryFile
from .spans import (
    Replacement,
    already_correct,
    apply_replacements,
    best_span,
    describe,
    normalized_words,
    only_stopwords,
)
from .spotter import Trie, spot
from .text import CYRILLIC_LANGUAGES, normalize, to_cyrillic

log = logging.getLogger(__name__)

SIM_THRESHOLD = 0.55
STOPWORD_MIN_SIM = 0.85
CONSUME_WINDOW_S = 0.4


class CtcModel(Protocol):
    frame_s: float
    blank_id: int
    language: str

    def encode(self, text: str) -> list[int]: ...

    def log_probs(self, audio: np.ndarray) -> np.ndarray: ...


def spellings(term: str, variants: tuple[str, ...], language: str) -> list[str]:
    """Every string to search for: case forms, pronunciation variants, transliterations."""
    norm = normalize(term, language)
    out = [norm, norm[:1].upper() + norm[1:], term]
    for v in variants:
        out += [v, v[:1].upper() + v[1:]]
    if language in CYRILLIC_LANGUAGES:  # a Latin brand said by a Russian speaker
        for s in list(out):
            if any("a" <= c.lower() <= "z" for c in s):
                cyr = to_cyrillic(s)
                out += [cyr, cyr[:1].upper() + cyr[1:]]
    seen: set[str] = set()
    return [s for s in out if s and not (s in seen or seen.add(s))]


class AcousticCorrector:
    def __init__(
        self,
        ctc: CtcModel,
        glossary: GlossaryFile,
        ctc_weight: float = 0.5,
        max_frames_per_token: int = 15,
        min_similarity: float = SIM_THRESHOLD,
    ) -> None:
        self._ctc = ctc
        self._glossary = glossary
        self._weight = ctc_weight
        self._max_frames = max_frames_per_token
        self._min_similarity = min_similarity
        self._built_version = -1
        self._trie: Trie | None = None
        # The CTC model needs only the audio, so it can run while the recognizer works.
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="diga-ctc")
        self._pending: tuple[np.ndarray, Future[np.ndarray]] | None = None

    @property
    def language(self) -> str:
        return self._ctc.language

    def _ensure_trie(self) -> Trie:
        self._glossary.refresh()
        if self._trie is None or self._built_version != self._glossary.version:
            lang = self.language
            sp = [spellings(t.term, t.variants_for(lang), lang) for t in self._glossary.terms]
            self._trie = Trie(sp, self._ctc.encode, self._ctc.blank_id)
            self._built_version = self._glossary.version
        return self._trie

    def prefetch(self, audio: np.ndarray) -> None:
        self._pending = (audio, self._pool.submit(self._ctc.log_probs, audio))

    def _log_probs(self, audio: np.ndarray) -> np.ndarray:
        pending, self._pending = self._pending, None
        if pending is not None and pending[0] is audio:
            return pending[1].result()
        return self._ctc.log_probs(audio)

    def correct(self, audio: np.ndarray, transcript: Transcript) -> str:
        words = transcript.words
        if not words:
            self._pending = None
            return transcript.text
        trie = self._ensure_trie()
        lang = self.language
        terms = self._glossary.terms
        spots = spot(self._log_probs(audio), trie, self._weight, 0.0, self._max_frames)
        texts = [w.text for w in words]
        norms = normalized_words(texts, lang)
        replacements: list[Replacement] = []
        taken: set[int] = set()
        for s in sorted(spots, key=lambda x: -x.score):
            term = terms[s.entry]
            lo = s.frame_start * self._ctc.frame_s - CONSUME_WINDOW_S
            hi = (s.frame_end + 1) * self._ctc.frame_s + CONSUME_WINDOW_S
            near = [i for i, w in enumerate(words) if lo <= w.start < hi]
            term_norm = normalize(term.term, lang)
            targets = [term_norm] + [normalize(v, lang) for v in term.variants_for(lang)]
            sim, span = best_span(norms, near, targets)
            if sim < self._min_similarity or not span or taken.intersection(span):
                continue
            span_norms = [norms[i] for i in span]
            if already_correct(term_norm, span_norms):
                continue
            if sim < STOPWORD_MIN_SIM and only_stopwords(span_norms, lang):
                continue
            taken.update(span)
            replacements.append(Replacement(span[0], len(span), term.term))
        if replacements:
            log.debug("  terms, by sound: %s", describe(texts, replacements))
        return apply_replacements(texts, replacements)
