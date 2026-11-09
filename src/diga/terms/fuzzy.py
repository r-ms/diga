"""Text-only term correction for languages without an acoustic (CTC) model.

Every run of 1–3 recognized words is compared with each term and its pronunciation variants
for the current language; a close enough match is replaced by the term. This is what most
dictation apps do; it cannot recover a term the recognizer mangled beyond recognition, which
is why Russian uses the acoustic corrector instead.

In ``auto`` mode the recognizer picks the language, so the glossary languages are chosen per
chunk from its alphabet: Cyrillic text uses the Cyrillic-script variants (``ru``…), Latin text
the Latin-script ones (``en``, ``pt``…).
"""

from __future__ import annotations

import logging

import numpy as np

from ..asr.base import Transcript
from .glossary import ALL_LANGUAGES, GlossaryFile
from .spans import (
    MAX_SPAN,
    Replacement,
    already_correct,
    apply_replacements,
    best_span,
    describe,
    normalized_words,
    only_stopwords,
)
from .text import CYRILLIC_LANGUAGES, dominant_script, normalize

log = logging.getLogger(__name__)

MIN_CHARS = 3  # very short spans match too many things
# Up to this many letters a word written in the term's own alphabet must match a listed spelling
# exactly: one letter is a large part of a short word, so "code" is close to "clode" (Claude)
# but is a word of its own. Across alphabets a near-miss is a transliteration ("вил" → vLLM),
# so there the usual threshold applies.
EXACT_UP_TO = 5
AUTO = "auto"


class FuzzyCorrector:
    def __init__(self, glossary: GlossaryFile, language: str, threshold: float = 0.84) -> None:
        self._glossary = glossary
        self.language = language
        self._threshold = threshold

    def correct(self, audio: np.ndarray, transcript: Transcript) -> str:
        texts = [w.text for w in transcript.words] or transcript.text.split()
        if not texts:
            return transcript.text
        self._glossary.refresh()
        lang, glossary_langs = self._languages(" ".join(texts))
        norms = normalized_words(texts, lang)
        protected = _already_terms(norms, [normalize(t.term, lang) for t in self._glossary.terms])
        candidates: list[tuple[float, list[int], str]] = []
        for term in self._glossary.terms:
            term_norm = normalize(term.term, lang)
            listed = {normalize(v, lang) for v in term.variants_for(*glossary_langs)}
            targets = [t for t in [term_norm, *listed] if len(t.replace(" ", "")) >= MIN_CHARS]
            if not targets:
                continue
            for i in range(len(norms)):
                sim, span = best_span(norms, list(range(i, min(i + MAX_SPAN, len(norms)))), targets)
                if sim < self._threshold or not span or span[0] != i:
                    continue
                span_norms = [norms[j] for j in span]
                joined = " ".join(span_norms)
                if joined == term_norm or only_stopwords(span_norms, *glossary_langs):
                    continue
                if protected.intersection(span):  # part of a term that is already right
                    continue
                short = len(joined.replace(" ", "")) <= EXACT_UP_TO
                same_alphabet = dominant_script(joined) == dominant_script(term.term)
                if short and same_alphabet and joined not in listed:
                    continue
                # A misspelling the user listed is replaced even if it looks like an
                # inflected form of the term ("cômite" vs "commit"); otherwise guard.
                if joined not in listed and already_correct(term_norm, span_norms):
                    continue
                candidates.append((sim, span, term.term))
        replacements: list[Replacement] = []
        taken: set[int] = set()
        # Best match first; on a tie the longer term wins ("cloud code" → Claude Code, not Claude).
        for _, span, term in sorted(candidates, key=lambda c: (-c[0], -len(c[1]))):
            if taken.intersection(span):
                continue
            taken.update(span)
            replacements.append(Replacement(span[0], len(span), term))
        if replacements:
            log.debug("  terms, by spelling: %s", describe(texts, replacements))
        return apply_replacements(texts, replacements)

    def _languages(self, text: str) -> tuple[str, list[str]]:
        """(language for normalisation, glossary languages) for this chunk."""
        if self.language != AUTO:
            return self.language, [self.language]
        cyrillic = dominant_script(text) == "cyrillic"
        known = {
            lang
            for term in self._glossary.terms
            for lang in term.variants
            if lang != ALL_LANGUAGES and (lang in CYRILLIC_LANGUAGES) == cyrillic
        }
        if cyrillic:
            return "ru", sorted(known | {"ru"})
        return "en", sorted(known | {"en", "pt"})


def _already_terms(norms: list[str], term_norms: list[str]) -> set[int]:
    """Indices of words that already spell a glossary term ("Claude Code" stays as it is)."""
    covered: set[int] = set()
    for term in term_norms:
        parts = term.split()
        n = len(parts)
        if not n:
            continue
        for i in range(len(norms) - n + 1):
            if norms[i : i + n] == parts:
                covered.update(range(i, i + n))
    return covered
