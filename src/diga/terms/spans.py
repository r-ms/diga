"""Choosing which recognized words a term replaces, and applying the replacements.

Shared by both correctors: the acoustic one (which first finds *where* a term was said) and
the text-only one (which scans every span).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from .text import normalize, stopwords

MAX_SPAN = 3  # a term can replace up to three recognized words ("гит лаб" → GitLab)


@dataclass(frozen=True)
class Replacement:
    first: int  # index of the first replaced word
    count: int  # how many words are replaced (may differ from the term's word count)
    term: str


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def best_span(
    norm_words: list[str], candidates: list[int], targets: list[str], max_span: int = MAX_SPAN
) -> tuple[float, list[int]]:
    """Contiguous run of 1..max_span candidate words most similar to any target."""
    best, span = 0.0, []
    for a in range(len(candidates)):
        for b in range(a, min(a + max_span, len(candidates))):
            idx = candidates[a : b + 1]
            if idx[-1] - idx[0] != len(idx) - 1:
                continue
            text = " ".join(norm_words[i] for i in idx).strip()
            if not text:
                continue
            sim = max(similarity(text, t) for t in targets)
            if sim > best:
                best, span = sim, idx
    return best, span


def same_stem(a: str, b: str) -> bool:
    """Crude inflection check: same word with a different ending is not an error to fix."""
    if a == b:
        return True
    if min(len(a), len(b)) < 4:
        return False
    common = 0
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        common += 1
    return common >= max(len(a), len(b)) - 3


def already_correct(term_norm: str, span_norms: list[str]) -> bool:
    joined = " ".join(n for n in span_norms if n)
    if term_norm in span_norms or term_norm == joined:
        return True
    return any(same_stem(term_norm, n) for n in span_norms if n) or same_stem(term_norm, joined)


def only_stopwords(span_norms: list[str], *languages: str) -> bool:
    sw = stopwords(*languages)
    return all(n in sw for n in span_norms if n)


_EDGE = re.compile(r"^(\W*)(.*?)(\W*)$", re.UNICODE | re.DOTALL)


def apply_replacements(words: list[str], replacements: list[Replacement]) -> str:
    """Replace word spans by terms; keep leading/trailing punctuation; first one wins."""
    out = list(words)
    taken: set[int] = set()
    plan: dict[int, Replacement] = {}
    for r in replacements:
        span = range(r.first, r.first + r.count)
        if r.count < 1 or r.first < 0 or span.stop > len(words) or taken.intersection(span):
            continue
        taken.update(span)
        plan[r.first] = r
    result: list[str] = []
    i = 0
    while i < len(out):
        r = plan.get(i)
        if r is None:
            result.append(out[i])
            i += 1
            continue
        lead = _EDGE.match(out[i]).group(1)  # type: ignore[union-attr]
        trail = _EDGE.match(out[i + r.count - 1]).group(3)  # type: ignore[union-attr]
        result.append(f"{lead}{r.term}{trail}")
        i += r.count
    return " ".join(result)


def normalized_words(words: list[str], language: str) -> list[str]:
    return [normalize(w, language) for w in words]


def describe(words: list[str], replacements: list[Replacement]) -> str:
    """'пужгид → git, пайтоне → Python' for the debug log."""
    return ", ".join(
        f"{' '.join(words[r.first : r.first + r.count])} → {r.term}" for r in replacements
    )
