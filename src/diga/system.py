"""What this Mac says about its user: the languages they read and the keyboards they type on.

Used when ``languages`` is not set in the configuration, to decide whether to load the extra
Russian recognizer (GigaAM, ~2 GB of memory) — see ``Config.spoken_languages``.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Keyboard layout names (System Settings → Keyboard → Input Sources) → language code.
_LAYOUTS = {
    "russian": "ru",
    "ukrainian": "uk",
    "belarusian": "be",
    "bulgarian": "bg",
    "serbian": "sr",
    "kazakh": "kk",
    "portuguese": "pt",
    "brazilian": "pt",
    "abc": "en",
    "u.s.": "en",
    "us": "en",
    "british": "en",
    "australian": "en",
    "canadian": "en",
    "irish": "en",
    "german": "de",
    "french": "fr",
    "spanish": "es",
    "italian": "it",
    "polish": "pl",
    "dutch": "nl",
}


def code(tag: str) -> str:
    """'ru-AM' / 'pt_PT' → 'ru' / 'pt'."""
    return tag.replace("_", "-").split("-")[0].lower()


def layout_language(name: str) -> str | None:
    """'Russian - Phonetic' → 'ru'; unknown layouts → None."""
    first = name.lower().replace("–", "-").split(" - ")[0].split("(")[0].strip()
    return _LAYOUTS.get(first) or _LAYOUTS.get(first.split()[0] if first else "")


def mac_languages(
    preferred: list[str] | None = None, layouts: list[str] | None = None
) -> list[str]:
    """Languages from macOS's preferred languages, then from the keyboard layouts, in order."""
    if preferred is None:
        preferred = _preferred_languages()
    if layouts is None:
        layouts = _keyboard_layouts()
    found = [code(tag) for tag in preferred]
    found += [lang for lang in (layout_language(n) for n in layouts) if lang]
    return list(dict.fromkeys(found))


def _preferred_languages() -> list[str]:
    try:
        from Foundation import NSLocale  # type: ignore[import-not-found]

        return [str(x) for x in NSLocale.preferredLanguages()]
    except Exception as e:
        log.debug("preferred languages unavailable: %s", e)
        return []


def _keyboard_layouts() -> list[str]:
    try:
        from Foundation import NSUserDefaults  # type: ignore[import-not-found]

        prefs = NSUserDefaults.alloc().initWithSuiteName_("com.apple.HIToolbox")
        sources = prefs.arrayForKey_("AppleEnabledInputSources") or []
        return [str(s["KeyboardLayout Name"]) for s in sources if s.get("KeyboardLayout Name")]
    except Exception as e:
        log.debug("keyboard layouts unavailable: %s", e)
        return []
