"""GigaAM v3 CTC model (ONNX) — frame-level log-probabilities for the Russian term spotter."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..models import GIGAAM_CTC_FP32, GIGAAM_CTC_INT8, GIGAAM_CTC_TOKENIZER, fetch_file

SAMPLE_RATE = 16_000


class GigaAMCtc:
    """ONNX CTC model + SentencePiece tokenizer + the matching log-mel front end."""

    frame_s = 0.04  # 10 ms hop × 4 subsampling
    language = "ru"

    def __init__(self, onnx_path: Path, tokenizer_path: Path, threads: int = 2) -> None:
        import onnxruntime as ort
        import sentencepiece as spm
        import torch
        import torchaudio

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        opts.add_session_config_entry("session.intra_op.allow_spinning", "0")
        self._session = ort.InferenceSession(
            str(onnx_path), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self._sp = spm.SentencePieceProcessor(model_file=str(tokenizer_path))
        self.blank_id = int(self._sp.get_piece_size())  # vocabulary + 1 blank = 257
        self._torch = torch
        # Same front end as GigaAM's own FeatureExtractor: 64 HTK mels, 20 ms window, 10 ms hop.
        self._mel = torchaudio.transforms.MelSpectrogram(
            sample_rate=SAMPLE_RATE,
            n_mels=64,
            win_length=SAMPLE_RATE // 50,
            hop_length=SAMPLE_RATE // 100,
            n_fft=SAMPLE_RATE // 50,
            center=False,
        )

    @classmethod
    def from_hub(cls, precision: str = "int8") -> GigaAMCtc:
        spec = GIGAAM_CTC_FP32 if precision == "fp32" else GIGAAM_CTC_INT8
        return cls(
            fetch_file(spec, spec.files[0]),
            fetch_file(GIGAAM_CTC_TOKENIZER, GIGAAM_CTC_TOKENIZER.files[0]),
        )

    def encode(self, text: str) -> list[int]:
        return list(self._sp.encode(text))

    def log_probs(self, audio: np.ndarray) -> np.ndarray:
        """One chunk (≤ 20 s, 16 kHz mono float32) → [T, blank_id + 1] log-probabilities."""
        torch = self._torch
        with torch.no_grad():
            feats = self._mel(torch.from_numpy(np.asarray(audio, dtype=np.float32))[None, :])
            feats = torch.log(feats.clamp(1e-9, 1e9))
        out = self._session.run(
            None,
            {
                "features": feats.numpy(),
                "feature_lengths": np.array([feats.shape[2]], dtype=np.int64),
            },
        )
        return np.asarray(out[0])[0]
