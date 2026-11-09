"""The ``auto`` language (the default): no need to tell diga which language you speak.

Parakeet v3 hears every chunk; it knows 25 European languages and picks the language itself,
so English, Portuguese and the rest come straight from it. When it writes a chunk mostly in
Cyrillic, the speaker was speaking Russian, where GigaAM is much stronger: GigaAM transcribes
the same chunk, and Parakeet's words — already at hand — serve as its second opinion
(``second_opinion.py``). The result is marked ``language="ru"`` so that term correction uses
the Russian acoustic spotter.

Speed: people mostly keep to one language, so after a Russian chunk GigaAM starts on the next
one right away, in parallel with Parakeet (and its result is dropped if that chunk turns out
not to be Russian). After a non-Russian chunk only Parakeet runs, so English and Portuguese
cost nothing extra.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import numpy as np

from ..terms.text import dominant_script
from .base import Transcriber, Transcript
from .second_opinion import _timed, merge_transcripts

log = logging.getLogger(__name__)


class AutoTranscriber:
    def __init__(
        self,
        detector: Transcriber,
        russian: Transcriber,
        *,
        second_opinion: bool = True,
        unsure: float = 0.8,
        insert: float = 0.85,
        judge: Callable[[str], float] | None = None,
        margin: float = 0.25,
    ) -> None:
        self.detector, self.russian = detector, russian
        self.name = f"auto({detector.name}, ru: {russian.name})"
        self._second_opinion = second_opinion
        self._merge_args = (unsure, insert, judge, margin)
        # One worker: GigaAM never runs twice at once, even when a dropped early run is
        # still finishing.
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="diga-ru")
        self._last_was_russian = False

    def warmup(self) -> None:
        self.detector.warmup()
        self.russian.warmup()

    def transcribe(self, audio: np.ndarray) -> Transcript:
        early = self._pool.submit(_timed, self.russian, audio) if self._last_was_russian else None
        heard = _timed(self.detector, audio)
        self._last_was_russian = dominant_script(heard.text) == "cyrillic"
        log.debug("  language: %s", "Russian" if self._last_was_russian else "not Russian")
        if not self._last_was_russian:
            return heard
        future = early or self._pool.submit(_timed, self.russian, audio)
        mine = replace(future.result(), language="ru")
        if not self._second_opinion:
            return mine
        return merge_transcripts(mine, heard, *self._merge_args)
