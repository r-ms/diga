"""Model registry: where each model comes from, its license, and download helpers.

Everything is fetched from Hugging Face into the standard Hugging Face cache on first use.
Repositories that ship code (GigaAM) are pinned to a reviewed commit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelSpec:
    key: str
    repo: str
    revision: str | None  # branch, tag or commit; None = default branch
    license: str
    size_mb: int
    purpose: str
    files: tuple[str, ...] = field(default=())  # empty: the whole repository
    weights: str = ""  # the big file whose presence means "downloaded"

    @property
    def check_file(self) -> str:
        return self.weights or (self.files[0] if self.files else "config.json")


GIGAAM_RNNT = ModelSpec(
    key="gigaam-v3-e2e-rnnt",
    repo="ai-sage/GigaAM-v3",
    revision="7655ad717f8122257385bb4b2f373db3697e8680",  # branch e2e_rnnt
    license="MIT",
    size_mb=450,
    purpose="Russian transcription with punctuation",
    weights="pytorch_model.bin",
)
GIGAAM_CTC_INT8 = ModelSpec(
    key="gigaam-v3-e2e-ctc-int8",
    repo="istupakov/gigaam-v3-onnx",
    revision="322c3b29492673eb7d0b434bfa9dfb8653e34d02",
    license="MIT",
    size_mb=225,
    purpose="Russian acoustic term correction (CTC, ONNX int8)",
    files=("v3_e2e_ctc.int8.onnx",),
)
GIGAAM_CTC_FP32 = ModelSpec(
    key="gigaam-v3-e2e-ctc",
    repo="istupakov/gigaam-v3-onnx",
    revision="322c3b29492673eb7d0b434bfa9dfb8653e34d02",
    license="MIT",
    size_mb=886,
    purpose="Russian acoustic term correction (CTC, ONNX fp32)",
    files=("v3_e2e_ctc.onnx",),
)
GIGAAM_CTC_TOKENIZER = ModelSpec(
    key="gigaam-v3-e2e-ctc-tokenizer",
    repo="ai-sage/GigaAM-v3",
    revision="cec030b4c4f35d928e4a9044a3bdb29ebd499fac",  # branch e2e_ctc
    license="MIT",
    size_mb=1,
    purpose="Tokenizer of the CTC model",
    files=("tokenizer.model",),
)
PARAKEET_V3 = ModelSpec(
    key="parakeet-tdt-0.6b-v3",
    repo="mlx-community/parakeet-tdt-0.6b-v3",
    revision="ed2b7e8c15f9aaa0b5772e2efb986255eaef7e15",
    license="CC-BY-4.0",
    size_mb=2510,
    purpose="English, Portuguese and 23 more European languages",
    weights="model.safetensors",
)
WHISPER_TURBO = ModelSpec(
    key="whisper-large-v3-turbo",
    repo="mlx-community/whisper-large-v3-turbo",
    revision="a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb",
    license="MIT",
    size_mb=1614,
    purpose="Every other language Whisper supports",
    weights="weights.safetensors",
)

QWEN3_LM = ModelSpec(
    key="qwen3-0.6b-4bit",
    repo="mlx-community/Qwen3-0.6B-4bit",
    revision="73e3e38d981303bc594367cd910ea6eb48349da8",
    license="Apache-2.0",
    size_mb=351,
    purpose="Small language model that arbitrates the Russian second opinion",
    weights="model.safetensors",
)

REGISTRY: tuple[ModelSpec, ...] = (
    GIGAAM_RNNT,
    GIGAAM_CTC_INT8,
    GIGAAM_CTC_FP32,
    GIGAAM_CTC_TOKENIZER,
    PARAKEET_V3,
    WHISPER_TURBO,
    QWEN3_LM,
)


def fetch_file(spec: ModelSpec, filename: str) -> Path:
    """Local path of one file of ``spec``; the network is used only if it is not cached yet."""
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    try:
        return Path(
            hf_hub_download(spec.repo, filename, revision=spec.revision, local_files_only=True)
        )
    except LocalEntryNotFoundError:
        log.info("downloading %s/%s…", spec.repo, filename)
        return Path(hf_hub_download(spec.repo, filename, revision=spec.revision))


def fetch(spec: ModelSpec) -> Path:
    """Local snapshot directory of ``spec`` (only ``spec.files`` if listed).

    Cached models load without touching the network — Hugging Face's own loaders would check
    for updates on every start, and diga promises not to go online after the first download.
    """
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    patterns = list(spec.files) or None
    try:
        local = Path(
            snapshot_download(
                spec.repo, revision=spec.revision, allow_patterns=patterns, local_files_only=True
            )
        )
        if (local / spec.check_file).is_file():  # not a half-finished download
            return local
    except LocalEntryNotFoundError:
        pass
    log.info("downloading %s (%d MB)…", spec.repo, spec.size_mb)
    return Path(snapshot_download(spec.repo, revision=spec.revision, allow_patterns=patterns))


def is_cached(spec: ModelSpec) -> bool:
    """True if the model's main file is already in the local cache (no network)."""
    from huggingface_hub import try_to_load_from_cache

    found = try_to_load_from_cache(spec.repo, spec.check_file, revision=spec.revision)
    return isinstance(found, str)


def needed(cfg: Config) -> list[ModelSpec]:
    """The models diga loads with this configuration (what ``diga models --download default``
    fetches, so the first dictation does not wait for a download)."""
    backends = {cfg.backend_for(cfg.language)}
    if cfg.language == "auto":
        backends.add(cfg.backend_for("ru"))
    russian = "gigaam" in backends
    if russian and cfg.second_opinion:
        backends.add("parakeet")
    by_backend = {"gigaam": GIGAAM_RNNT, "parakeet": PARAKEET_V3, "whisper": WHISPER_TURBO}
    specs = [by_backend[b] for b in sorted(backends) if b in by_backend]
    if russian and cfg.terms.enabled:
        ctc = GIGAAM_CTC_FP32 if cfg.terms.ctc_precision == "fp32" else GIGAAM_CTC_INT8
        specs += [ctc, GIGAAM_CTC_TOKENIZER]
    if russian and cfg.second_opinion and cfg.use_language_model():
        specs.append(QWEN3_LM)
    return specs
