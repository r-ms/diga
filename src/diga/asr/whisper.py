"""OpenAI Whisper large-v3-turbo on Apple Silicon (MLX) — every language Whisper supports.

Glossary terms are passed as the initial prompt, which nudges Whisper toward those spellings.
Model: ``mlx-community/whisper-large-v3-turbo`` (MIT).
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from ..models import WHISPER_TURBO, ModelSpec, fetch
from .base import Transcript, Word

log = logging.getLogger(__name__)


class WhisperTranscriber:
    name = "whisper"

    def __init__(
        self,
        language: str | None = None,
        model: str | None = None,
        spec: ModelSpec = WHISPER_TURBO,
        prompt: str | None = None,
    ) -> None:
        import mlx_whisper

        self._whisper = mlx_whisper
        self._repo = model or str(fetch(spec))  # pinned revision; no network once downloaded
        self._language = None if language in (None, "auto") else language
        self.prompt = prompt
        log.info("using Whisper from %s", self._repo)

    def warmup(self) -> None:
        self.transcribe(np.zeros(16_000 // 2, dtype=np.float32))

    def transcribe(self, audio: np.ndarray) -> Transcript:
        result: dict[str, Any] = self._whisper.transcribe(  # pyright: ignore[reportAttributeAccessIssue]
            np.asarray(audio, dtype=np.float32),
            path_or_hf_repo=self._repo,
            language=self._language,
            word_timestamps=True,
            initial_prompt=self.prompt,
            condition_on_previous_text=False,  # chunks are independent; avoids repetition loops
            verbose=None,
        )
        segments: list[dict[str, Any]] = result.get("segments") or []
        words = tuple(
            Word(
                str(w["word"]).strip(),
                float(w["start"]),
                float(w["end"]),
                float(w.get("probability", 1.0)),
            )
            for seg in segments
            for w in seg.get("words") or []
            if str(w["word"]).strip()
        )
        return Transcript(str(result.get("text", "")).strip(), words)
