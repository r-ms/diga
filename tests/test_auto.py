"""The ``auto`` language: Parakeet detects, GigaAM re-hears Russian chunks — no models needed."""

from __future__ import annotations

import numpy as np

from diga.asr.auto import AutoTranscriber
from diga.asr.base import Transcript, Word
from diga.terms import ByLanguage

AUDIO = np.zeros(16_000, dtype=np.float32)


def transcript(spec: str) -> Transcript:
    """'Обнови:0.99 Макрус:0.6' → a Transcript with those words and confidences."""
    words = []
    for i, item in enumerate(spec.split()):
        text, _, conf = item.partition(":")
        words.append(Word(text, 0.3 * i, 0.3 * i + 0.25, float(conf or 1)))
    return Transcript(" ".join(w.text for w in words), tuple(words))


class Fake:
    def __init__(self, name: str, result: Transcript) -> None:
        self.name, self._result, self.calls = name, result, 0

    def transcribe(self, audio: np.ndarray) -> Transcript:
        self.calls += 1
        return self._result

    def warmup(self) -> None:
        pass


def test_latin_chunks_come_straight_from_the_detector():
    parakeet = Fake("parakeet", transcript("Let's ship it"))
    gigaam = Fake("gigaam", transcript("Летс шип ит"))
    out = AutoTranscriber(parakeet, gigaam).transcribe(AUDIO)
    assert out.text == "Let's ship it" and out.language is None
    assert gigaam.calls == 0  # English and Portuguese cost nothing extra


def test_portuguese_with_accents_is_not_mistaken_for_russian():
    parakeet = Fake("parakeet", transcript("Amanhã faço o deploy à tarde"))
    gigaam = Fake("gigaam", transcript("Аманья фасу"))
    assert AutoTranscriber(parakeet, gigaam).transcribe(AUDIO).text.startswith("Amanhã")
    assert gigaam.calls == 0


def test_cyrillic_chunks_go_to_gigaam_with_parakeet_as_second_opinion():
    parakeet = Fake("parakeet", transcript("Обнови:0.99 Макос:0.9 сейчас:0.99"))
    gigaam = Fake("gigaam", transcript("Обнови:0.99 Макрус:0.6 сейчас:0.99"))
    out = AutoTranscriber(parakeet, gigaam).transcribe(AUDIO)
    assert out.text == "Обнови Макос сейчас" and out.language == "ru"
    assert parakeet.calls == 1 and gigaam.calls == 1  # Parakeet's answer is reused


def test_language_model_judge_is_used_for_russian_chunks():
    parakeet = Fake("parakeet", transcript("Давай:0.99 попробуем:0.99 maybe:0.9 small:0.9 куски"))
    gigaam = Fake("gigaam", transcript("Давай:0.99 попробуем:0.99 maby:0.95 Смоу:0.93 куски"))
    judge = lambda s: -2.0 if "maybe small" in s else -6.0  # noqa: E731
    out = AutoTranscriber(parakeet, gigaam, judge=judge).transcribe(AUDIO)
    assert out.text == "Давай попробуем maybe small куски" and out.language == "ru"


def test_a_mostly_english_chunk_stays_with_the_detector():
    # More Latin than Cyrillic letters: Parakeet already wrote it well, GigaAM is not asked
    parakeet = Fake("parakeet", transcript("Сделай pull request и code review"))
    gigaam = Fake("gigaam", transcript("Сделай пул-реквест и коуд ревью"))
    assert AutoTranscriber(parakeet, gigaam).transcribe(AUDIO).language is None
    assert gigaam.calls == 0


def test_without_second_opinion_gigaam_alone_decides_russian():
    parakeet = Fake("parakeet", transcript("Обнови:0.99 Макос:0.9"))
    gigaam = Fake("gigaam", transcript("Обнови:0.99 Макрус:0.6"))
    out = AutoTranscriber(parakeet, gigaam, second_opinion=False).transcribe(AUDIO)
    assert out.text == "Обнови Макрус" and out.language == "ru"


class Marker:
    def __init__(self, tag: str) -> None:
        self.tag = tag

    @property
    def language(self) -> str:
        return self.tag

    def correct(self, audio: np.ndarray, transcript: Transcript) -> str:
        return f"{self.tag}:{transcript.text}"


def test_by_language_routes_russian_chunks_to_the_russian_corrector():
    fix = ByLanguage(Marker("auto"), ru=Marker("ru"))
    assert fix.correct(AUDIO, Transcript("пуш в гит", language="ru")) == "ru:пуш в гит"
    assert fix.correct(AUDIO, Transcript("push to git")) == "auto:push to git"
    assert fix.language == "auto"


class Switching(Fake):
    """A detector whose answers change from call to call."""

    def __init__(self, *results: Transcript) -> None:
        super().__init__("parakeet", results[0])
        self._results = list(results)

    def transcribe(self, audio: np.ndarray) -> Transcript:
        self.calls += 1
        return self._results.pop(0)


def test_after_a_russian_chunk_gigaam_starts_early_and_is_dropped_if_not_needed():
    ru = transcript("Обнови:0.99 систему:0.99")
    parakeet = Switching(ru, ru, transcript("Now in English"))
    gigaam = Fake("gigaam", ru)
    auto = AutoTranscriber(parakeet, gigaam)
    assert auto.transcribe(AUDIO).language == "ru"  # first chunk: one after the other
    assert gigaam.calls == 1
    assert auto.transcribe(AUDIO).language == "ru"  # second: GigaAM started in parallel
    assert gigaam.calls == 2
    english = auto.transcribe(AUDIO)  # third: GigaAM started early, but it is English
    assert english.text == "Now in English" and english.language is None
    auto._pool.shutdown(wait=True)
    assert gigaam.calls == 3  # the early run happened; its result was dropped
