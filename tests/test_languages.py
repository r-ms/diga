"""Which languages you dictate in: from the settings, or read off this Mac."""

from __future__ import annotations

import numpy as np

from diga import system
from diga.asr.auto import AutoTranscriber
from diga.asr.base import Transcript
from diga.config import Config


def test_language_codes_from_macos_tags_and_keyboard_layouts():
    assert system.code("ru-AM") == "ru" and system.code("pt_PT") == "pt"
    assert system.layout_language("Russian - Phonetic") == "ru"
    assert system.layout_language("ABC") == "en" and system.layout_language("Portuguese") == "pt"
    assert system.layout_language("Dvorak") is None


def test_preferred_languages_come_first_then_keyboards_without_repeats():
    langs = system.mac_languages(["en-AM", "pt-PT"], ["ABC", "Russian", "Portuguese"])
    assert langs == ["en", "pt", "ru"]


def test_your_list_wins_over_what_the_mac_shows(monkeypatch):
    monkeypatch.setattr(system, "mac_languages", lambda: ["en"])
    assert Config().spoken_languages() == (["en"], "macOS")
    assert not Config().wants_russian()  # an English-only Mac
    mine = Config(languages=["ru", "EN"])
    assert mine.spoken_languages() == (["ru", "en"], "config") and mine.wants_russian()
    assert Config(language="ru", languages=["en"]).wants_russian()  # `language: ru` is explicit


class Fake:
    def __init__(self, name: str, text: str) -> None:
        self.name, self._text = name, text

    def transcribe(self, audio: np.ndarray) -> Transcript:
        return Transcript(self._text)

    def warmup(self) -> None:
        pass


def test_without_russian_parakeet_keeps_russian_chunks_and_hints_once():
    hints: list[str] = []
    auto = AutoTranscriber(
        Fake("parakeet", "Привет, как дела"), None, on_russian_unhandled=lambda: hints.append("x")
    )
    for _ in range(3):
        assert auto.transcribe(np.zeros(10, dtype=np.float32)).text == "Привет, как дела"
    assert hints == ["x"]
