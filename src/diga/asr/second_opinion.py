"""Second opinion: a second recognizer fixes the words the first one is unsure about.

Both recognizers transcribe the same chunk and their word sequences are aligned (as in ROVER,
Fiscus 1997). Where they agree, nothing changes. Where they disagree, the primary's words are
kept unless the primary is *unsure* there (word confidence below ``unsure``) and the secondary
is more confident. Words the primary dropped but the secondary heard with confidence of at
least ``insert`` are inserted.

With a ``judge`` (a small language model, see ``plausibility.py``) each disagreement is also
read in context: the whole sentence is scored with either wording, and a clear preference
(more than ``margin`` nats per token) decides — even where GigaAM was acoustically sure of a
word that does not exist ("maby Just Смоу" → "maybe just small"), and in the other direction it
protects GigaAM's correct words from Parakeet's mistakes. Without a clear preference the
confidence rule above decides.

Meant for Russian: GigaAM is the stronger Russian recognizer, while Parakeet often hears the
English technical terms and phrases GigaAM garbles ("Соберидоробрас" → "Собери докер образ").
No glossary is needed. See ``benchmarks/terms.py``.
"""

from __future__ import annotations

import difflib
import logging
import re
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .base import Transcriber, Transcript, Word

log = logging.getLogger(__name__)

_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


def _key(word: Word) -> str:
    """Comparison form of a word: lower-case, ё→е, no punctuation."""
    return _NON_WORD.sub(" ", word.text.lower().replace("ё", "е")).strip()


def _by_confidence(mine: list[Word], theirs: list[Word], unsure: float, insert: float) -> bool:
    """Take the secondary's words? Decided by the recognizers' confidence alone."""
    their_conf = min((w.confidence for w in theirs), default=0.0)
    if not mine:  # the primary dropped something the secondary heard
        return their_conf >= insert
    my_conf = min(w.confidence for w in mine)
    return bool(theirs) and my_conf < unsure and their_conf > my_conf


def merge(
    primary: Sequence[Word],
    secondary: Sequence[Word],
    unsure: float = 0.8,
    insert: float = 0.85,
    judge: Callable[[str], float] | None = None,
    margin: float = 0.25,
    floor: float = 0.5,
) -> list[Word]:
    """Align two word sequences and resolve each disagreement (see the module docstring).

    ``judge(sentence)`` returns a plausibility score (higher is better); the secondary's words
    are only taken on the judge's say-so if their own confidence is at least ``floor``.
    """
    a = [_key(w) for w in primary]
    b = [_key(w) for w in secondary]
    out: list[Word] = []
    for op, a0, a1, b0, b1 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        mine, theirs = list(primary[a0:a1]), list(secondary[b0:b1])
        if op == "equal":
            out += mine
            continue
        take = _by_confidence(mine, theirs, unsure, insert)
        why = "confidence " + "/".join(
            f"{min(w.confidence for w in ws):.2f}" if ws else "—" for ws in (mine, theirs)
        )
        if judge is not None and theirs:
            before = [w.text for w in out]
            after = [w.text for w in primary[a1:]]
            with_mine = judge(" ".join(before + [w.text for w in mine] + after))
            with_theirs = judge(" ".join(before + [w.text for w in theirs] + after))
            their_conf = min(w.confidence for w in theirs)
            lm = f"language model {with_theirs - with_mine:+.2f}"
            if with_theirs - with_mine > margin and their_conf >= floor:
                take, why = True, lm
            elif with_mine - with_theirs > margin:
                take, why = False, lm
        log.debug(
            "  second opinion: «%s» vs «%s» → %s (%s)",
            " ".join(w.text for w in mine),
            " ".join(w.text for w in theirs),
            "second" if take else "first",
            why,
        )
        out += theirs if take else mine
    return out


def merge_transcripts(
    mine: Transcript,
    theirs: Transcript,
    unsure: float = 0.8,
    insert: float = 0.85,
    judge: Callable[[str], float] | None = None,
    margin: float = 0.25,
) -> Transcript:
    """``merge`` for whole transcripts; ``mine`` is the primary recognizer's."""
    if not mine.words:
        return mine
    words = merge(mine.words, theirs.words, unsure, insert, judge, margin)
    if words == list(mine.words):
        return mine
    return Transcript(" ".join(w.text for w in words), tuple(words), mine.language)


def _timed(transcriber: Transcriber, audio: np.ndarray) -> Transcript:
    """Transcribe and log what this recognizer heard and how long it took (debug)."""
    t0 = time.perf_counter()
    result = transcriber.transcribe(audio)
    log.debug("  %s (%.2f s): %s", transcriber.name, time.perf_counter() - t0, result.text)
    return result


class SecondOpinionTranscriber:
    """Runs ``primary`` and ``secondary`` on every chunk (in parallel) and merges them."""

    def __init__(
        self,
        primary: Transcriber,
        secondary: Transcriber,
        unsure: float = 0.8,
        insert: float = 0.85,
        judge: Callable[[str], float] | None = None,
        margin: float = 0.25,
    ) -> None:
        self.primary, self.secondary = primary, secondary
        self.name = f"{primary.name}+{secondary.name}" + ("+lm" if judge else "")
        self._unsure, self._insert = unsure, insert
        self._judge, self._margin = judge, margin
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="diga-second")

    def warmup(self) -> None:
        self.primary.warmup()
        self.secondary.warmup()

    def transcribe(self, audio: np.ndarray) -> Transcript:
        future = self._pool.submit(_timed, self.secondary, audio)
        mine = _timed(self.primary, audio)
        try:
            theirs = future.result()
        except Exception as e:  # the second opinion is optional: fall back to the primary
            log.warning("second opinion failed, using %s alone: %s", self.primary.name, e)
            return mine
        return merge_transcripts(
            mine, theirs, self._unsure, self._insert, self._judge, self._margin
        )
