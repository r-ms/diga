"""NVIDIA Parakeet TDT 0.6B v3 on Apple Silicon (MLX) — 25 European languages.

Covers English and Portuguese (its training data is European Portuguese) among others, with
automatic language detection. Model: ``mlx-community/parakeet-tdt-0.6b-v3`` (CC-BY-4.0).
"""

from __future__ import annotations

import logging

import numpy as np

from ..models import PARAKEET_V3, ModelSpec, fetch
from .base import Transcript, words_from_tokens

log = logging.getLogger(__name__)


class ParakeetTranscriber:
    name = "parakeet"

    def __init__(self, model: str | None = None, spec: ModelSpec = PARAKEET_V3) -> None:
        import mlx.core as mx
        from parakeet_mlx import from_pretrained
        from parakeet_mlx.audio import get_logmel

        self._mx = mx
        # get_logmel is wrapped in an unbounded functools.lru_cache that would keep every
        # chunk ever recorded alive; call the undecorated function instead.
        self._get_logmel = getattr(get_logmel, "__wrapped__", get_logmel)
        source = model or str(fetch(spec))  # pinned revision; no network once downloaded
        log.info("loading Parakeet from %s", source)
        self._model = from_pretrained(source)
        self._min_samples = int(self._model.preprocessor_config.hop_length)

    def warmup(self) -> None:
        self.transcribe(np.zeros(16_000 // 2, dtype=np.float32))

    def transcribe(self, audio: np.ndarray) -> Transcript:
        audio = np.asarray(audio, dtype=np.float32)
        if len(audio) < self._min_samples:
            return Transcript("")
        mx = self._mx
        # float32 in: the STFT reinterprets complex output as pairs of the input dtype
        mel = self._get_logmel(mx.array(audio), self._model.preprocessor_config)
        result = self._model.generate(mel)[0]
        tokens = [
            (tok.text, float(tok.start), float(tok.end), float(tok.confidence))
            for tok in result.tokens
        ]
        words = words_from_tokens(tokens)
        return Transcript(result.text.strip(), tuple(words))
