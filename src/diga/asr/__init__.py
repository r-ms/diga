"""Speech recognizers and picking one for a language."""

from __future__ import annotations

from ..config import Config
from .base import Transcriber, Transcript, Word

__all__ = [
    "BACKENDS",
    "MissingBackend",
    "Transcriber",
    "Transcript",
    "Word",
    "create_transcriber",
]

# backend → (extra to install, languages it is meant for)
BACKENDS: dict[str, tuple[str, str]] = {
    "gigaam": ("ru", "Russian"),
    "parakeet": ("parakeet", "25 European languages incl. English and Portuguese"),
    "whisper": ("whisper", "99 languages"),
}


class MissingBackend(RuntimeError):
    def __init__(self, backend: str) -> None:
        extra = BACKENDS.get(backend, (backend, ""))[0]
        super().__init__(
            f"the '{backend}' recognizer is not installed — "
            f"install it with: uv tool install 'diga[{extra}]'"
        )


def create_transcriber(language: str, cfg: Config, prompt: str | None = None) -> Transcriber:
    """Build (and download on first use) the recognizer configured for ``language``."""
    backend = cfg.backend_for(language)
    override = cfg.models.get(backend)
    try:
        if backend == "gigaam":
            from .gigaam import GigaAMTranscriber

            return GigaAMTranscriber(override, device=cfg.device)
        if backend == "parakeet":
            from .parakeet import ParakeetTranscriber

            return ParakeetTranscriber(override)
        if backend == "whisper":
            from .whisper import WhisperTranscriber

            return WhisperTranscriber(language, override, prompt=prompt)
    except ImportError as e:
        raise MissingBackend(backend) from e
    raise ValueError(f"unknown recognizer {backend!r} (known: {', '.join(BACKENDS)})")
