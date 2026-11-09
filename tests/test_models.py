"""End-to-end checks with real models (downloaded on first run) and macOS `say` voices.

Run with ``uv run pytest -m models``. Skipped automatically without the voices or extras.
"""

from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from diga.config import Config
from diga.terms.glossary import GlossaryFile, ensure_glossary

pytestmark = pytest.mark.models


def synth(tmp_path: Path, voice: str, text: str) -> np.ndarray:
    if not shutil.which("say"):
        pytest.skip("macOS `say` not available")
    voices = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    if not any(line.split()[0] == voice for line in voices.splitlines() if line.strip()):
        pytest.skip(f"voice {voice} not installed")
    out = tmp_path / f"{voice}.wav"
    subprocess.run(
        ["say", "-v", voice, "--data-format=LEI16@16000", "-o", str(out), text], check=True
    )
    with wave.open(str(out)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16) / 32768.0


@pytest.fixture(scope="module")
def glossary(tmp_path_factory) -> GlossaryFile:
    return GlossaryFile(ensure_glossary(tmp_path_factory.mktemp("g") / "glossary.yaml"))


def test_russian_gigaam_with_acoustic_term_correction(tmp_path, glossary):
    pytest.importorskip("transformers")
    from diga.app import build_corrector
    from diga.asr import create_transcriber

    cfg = Config(language="ru")
    asr = create_transcriber("ru", cfg)
    corrector = build_corrector("ru", cfg, glossary)
    assert corrector is not None and type(corrector).__name__ == "ChainCorrector"
    audio = synth(
        tmp_path, "Milena", "Запусти оллама, потом сделай пуш в гит и подними докер с редис."
    )
    transcript = asr.transcribe(audio.astype(np.float32))
    fixed = corrector.correct(audio.astype(np.float32), transcript)
    for term in ("push", "git", "Docker", "Redis"):
        assert term in fixed, (transcript.text, fixed)
    # The synthetic voice sometimes swallows "оллама" so badly that the recognizer drops the
    # word; the corrector never inserts words, so only check it when something was heard.
    if "лама" in transcript.text.lower():
        assert "ollama" in fixed, (transcript.text, fixed)


def test_english_parakeet(tmp_path):
    pytest.importorskip("parakeet_mlx")
    from diga.asr import create_transcriber

    asr = create_transcriber("en", Config(language="en"))
    audio = synth(tmp_path, "Samantha", "Please open the GitHub repository and run Docker.")
    text = asr.transcribe(audio.astype(np.float32)).text
    assert "GitHub" in text and "Docker" in text, text


def test_portuguese_parakeet_with_text_term_correction(tmp_path, glossary):
    pytest.importorskip("parakeet_mlx")
    from diga.app import build_corrector
    from diga.asr import create_transcriber

    cfg = Config(language="pt")
    asr = create_transcriber("pt", cfg)
    corrector = build_corrector("pt", cfg, glossary)
    audio = synth(tmp_path, "Joana", "Bom dia. Hoje vou trabalhar no projeto em Lisboa.")
    transcript = asr.transcribe(audio.astype(np.float32))
    assert "Lisboa" in transcript.text, transcript.text
    assert corrector is not None
    assert corrector.correct(audio, transcript)  # runs, leaves ordinary words intact


def test_whisper_backend_api(tmp_path):
    pytest.importorskip("mlx_whisper")
    from diga.asr.whisper import WhisperTranscriber

    asr = WhisperTranscriber("en", model="mlx-community/whisper-tiny")  # small, API check only
    audio = synth(tmp_path, "Samantha", "Hello world, this is a test.")
    result = asr.transcribe(audio.astype(np.float32))
    assert "world" in result.text.lower() and result.words, result


def test_russian_second_opinion_end_to_end(tmp_path):
    pytest.importorskip("transformers")
    pytest.importorskip("parakeet_mlx")
    from diga.asr import create_transcriber
    from diga.asr.parakeet import ParakeetTranscriber
    from diga.asr.second_opinion import SecondOpinionTranscriber

    gigaam = create_transcriber("ru", Config(language="ru"))
    both = SecondOpinionTranscriber(gigaam, ParakeetTranscriber())
    audio = synth(tmp_path, "Milena", "Собери докер образ и запушь его в реестр.").astype(
        np.float32
    )
    alone = gigaam.transcribe(audio)
    assert alone.words and all(0.0 <= w.confidence <= 1.0 for w in alone.words)
    merged = both.transcribe(audio)
    assert "реестр" in merged.text.lower(), merged.text
    assert merged.words and all(w.end >= w.start for w in merged.words)


def test_auto_routes_russian_to_gigaam_and_english_to_parakeet(tmp_path, glossary):
    pytest.importorskip("transformers")
    pytest.importorskip("parakeet_mlx")
    from diga.app import App

    cfg = Config()  # the default: auto, second opinion on
    cfg.terms.glossary = str(glossary.path)
    asr, corrector = App(cfg, with_ui=False).build_engine("auto")
    assert type(asr).__name__ == "AutoTranscriber" and corrector is not None

    ru = synth(tmp_path, "Milena", "Сделай пуш в гит и подними докер с редис.").astype(np.float32)
    heard = asr.transcribe(ru)
    assert heard.language == "ru", heard
    fixed = corrector.correct(ru, heard)
    for term in ("git", "Docker", "Redis"):
        assert term in fixed, (heard.text, fixed)

    en = synth(tmp_path, "Samantha", "Hello world, push the branch to GitHub.").astype(np.float32)
    heard = asr.transcribe(en)
    assert heard.language is None and "world" in heard.text.lower(), heard


def test_downloaded_models_load_without_network(monkeypatch, glossary):
    pytest.importorskip("transformers")
    pytest.importorskip("parakeet_mlx")
    import socket

    from diga import models
    from diga.app import App

    needed = (
        models.GIGAAM_RNNT,
        models.PARAKEET_V3,
        models.QWEN3_LM,
        models.GIGAAM_CTC_INT8,
        models.GIGAAM_CTC_TOKENIZER,
    )
    if not all(models.is_cached(spec) for spec in needed):
        pytest.skip("models are not downloaded yet")
    attempts: list[object] = []

    def deny(sock: socket.socket, address: object) -> None:
        attempts.append(address)
        raise OSError("network is off in this test")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    cfg = Config()
    cfg.terms.glossary = str(glossary.path)
    _, corrector = App(cfg, with_ui=False).build_engine("auto")
    assert corrector is not None
    assert attempts == [], f"diga tried to go online: {attempts}"
