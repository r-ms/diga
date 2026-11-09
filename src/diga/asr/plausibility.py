"""How plausible a sentence is, according to a small language model (Qwen3 0.6B on MLX).

Used by the second opinion to decide between GigaAM's and Parakeet's wording of the same
moment: the model reads the whole sentence with each alternative and the one it finds more
likely wins. Unlike a word list it sees context, so it prefers "maybe just small" over
"maby Just Смоу" — and also keeps GigaAM's "логи Редиса" against Parakeet's "логер Диса".

Score = mean log-probability per token, so sentences of different lengths are comparable.
"""

from __future__ import annotations

import logging
from typing import Any

from ..models import QWEN3_LM, ModelSpec, fetch

log = logging.getLogger(__name__)


class PlausibilityModel:
    def __init__(self, spec: ModelSpec = QWEN3_LM) -> None:
        import mlx.core as mx
        from mlx_lm import load

        self._mx = mx
        log.info("loading the language model %s", spec.repo)
        loaded: Any = load(str(fetch(spec)))
        self._model: Any = loaded[0]
        self._tokenizer: Any = loaded[1]
        # A neutral line break before the sentence, so its first word is scored too.
        self._prefix = list(self._tokenizer.encode("\n"))

    def warmup(self) -> None:
        self.score("проверка связи")

    def score(self, text: str) -> float:
        """Mean log-probability per token of ``text`` (higher = more plausible)."""
        mx = self._mx
        body = list(self._tokenizer.encode(text))
        if not body:
            return 0.0
        ids = self._prefix + body
        logits = self._model(mx.array([ids]))[0]  # [T, vocab]
        logp = logits - mx.logsumexp(logits, axis=-1, keepdims=True)
        targets = mx.array(ids[len(self._prefix) :])
        picked = mx.take_along_axis(logp[len(self._prefix) - 1 : -1], targets[:, None], axis=-1)
        return float(picked.mean())
