"""The glossary: terms to fix and how people actually pronounce them.

Two parts. diga ships about 30 common developer terms (``data/glossary.builtin.yaml``), which
always apply and are updated with diga. Your own file, ``~/.config/diga/glossary.yaml``, starts
as a short template (``data/glossary.template.yaml``) and holds only your terms; a term in both
gets the variants of both, and ``use_builtin: false`` in your file turns the built-in part off.

``glossary.yaml``::

    terms:
      - term: git
        pron_variants: {ru: [гит, гид]}        # per language…
      - term: Kubernetes
        pron_variants: [кубернетес, кубер]     # …or one list for every language

The file is re-read automatically when it changes, so edits apply to the next dictation.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml

log = logging.getLogger(__name__)
ALL_LANGUAGES = "*"


@dataclass(frozen=True)
class Term:
    term: str
    variants: dict[str, tuple[str, ...]] = field(default_factory=dict)  # language → variants

    def variants_for(self, *languages: str) -> tuple[str, ...]:
        out: tuple[str, ...] = ()
        for lang in (*languages, ALL_LANGUAGES):
            out += self.variants.get(lang, ())
        return out


def parse_glossary(doc: dict) -> list[Term]:
    terms: list[Term] = []
    for entry in (doc or {}).get("terms") or []:
        term = str(entry.get("term") or "").strip()
        if not term:
            raise ValueError(f"glossary entry without 'term': {entry!r}")
        raw = entry.get("pron_variants") or []
        if isinstance(raw, dict):
            variants = {str(k): tuple(str(v) for v in vs or []) for k, vs in raw.items()}
        else:
            variants = {ALL_LANGUAGES: tuple(str(v) for v in raw)}
        terms.append(Term(term, variants))
    return terms


def load_glossary(path: Path) -> list[Term]:
    with path.open(encoding="utf-8") as f:
        return parse_glossary(yaml.safe_load(f) or {})


def _data(name: str) -> str:
    return resources.files("diga").joinpath(f"data/{name}").read_text("utf-8")


def builtin_glossary_text() -> str:
    return _data("glossary.builtin.yaml")


def template_glossary_text() -> str:
    return _data("glossary.template.yaml")


def builtin_terms() -> list[Term]:
    return parse_glossary(yaml.safe_load(builtin_glossary_text()) or {})


def merge_terms(*groups: list[Term]) -> list[Term]:
    """Terms of all groups, in order; a term repeated (any case) gets the variants of all.

    The spelling of the last occurrence wins: your "Github" overrides the built-in "GitHub".
    """
    merged: dict[str, Term] = {}
    for group in groups:
        for t in group:
            key = t.term.casefold()
            old = merged.get(key)
            if old is None:
                merged[key] = t
                continue
            variants = dict(old.variants)
            for lang, vs in t.variants.items():
                variants[lang] = tuple(dict.fromkeys(variants.get(lang, ()) + vs))
            merged[key] = Term(t.term, variants)
    return list(merged.values())


def ensure_glossary(path: Path) -> Path:
    """Create ``path`` from the template if it does not exist yet (an existing file is kept)."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(template_glossary_text(), encoding="utf-8")
        log.info("created %s — add your own terms there", path)
    return path


class GlossaryFile:
    """Built-in terms plus your file, reloaded when the file's modification time changes."""

    def __init__(self, path: Path, builtin: bool = True) -> None:
        self.path = path
        self._builtin = builtin_terms() if builtin else []
        self._mtime: float | None = None
        self.own: list[Term] = []
        self.terms: list[Term] = list(self._builtin)
        self.version = 0  # bumps on every successful reload
        self.refresh()

    def refresh(self) -> bool:
        """Reload if the file changed; True if the terms changed. A broken file keeps the old."""
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            return False
        if mtime == self._mtime:
            return False
        self._mtime = mtime
        try:
            with self.path.open(encoding="utf-8") as f:
                doc = yaml.safe_load(f) or {}
            own = parse_glossary(doc)
        except Exception as e:
            log.warning("glossary reload failed, keeping the previous one: %s", e)
            return False
        use_builtin = doc.get("use_builtin", True) is not False
        self.own = own
        self.terms = merge_terms(self._builtin if use_builtin else [], own)
        self.version += 1
        log.info("glossary: %d terms (%d of them yours)", len(self.terms), len(own))
        return True
