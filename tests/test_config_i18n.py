from __future__ import annotations

import re

import pytest

from diga import i18n
from diga.asr.base import words_from_tokens
from diga.config import load_config
from diga.terms.glossary import example_glossary_text, parse_glossary


def test_defaults_need_no_choices_and_yaml_overrides_them(isolated_config):
    cfg = load_config()
    assert cfg.language == "auto" and cfg.second_opinion and cfg.send_return_after_hold
    isolated_config.mkdir(parents=True)
    (isolated_config / "config.yaml").write_text(
        "language: en\nchunking: {min_chunk_s: 8}\nbackends: {de: whisper}\n", encoding="utf-8"
    )
    cfg = load_config()
    assert cfg.language == "en" and cfg.chunking.min_chunk_s == 8
    assert cfg.chunking.max_chunk_s == 20  # untouched default
    assert cfg.backend_for("de") == "whisper" and cfg.backend_for("ru") == "gigaam"


def test_unknown_keys_are_ignored_with_a_warning(isolated_config, caplog):
    isolated_config.mkdir(parents=True)
    (isolated_config / "config.yaml").write_text("colour: blue\n", encoding="utf-8")
    load_config()
    assert "unknown setting 'colour'" in caplog.text


def test_every_language_has_every_string_with_the_same_placeholders():
    english = i18n.STRINGS["en"]
    for lang, strings in i18n.STRINGS.items():
        assert set(strings) == set(english), lang
        for key, text in strings.items():
            assert set(re.findall(r"{(\w+)", text)) == set(re.findall(r"{(\w+)", english[key])), (
                lang,
                key,
            )


def test_ui_language_falls_back_to_english():
    i18n.set_language("pt")
    assert i18n.t("menu.quit") == "Sair"
    i18n.set_language("en")
    assert i18n.t("menu.quit") == "Quit"


def test_example_glossary_is_valid():
    terms = parse_glossary(__import__("yaml").safe_load(example_glossary_text()))
    assert len(terms) > 10 and any(t.term == "GitHub" for t in terms)


def test_words_from_tokens_groups_subwords():
    tokens = [(" Hel", 0.0, 0.1), ("lo", 0.1, 0.2), (" world", 0.3, 0.5), (".", 0.5, 0.55)]
    words = words_from_tokens(tokens)
    assert [(w.text, w.start, w.end) for w in words] == [("Hello", 0.0, 0.2), ("world.", 0.3, 0.55)]


def test_language_model_is_left_out_on_small_macs(monkeypatch):
    import diga.config as config

    cfg = config.Config()
    monkeypatch.setattr(config, "memory_gb", lambda: 8.0)
    assert not cfg.use_language_model()
    monkeypatch.setattr(config, "memory_gb", lambda: 16.0)
    assert cfg.use_language_model()
    cfg.second_opinion_lm = False  # set in config.yaml: always wins
    assert not cfg.use_language_model()


def test_progress_bars_do_not_leave_a_semaphore_behind():
    tqdm = pytest.importorskip("tqdm").tqdm
    import multiprocessing.synchronize

    from diga.cli import _thread_lock_for_progress_bars

    _thread_lock_for_progress_bars()
    assert not isinstance(tqdm.get_lock(), multiprocessing.synchronize.SemLock)
    assert not hasattr(tqdm.get_lock(), "mp_lock")
