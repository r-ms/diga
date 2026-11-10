"""Configuration.

The defaults are meant to be the best choice, so there is nothing to set up. Precedence, lowest
to highest: built-in defaults → ``~/.config/diga/config.yaml`` (optional) →
``~/.config/diga/settings.json`` (what you picked in the menu: key and sound) → command line.
Set ``DIGA_CONFIG_DIR`` to use another directory.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


def config_dir() -> Path:
    return Path(os.environ.get("DIGA_CONFIG_DIR", "~/.config/diga")).expanduser()


SMALL_MAC_GB = 8


def memory_gb() -> float:
    """Physical memory of this Mac."""
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30


@dataclass
class ChunkingConfig:
    min_chunk_s: float = 10.0  # after this much audio, cut at the first pause…
    pause_s: float = 0.25  # …this long
    max_chunk_s: float = 20.0  # no pause by now: cut at the quietest spot (models take ≤25 s)
    max_record_s: float = 600.0  # safety limit for one recording
    min_record_s: float = 0.3  # shorter is an accidental press


@dataclass
class HotkeyConfig:
    key: str = "right_cmd"  # right_cmd | right_option | fn
    hold_s: float = 0.3  # holding right ⌘ longer than this starts recording
    double_tap_s: float = 0.4  # two taps within this toggle a long recording


@dataclass
class TermsConfig:
    enabled: bool = True
    glossary: str = ""  # empty: <config dir>/glossary.yaml, created from the example
    ctc_weight: float = 0.5  # acoustic spotter: per-token bonus for glossary paths
    max_frames_per_token: int = 15
    fuzzy_threshold: float = 0.84  # text matcher: minimum similarity to a listed spelling
    acoustic_min_similarity: float = (
        0.65  # acoustic: spotted term vs the words it replaces (benchmarks/terms.py)
    )
    ctc_precision: str = "int8"  # int8 (225 MB) or fp32 (886 MB); same corrections in our tests


@dataclass
class Config:
    # auto: Parakeet detects the language of every chunk and Russian chunks go to GigaAM
    # (asr/auto.py). Or fix it: ru | en | pt | any Whisper language code.
    language: str = "auto"
    # The languages you dictate in, e.g. [ru, en]. None: what this Mac shows — its preferred
    # languages and keyboard layouts. Russian among them loads the Russian recognizer (GigaAM,
    # ~2 GB); without it Russian speech is left to Parakeet and nothing extra is downloaded.
    languages: list[str] | None = None
    ui_language: str | None = None  # None: follow macOS
    # Show dictated text in the log. None: only in a terminal — not when the log goes to a
    # file (autostart), so your dictation is not kept on disk.
    log_text: bool | None = None
    send_return_after_hold: bool = True
    # soft | tick | drop | chime | off, or a folder with your own start.wav / done.wav
    sounds: str = "soft"
    # Russian: GigaAM and Parakeet both transcribe, a small language model settles where they
    # disagree (asr/second_opinion.py). Off: with `language: ru`, Parakeet is not loaded.
    second_opinion: bool = True
    second_opinion_unsure: float = 0.8  # GigaAM words below this confidence may be replaced
    second_opinion_insert: float = 0.85  # Parakeet words GigaAM dropped are inserted above this
    # A small language model (Qwen3 0.6B, ~0.4 GB of memory) settles disagreements in context.
    # None: on, except on Macs with 8 GB of memory or less, where it is left out.
    second_opinion_lm: bool | None = None
    second_opinion_lm_margin: float = 0.25  # nats per token
    # Which recognizer handles which language; anything else goes to `fallback_backend`.
    backends: dict[str, str] = field(
        default_factory=lambda: {
            "ru": "gigaam",
            "en": "parakeet",
            "pt": "parakeet",
            "auto": "parakeet",
        }
    )
    fallback_backend: str = "whisper"
    # Optional model overrides: backend name → Hugging Face repo or local directory.
    models: dict[str, str] = field(default_factory=dict)
    device: str = "mps"  # mps | cpu (GigaAM only; MLX backends always use the GPU)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    terms: TermsConfig = field(default_factory=TermsConfig)

    def spoken_languages(self) -> tuple[list[str], str]:
        """(language codes, where they came from: "config" or "macOS")."""
        from .system import code, mac_languages

        if self.languages:
            return list(dict.fromkeys(code(str(x)) for x in self.languages)), "config"
        return mac_languages(), "macOS"

    def wants_russian(self) -> bool:
        """Load the Russian recognizer? Always for `language: ru`; in auto, if you speak it."""
        if self.language == "ru":
            return True
        return self.language == "auto" and "ru" in self.spoken_languages()[0]

    def use_language_model(self) -> bool:
        if self.second_opinion_lm is not None:
            return self.second_opinion_lm
        return memory_gb() > SMALL_MAC_GB

    def backend_for(self, language: str) -> str:
        return self.backends.get(language, self.fallback_backend)

    def glossary_path(self) -> Path:
        return (
            Path(self.terms.glossary).expanduser()
            if self.terms.glossary
            else (config_dir() / "glossary.yaml")
        )


MENU_SETTINGS = ("sounds", "hotkey")


def _merge(obj: Any, data: dict[str, Any], where: str) -> None:
    """Copy known keys from ``data`` onto dataclass ``obj``, recursing into nested ones."""
    known = {f.name: f for f in dataclasses.fields(obj)}
    for key, value in data.items():
        if key not in known:
            log.warning("%s: unknown setting %r ignored", where, key)
            continue
        current = getattr(obj, key)
        if dataclasses.is_dataclass(current) and isinstance(value, dict):
            _merge(current, value, f"{where}.{key}")
        elif isinstance(current, dict) and isinstance(value, dict):
            current.update(value)
        else:
            setattr(obj, key, value)


def load_config(path: Path | None = None) -> Config:
    cfg = Config()
    path = path or config_dir() / "config.yaml"
    if path.is_file():
        with path.open(encoding="utf-8") as f:
            _merge(cfg, yaml.safe_load(f) or {}, path.name)
    menu = {k: v for k, v in load_settings().items() if k in MENU_SETTINGS}
    _merge(cfg, menu, "settings.json")
    return cfg


def load_settings() -> dict[str, Any]:
    try:
        with (config_dir() / "settings.json").open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_setting(key: str, value: Any) -> None:
    """Remember one menu choice (written atomically, other keys kept)."""
    settings = load_settings()
    settings[key] = value
    target = config_dir() / "settings.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)
