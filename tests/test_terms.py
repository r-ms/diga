"""Term correction without models: synthetic CTC log-probs and fake recognizer output."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from diga.asr.base import Transcript, Word
from diga.terms.acoustic import AcousticCorrector, spellings
from diga.terms.fuzzy import FuzzyCorrector
from diga.terms.glossary import GlossaryFile, parse_glossary
from diga.terms.spans import Replacement, apply_replacements
from diga.terms.spotter import Trie, spot

BLANK = 255


class CharTokenizer:
    """One token per character; ids assigned on first sight."""

    def __init__(self) -> None:
        self.ids: dict[str, int] = {}

    def encode(self, text: str) -> list[int]:
        return [self.ids.setdefault(c, len(self.ids)) for c in text]


def emit(tok: CharTokenizer, text: str, at: int, n_frames: int = 60) -> np.ndarray:
    """Log-probs where ``text`` is spoken one character per frame from frame ``at``."""
    logits = np.zeros((n_frames, BLANK + 1), dtype=np.float32)
    logits[:, BLANK] = 10.0
    for i, tid in enumerate(tok.encode(text)):
        logits[at + i, BLANK] = 0.0
        logits[at + i, tid] = 10.0
    return logits - np.log(np.exp(logits).sum(axis=1, keepdims=True))


class FakeCtc:
    frame_s = 0.04
    blank_id = BLANK
    language = "ru"

    def __init__(self, log_probs: np.ndarray, tok: CharTokenizer) -> None:
        self._lp, self._tok = log_probs, tok

    def encode(self, text: str) -> list[int]:
        return self._tok.encode(text)

    def log_probs(self, audio: np.ndarray) -> np.ndarray:
        return self._lp


def glossary_file(tmp_path: Path, text: str) -> GlossaryFile:
    path = tmp_path / "glossary.yaml"
    path.write_text(text, encoding="utf-8")
    return GlossaryFile(path)


GLOSSARY = """
terms:
  - term: GitLab
    pron_variants: {ru: [гитлаб, гит лаб], en: [get lab, git lab]}
  - term: commit
    pron_variants: {ru: [коммит], pt: [cômite, comite]}
  - term: Docker
    pron_variants: [докер]
"""


# --- applying replacements -------------------------------------------------------------


def test_multi_word_span_becomes_one_term_keeping_punctuation():
    # the old code skipped every replacement whose word count differed ("гит лаб" → GitLab)
    words = ["Открой", "гит", "лаб,", "потом"]
    assert apply_replacements(words, [Replacement(1, 2, "GitLab")]) == "Открой GitLab, потом"


def test_one_word_can_become_a_multi_word_term():
    words = ["Запусти", "клодкод."]
    assert apply_replacements(words, [Replacement(1, 1, "Claude Code")]) == "Запусти Claude Code."


def test_overlapping_replacements_first_wins():
    words = ["a", "b", "c"]
    reps = [Replacement(0, 2, "X"), Replacement(1, 2, "Y")]
    assert apply_replacements(words, reps) == "X c"


# --- acoustic spotting -------------------------------------------------------------------


def test_spotter_finds_term_where_it_was_said():
    tok = CharTokenizer()
    trie = Trie([["докер"]], tok.encode, BLANK)
    spots = spot(emit(tok, "докер", at=20), trie, ctc_weight=0.5)
    assert len(spots) == 1
    assert spots[0].entry == 0 and spots[0].frame_start == 20 and spots[0].frame_end == 24


def test_spotter_silent_audio_has_no_spots():
    tok = CharTokenizer()
    trie = Trie([["докер"]], tok.encode, BLANK)
    assert spot(emit(tok, "", at=0), trie) == []


def test_acoustic_corrector_replaces_two_recognized_words(tmp_path):
    tok = CharTokenizer()
    for s in ("гитлаб",):  # make sure the ids exist before building log-probs
        tok.encode(s)
    lp = emit(tok, "гитлаб", at=12)  # spoken at 0.48–0.72 s
    corrector = AcousticCorrector(FakeCtc(lp, tok), glossary_file(tmp_path, GLOSSARY))
    transcript = Transcript(
        "Открой гит лаб сейчас",
        (
            Word("Открой", 0.0, 0.4),
            Word("гит", 0.48, 0.6),
            Word("лаб", 0.62, 0.76),
            Word("сейчас", 1.2, 1.6),
        ),
    )
    assert corrector.correct(np.zeros(16_000), transcript) == "Открой GitLab сейчас"


def test_acoustic_corrector_leaves_correct_text_alone(tmp_path):
    tok = CharTokenizer()
    lp = emit(tok, "докер", at=5)
    corrector = AcousticCorrector(FakeCtc(lp, tok), glossary_file(tmp_path, GLOSSARY))
    transcript = Transcript("Docker готов", (Word("Docker", 0.2, 0.5), Word("готов", 0.6, 0.9)))
    assert corrector.correct(np.zeros(16_000), transcript) == "Docker готов"


def test_russian_spellings_include_transliteration():
    s = spellings("ollama", ("оллама",), "ru")
    assert "ollama" in s and "оллама" in s and "оллама".capitalize() in s
    assert any(x.startswith("олл") for x in s)


# --- text-only matching --------------------------------------------------------------------


def test_fuzzy_fixes_portuguese_misrecognition(tmp_path):
    fixer = FuzzyCorrector(glossary_file(tmp_path, GLOSSARY), "pt")
    out = fixer.correct(np.zeros(1), Transcript("Preciso fazer um cômite no GitLab"))
    assert out == "Preciso fazer um commit no GitLab"


def test_fuzzy_joins_split_english_term(tmp_path):
    fixer = FuzzyCorrector(glossary_file(tmp_path, GLOSSARY), "en")
    out = fixer.correct(np.zeros(1), Transcript("open the get lab project"))
    assert out == "open the GitLab project"


def test_fuzzy_does_not_touch_ordinary_words(tmp_path):
    fixer = FuzzyCorrector(glossary_file(tmp_path, GLOSSARY), "en")
    text = "I will commit to the plan and get back to you"
    assert fixer.correct(np.zeros(1), Transcript(text)) == text


# --- glossary -------------------------------------------------------------------------------


def test_glossary_list_applies_to_every_language():
    (docker,) = [
        t for t in parse_glossary({"terms": [{"term": "Docker", "pron_variants": ["докер"]}]})
    ]
    assert docker.variants_for("ru") == ("докер",) and docker.variants_for("pt") == ("докер",)


def test_glossary_entry_without_term_is_an_error():
    with pytest.raises(ValueError):
        parse_glossary({"terms": [{"pron_variants": ["x"]}]})


def test_glossary_reloads_and_survives_a_broken_file(tmp_path):
    g = glossary_file(tmp_path, GLOSSARY)
    assert [t.term for t in g.terms] == ["GitLab", "commit", "Docker"]
    import os
    import time

    g.path.write_text("terms:\n  - term: Redis\n", encoding="utf-8")
    os.utime(g.path, (time.time() + 5, time.time() + 5))
    assert g.refresh() and [t.term for t in g.terms] == ["Redis"]
    g.path.write_text("terms: [ {", encoding="utf-8")  # broken YAML
    os.utime(g.path, (time.time() + 10, time.time() + 10))
    assert not g.refresh() and [t.term for t in g.terms] == ["Redis"]


def test_chain_feeds_each_corrector_the_previous_output():
    from diga.terms import ChainCorrector

    class Upper:
        language = "ru"

        def correct(self, audio, transcript):
            return transcript.text.upper()

    class Exclaim:
        language = "ru"

        def correct(self, audio, transcript):
            assert transcript.words == ()  # later correctors work on text only
            return transcript.text + "!"

    chain = ChainCorrector(Upper(), Exclaim())
    assert chain.correct(np.zeros(1), Transcript("git")) == "GIT!"
    assert chain.language == "ru"


# --- auto mode: glossary languages chosen per chunk by alphabet ---------------------------


AUTO_GLOSSARY = """
terms:
  - term: Python
    pron_variants: {ru: [пайтон, пайтоне]}
  - term: GitLab
    pron_variants: {en: [get lab], pt: [guit lab]}
  - term: commit
    pron_variants: {pt: [cômite]}
"""


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Напиши тест на пайтоне", "Напиши тест на Python"),  # Cyrillic → ru variants
        ("open the get lab project", "open the GitLab project"),  # Latin → en variants
        ("vou fazer um cômite agora", "vou fazer um commit agora"),  # Latin → pt variants
    ],
)
def test_auto_mode_picks_glossary_languages_by_alphabet(tmp_path, text, expected):
    fixer = FuzzyCorrector(glossary_file(tmp_path, AUTO_GLOSSARY), "auto")
    assert fixer.correct(np.zeros(1), Transcript(text)) == expected


def test_auto_mode_does_not_apply_latin_variants_to_russian(tmp_path):
    # "get lab" is an English mishearing; Russian text must not be matched against it
    fixer = FuzzyCorrector(glossary_file(tmp_path, AUTO_GLOSSARY), "auto")
    text = "Сделай гет лаб тест"
    assert fixer.correct(np.zeros(1), Transcript(text)) == text


def test_dominant_script():
    from diga.terms.text import dominant_script

    assert dominant_script("Открой GitHub и сделай пуш") == "cyrillic"
    assert dominant_script("Abre o GitHub e faz o commit") == "latin"


def test_short_words_are_only_replaced_by_an_exact_listed_spelling(tmp_path):
    # "code" is one letter away from the listed "clóde" (Claude) but is a word of its own
    glossary = glossary_file(
        tmp_path,
        "terms:\n"
        "  - term: Claude\n"
        "    pron_variants: {en: [cloud, clod], pt: [clóde]}\n"
        "  - term: Claude Code\n"
        "    pron_variants: {en: [cloud code]}\n",
    )
    fixer = FuzzyCorrector(glossary, "auto")
    assert fixer.correct(np.zeros(1), Transcript("make a pull request and code review")) == (
        "make a pull request and code review"
    )
    assert fixer.correct(np.zeros(1), Transcript("ask clod about it")) == "ask Claude about it"


def test_short_transliterations_still_match_across_alphabets(tmp_path):
    glossary = glossary_file(tmp_path, "terms:\n  - term: vLLM\n    pron_variants: {ru: [вилм]}\n")
    fixer = FuzzyCorrector(glossary, "ru")
    assert fixer.correct(np.zeros(1), Transcript("Запусти вил")) == "Запусти vLLM"


def test_a_term_that_is_already_right_is_left_alone(tmp_path):
    glossary = glossary_file(
        tmp_path,
        "terms:\n"
        "  - term: Claude\n"
        "    pron_variants: {en: [cloud, clod, code]}\n"
        "  - term: Claude Code\n"
        "    pron_variants: {en: [cloud code]}\n",
    )
    fixer = FuzzyCorrector(glossary, "en")
    assert fixer.correct(np.zeros(1), Transcript("open Claude Code now")) == "open Claude Code now"
    assert fixer.correct(np.zeros(1), Transcript("ask cloud code")) == "ask Claude Code"


class CountingCtc(FakeCtc):
    def __init__(self, log_probs: np.ndarray, tok: CharTokenizer) -> None:
        super().__init__(log_probs, tok)
        self.runs = 0

    def log_probs(self, audio: np.ndarray) -> np.ndarray:
        self.runs += 1
        return super().log_probs(audio)


def test_acoustic_model_starts_before_recognition_ends_and_runs_once(tmp_path):
    from diga.terms import ChainCorrector, prefetch

    tok = CharTokenizer()
    tok.encode("гитлаб")
    ctc = CountingCtc(emit(tok, "гитлаб", at=12), tok)
    corrector = ChainCorrector(
        AcousticCorrector(ctc, glossary_file(tmp_path, GLOSSARY)),
        FuzzyCorrector(glossary_file(tmp_path, GLOSSARY), "ru"),
    )
    audio = np.zeros(16_000)
    prefetch(corrector, audio)  # the recorder does this before transcribing
    transcript = Transcript(
        "Открой гит лаб",
        (Word("Открой", 0.0, 0.4), Word("гит", 0.48, 0.6), Word("лаб", 0.62, 0.76)),
    )
    assert corrector.correct(audio, transcript) == "Открой GitLab"
    assert ctc.runs == 1
    other = np.zeros(8_000)  # a prefetch for another chunk is not reused by mistake
    prefetch(corrector, other)
    corrector.correct(audio, transcript)
    assert ctc.runs == 3


def test_by_language_prefetches_for_the_language_of_the_previous_chunk():
    from diga.terms import ByLanguage, prefetch

    class Spy:
        def __init__(self, tag: str) -> None:
            self.tag, self.prefetched = tag, 0

        @property
        def language(self) -> str:
            return self.tag

        def prefetch(self, audio: np.ndarray) -> None:
            self.prefetched += 1

        def correct(self, audio: np.ndarray, transcript: Transcript) -> str:
            return transcript.text

    default, ru = Spy("auto"), Spy("ru")
    fix = ByLanguage(default, ru=ru)
    audio = np.zeros(10)
    prefetch(fix, audio)
    assert (default.prefetched, ru.prefetched) == (1, 0)
    fix.correct(audio, Transcript("пуш", language="ru"))
    prefetch(fix, audio)
    assert (default.prefetched, ru.prefetched) == (1, 1)
