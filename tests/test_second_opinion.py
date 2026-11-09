"""Merging two recognizers by word confidence — no models needed."""

from __future__ import annotations

import numpy as np

from diga.asr.base import Transcript, Word
from diga.asr.second_opinion import SecondOpinionTranscriber, merge


def words(spec: str, start: float = 0.0) -> list[Word]:
    """'Собери:0.9 докер:0.6' → Words 0.3 s apart with the given confidences."""
    out = []
    for i, item in enumerate(spec.split()):
        text, _, conf = item.partition(":")
        out.append(Word(text, start + 0.3 * i, start + 0.3 * i + 0.25, float(conf or 1)))
    return out


def text(ws: list[Word]) -> str:
    return " ".join(w.text for w in ws)


def test_agreement_is_kept():
    g = words("Подними:0.99 докер:0.95 с:0.99 редисом:0.97")
    p = words("Подними:0.9 докер:0.9 с:0.9 редисом:0.9")
    assert merge(g, p) == g


def test_unsure_primary_words_are_replaced_by_a_more_confident_secondary():
    g = words("Соберидоробрас:0.75 и:0.85 запусти:0.7 его:0.99 в:0.99 реестр:0.99")
    p = words("Собери:0.99 докер:0.95 образ:0.99 и:0.99 запуши:0.86 его:0.99 в:0.99 реестр:0.99")
    assert text(merge(g, p)) == "Собери докер образ и запуши его в реестр"


def test_confident_primary_wins_a_disagreement():
    g = words("Обнови:0.99 макос:0.95")
    p = words("Обнови:0.99 Макрус:0.99")
    assert text(merge(g, p)) == "Обнови макос"


def test_less_confident_secondary_does_not_replace():
    g = words("Обнови:0.99 Макрус:0.6")
    p = words("Обнови:0.99 Мокус:0.5")
    assert text(merge(g, p)) == "Обнови Макрус"


def test_word_dropped_by_primary_is_inserted_when_secondary_is_sure():
    g = words("Сравни:0.99 ответы:0.99 двух:0.99 моделей:0.99")
    p = words("Сравни:0.99 ответы:0.99 двух:0.99 Ллм:0.9 моделей:0.99")
    assert text(merge(g, p)) == "Сравни ответы двух Ллм моделей"


def test_unsure_insertion_is_ignored():
    g = words("Сравни:0.99 ответы:0.99")
    p = words("Сравни:0.99 эм:0.5 ответы:0.99")
    assert text(merge(g, p)) == "Сравни ответы"


def test_punctuation_and_case_do_not_count_as_disagreement():
    g = words("проверь,:0.7 что:0.99 работает.:0.99")
    p = words("Проверь:0.99 что:0.99 работает:0.99")
    assert merge(g, p) == g  # same words: the primary's spelling and punctuation stay


class Fake:
    def __init__(self, name: str, result: Transcript | Exception) -> None:
        self.name, self._result = name, result

    def transcribe(self, audio: np.ndarray) -> Transcript:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result

    def warmup(self) -> None:
        pass


def test_transcriber_merges_and_falls_back_when_the_second_fails():
    g = Transcript("Обнови Макрус", tuple(words("Обнови:0.99 Макрус:0.6")))
    p = Transcript("Обнови Макос", tuple(words("Обнови:0.99 Макос:0.9")))
    both = SecondOpinionTranscriber(Fake("gigaam", g), Fake("parakeet", p))
    assert both.name == "gigaam+parakeet"
    assert both.transcribe(np.zeros(16_000)).text == "Обнови Макос"
    broken = SecondOpinionTranscriber(Fake("gigaam", g), Fake("parakeet", RuntimeError("oom")))
    assert broken.transcribe(np.zeros(16_000)).text == "Обнови Макрус"


# --- with a language model as the judge -------------------------------------------------


def judge_preferring(*good_phrases: str):
    """Fake language model: sentences containing one of ``good_phrases`` score higher."""
    calls: list[str] = []

    def judge(sentence: str) -> float:
        calls.append(sentence)
        return -2.0 if any(g in sentence for g in good_phrases) else -6.0

    judge.calls = calls  # type: ignore[attr-defined]
    return judge


def test_judge_overrides_a_confident_but_nonsense_primary_word():
    # GigaAM was acoustically sure of "Смоу"; the confidence rule alone would keep it
    g = words("попробуем:0.99 maby:0.95 Смоу:0.93 кусочки:0.99")
    p = words("попробуем:0.99 maybe:0.9 small:0.9 кусочки:0.99")
    assert text(merge(g, p)) == "попробуем maby Смоу кусочки"
    judged = merge(g, p, judge=judge_preferring("maybe small"))
    assert text(judged) == "попробуем maybe small кусочки"


def test_judge_protects_correct_primary_words():
    # GigaAM unsure but right; Parakeet confident but wrong: the confidence rule would swap
    g = words("Посмотри:0.99 логи:0.7 Редиса:0.7")
    p = words("Посмотри:0.99 логер:0.9 Диса:0.9")
    assert text(merge(g, p)) == "Посмотри логер Диса"
    judged = merge(g, p, judge=judge_preferring("логи Редиса"))
    assert text(judged) == "Посмотри логи Редиса"


def test_judge_reads_the_whole_sentence_in_context():
    j = judge_preferring("Макос")
    g = words("Обнови:0.99 Макрус:0.6 сейчас:0.99")
    p = words("Обнови:0.99 Макос:0.9 сейчас:0.99")
    assert text(merge(g, p, judge=j)) == "Обнови Макос сейчас"
    assert "Обнови Макрус сейчас" in j.calls and "Обнови Макос сейчас" in j.calls


def test_without_a_clear_preference_confidence_decides():
    g = words("Обнови:0.99 Макрус:0.6")
    p = words("Обнови:0.99 Макос:0.9")
    undecided = merge(g, p, judge=lambda s: -4.0)
    assert text(undecided) == "Обнови Макос"  # same as without the judge


def test_judge_does_not_pull_in_very_unsure_secondary_words():
    g = words("попробуем:0.99 Смоу:0.93")
    p = words("попробуем:0.99 small:0.3")  # the judge likes it, but Parakeet barely heard it
    assert text(merge(g, p, judge=judge_preferring("small"))) == "попробуем Смоу"
