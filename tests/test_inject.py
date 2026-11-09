"""Splitting text into key events — no keyboard needed."""

from __future__ import annotations

from diga.inject import MAX_UNITS_PER_EVENT, pieces


def test_long_text_goes_out_in_pieces_of_at_most_20_units():
    text = "Сделай пуш в гит и подними докер с редисом, потом проверь логи." * 3
    out = pieces(text)
    assert "".join(out) == text
    assert all(len(p.encode("utf-16-le")) // 2 <= MAX_UNITS_PER_EVENT for p in out)
    assert len(out) == -(-len(text) // MAX_UNITS_PER_EVENT)  # as few events as possible


def test_emoji_is_never_split_in_half():
    text = "a" * 19 + "😀" + "b"  # the emoji takes two UTF-16 units and would straddle 20
    out = pieces(text)
    assert out == ["a" * 19, "😀b"]
