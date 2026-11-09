"""GigaAM v3 (Russian) — the RNN-T model with punctuation, kept warm on the GPU.

The model is ``ai-sage/GigaAM-v3`` (MIT), revision ``e2e_rnnt``, loaded through
``transformers`` with the repository's own code. Word timings come from a greedy RNN-T
decode that also records the encoder frame of every emitted token — the model's public
``transcribe()`` returns text only, and the acoustic term corrector needs the timings.
"""

from __future__ import annotations

import logging
import math
import os
import sys
import warnings

import numpy as np

from ..models import GIGAAM_RNNT, ModelSpec, fetch
from .base import Transcript, Word

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
MAX_SAMPLES = 25 * SAMPLE_RATE  # the model rejects longer clips; diga's chunks are ≤ 20 s

# torchaudio's FeatureExtractor passes a preallocated `out` tensor to stft; harmless warning.
warnings.filterwarnings("ignore", message=".*output with one or more elements was resized.*")


def _ensure_pyannote_importable() -> None:
    try:
        import pyannote  # noqa: F401  # pyright: ignore[reportMissingImports]
    except ImportError:
        stubs = os.path.join(os.path.dirname(__file__), "_stubs")
        if stubs not in sys.path:
            sys.path.append(stubs)


class GigaAMTranscriber:
    name = "gigaam"

    def __init__(
        self, model: str | None = None, device: str = "mps", spec: ModelSpec = GIGAAM_RNNT
    ) -> None:
        import torch
        from transformers import AutoModel

        _ensure_pyannote_importable()
        self._torch = torch
        # A local snapshot of the pinned, reviewed commit (its code runs at load time), so
        # loading needs no network once it is downloaded.
        source = os.path.expanduser(model) if model else str(fetch(spec))
        kwargs: dict = {"trust_remote_code": True, "low_cpu_mem_usage": False}
        log.info("loading GigaAM from %s", source)
        # low_cpu_mem_usage=False: the model builds real tensors in its FeatureExtractor,
        # which is incompatible with meta-device initialisation.
        hf_model = AutoModel.from_pretrained(source, **kwargs)
        self._inner = hf_model.model  # GigaAMASR: .forward / .decoding / .head
        self._dtype = self._inner._dtype
        self._device = torch.device("cpu")
        if device == "mps" and torch.backends.mps.is_available():
            try:
                hf_model.to("mps")
                self._device = torch.device("mps")
            except Exception as e:
                log.warning("MPS failed, falling back to CPU: %s", e)
        elif device == "cuda" and torch.cuda.is_available():
            hf_model.cuda()
            self._device = torch.device("cuda")
        log.info("GigaAM ready on %s", self._device)

    def warmup(self) -> None:
        try:
            self.transcribe(np.zeros(SAMPLE_RATE // 2, dtype=np.float32))
        except Exception as e:
            log.warning("warmup failed (non-fatal): %s", e)

    def transcribe(self, audio: np.ndarray) -> Transcript:
        torch = self._torch
        audio = np.asarray(audio, dtype=np.float32)
        if audio.shape[0] > MAX_SAMPLES:
            log.warning("chunk longer than 25 s truncated")
            audio = audio[:MAX_SAMPLES]
        with torch.inference_mode():
            wav = torch.from_numpy(audio).to(self._device).to(self._dtype).unsqueeze(0)
            length = torch.full([1], wav.shape[-1], device=self._device)
            encoded, encoded_len = self._inner.forward(wav, length)  # [B, D, T], [B]
            n_frames = int(encoded_len[0].item())
            if n_frames <= 0:
                return Transcript("")
            frame_s = wav.shape[-1] / SAMPLE_RATE / n_frames
            tokens, frames, confidences = self._greedy_decode(encoded, n_frames)
        if self._device.type == "mps":
            # PyTorch keeps freed GPU buffers for reuse; with chunks of every length that pool
            # only grows (several GB over a session). Releasing it costs no measurable time.
            torch.mps.empty_cache()
        words = self._words(tokens, frames, confidences, frame_s)
        return Transcript(" ".join(w.text for w in words), tuple(words))

    def _greedy_decode(self, encoded, n_frames: int) -> tuple[list[int], list[int], list[float]]:
        """Greedy RNN-T decode (batch 1) that also records each token's encoder frame and
        confidence.

        Mirrors ``RNNTGreedyDecoding._greedy_decode`` from the model's own code. Confidence is
        ``1 − entropy / max_entropy`` of the output distribution at the step that emitted the
        token (the same measure parakeet-mlx uses): ~1 when the model is sure, lower when the
        probability is spread over several tokens.
        """
        torch = self._torch
        head = self._inner.head
        decoding = self._inner.decoding
        x = encoded.transpose(1, 2)[0].unsqueeze(1)  # [T, 1, D]
        hyp: list[int] = []
        frames: list[int] = []
        pending: list = []  # per-token confidence tensors
        state = None
        last = None
        for t in range(n_frames):
            f = x[t, :, :].unsqueeze(1)
            emitted = 0
            while emitted < decoding.max_symbols:
                g, hidden = head.decoder.predict(last, state)
                logits = head.joint.joint(f, g)[0, 0, 0, :].float()
                k = int(logits.argmax(0).item())
                if k == decoding.blank_id:
                    break
                probs = torch.softmax(logits, dim=-1)
                # kept as a tensor: one GPU→CPU sync at the end instead of one per token
                entropy = -(probs * torch.log(probs + 1e-12)).sum()
                pending.append(1.0 - entropy / math.log(logits.shape[-1]))
                hyp.append(k)
                frames.append(t)
                state = hidden
                last = torch.tensor([[k]]).to(x.device)
                emitted += 1
        confidences = torch.stack(pending).float().tolist() if pending else []
        return hyp, frames, confidences

    def _words(
        self, tokens: list[int], frames: list[int], confidences: list[float], frame_s: float
    ) -> list[Word]:
        sp = self._inner.decoding.tokenizer.model  # SentencePieceProcessor
        words: list[Word] = []
        cur_t: list[int] = []
        cur_f: list[int] = []
        cur_c: list[float] = []

        def flush() -> None:
            if cur_t:
                text = sp.decode(cur_t).strip()
                if text:
                    words.append(
                        Word(
                            text,
                            round(cur_f[0] * frame_s, 3),
                            round((cur_f[-1] + 1) * frame_s, 3),
                            round(min(cur_c), 3),
                        )
                    )

        for tok, frame, conf in zip(tokens, frames, confidences, strict=True):
            if sp.id_to_piece(tok).startswith("▁") and cur_t:
                flush()
                cur_t, cur_f, cur_c = [], [], []
            cur_t.append(tok)
            cur_f.append(frame)
            cur_c.append(conf)
        flush()
        return words
