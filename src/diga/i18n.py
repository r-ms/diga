"""User-facing strings in English, Russian and Portuguese.

``t(key, **kwargs)`` returns the string in the current UI language (``set_language``),
falling back to English. The default UI language follows macOS preferences.
"""

from __future__ import annotations

import os

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "status.second_opinion_missing": "The second opinion needs Parakeet: "
        "uv tool install 'diga[ru,parakeet]'",
        "menu.hint": "Hold right ⌘ and speak",
        "status.auto_without_detector": "Language detection is off ({reason}); dictating in "
        "Russian only",
        "status.russian_missing": "Russian is recognized by Parakeet; for better Russian "
        "install GigaAM: uv tool install 'diga[ru,parakeet]'",
        "menu.sounds": "Sound",
        "sounds.soft": "Soft",
        "sounds.tick": "Tick",
        "sounds.drop": "Drop",
        "sounds.chime": "Chime",
        "sounds.off": "Off",
        "sounds.custom": "Your own ({name})",
        "menu.open_glossary": "Open glossary",
        "menu.quit": "Quit",
        "menu.no_typing": "⚠ macOS doesn't let diga type — see the console",
        "status.no_typing": "⚠ macOS doesn't allow {app} to type into other apps. System Settings →"
        " Privacy & Security → Accessibility → turn {app} on, then restart "
        "diga.",
        "status.loading": "Loading {model}…",
        "status.ready_hotkeys": "Ready. Hold right ⌘ to dictate, release to insert{send}. "
        "Double-tap right ⌘ for long dictation.",
        "status.ready_send": " and press Return",
        "status.ready_stdin": "Ready. Press Enter to start/stop recording, Ctrl+C to quit.",
        "status.recording_hold": "● recording… (release right ⌘ to stop)",
        "status.recording_toggle": "● recording… (double-tap right ⌘ to stop)",
        "status.stopped": "○ stopped, finishing the last chunk…",
        "status.chunk": "  ✓ chunk {i}: {audio:.1f} s of audio → {asr:.2f} s  «{text}»",
        "status.done": "  done: {audio:.1f} s of audio, {chunks} chunk(s), "
        "{after:.2f} s after stop",
        "status.sent": "  ⏎ sent",
        "status.too_short": "  too short — skipped",
        "status.nothing": "  (nothing recognized)",
        "status.cancelled": "  cancelled: another key was pressed while holding ⌘",
        "status.limit": "  recording limit of {seconds:.0f} s reached — stopping",
        "status.terms_off": "Term correction is off: {reason}",
        "status.quit": "Bye.",
    },
    "ru": {
        "status.second_opinion_missing": "Для второго мнения нужен Parakeet: "
        "uv tool install 'diga[ru,parakeet]'",
        "menu.hint": "Держи правый ⌘ и говори",
        "status.auto_without_detector": "Определение языка выключено ({reason}); диктовка "
        "только по-русски",
        "status.russian_missing": "Русский распознаёт Parakeet; для лучшего русского "
        "поставь GigaAM: uv tool install 'diga[ru,parakeet]'",
        "menu.sounds": "Звук",
        "sounds.soft": "Мягкий",
        "sounds.tick": "Щелчок",
        "sounds.drop": "Капля",
        "sounds.chime": "Колокольчик",
        "sounds.off": "Без звука",
        "sounds.custom": "Свои ({name})",
        "menu.open_glossary": "Открыть словарь",
        "menu.quit": "Выход",
        "menu.no_typing": "⚠ macOS не даёт diga печатать — подробности в консоли",
        "status.no_typing": "⚠ macOS не разрешает {app} печатать в другие приложения. Системные "
        "настройки → Конфиденциальность и безопасность → Универсальный доступ →"
        " включи {app}, затем перезапусти diga.",
        "status.loading": "Загружаю {model}…",
        "status.ready_hotkeys": "Готово. Держи правый ⌘ — диктовка, отпустил — вставка{send}. "
        "Двойное нажатие правого ⌘ — длинная диктовка.",
        "status.ready_send": " и Enter",
        "status.ready_stdin": "Готово. Enter — старт/стоп записи, Ctrl+C — выход.",
        "status.recording_hold": "● запись… (отпусти правый ⌘ — стоп)",
        "status.recording_toggle": "● запись… (двойное нажатие правого ⌘ — стоп)",
        "status.stopped": "○ стоп, досчитываю последний кусок…",
        "status.chunk": "  ✓ кусок {i}: {audio:.1f} с звука → {asr:.2f} с  «{text}»",
        "status.done": "  готово: {audio:.1f} с звука, кусков: {chunks}, после стопа {after:.2f} с",
        "status.sent": "  ⏎ отправлено",
        "status.too_short": "  слишком коротко — пропускаю",
        "status.nothing": "  (ничего не распознано)",
        "status.cancelled": "  отменено: пока держал ⌘, была нажата другая клавиша",
        "status.limit": "  достигнут лимит записи {seconds:.0f} с — останавливаю",
        "status.terms_off": "Исправление терминов выключено: {reason}",
        "status.quit": "Выход.",
    },
    "pt": {
        "status.second_opinion_missing": "A segunda opinião precisa do Parakeet: "
        "uv tool install 'diga[ru,parakeet]'",
        "menu.hint": "Mantenha o ⌘ direito premido e fale",
        "status.auto_without_detector": "Deteção de idioma desligada ({reason}); ditado "
        "só em russo",
        "status.russian_missing": "O russo é reconhecido pelo Parakeet; para um russo "
        "melhor instale o GigaAM: uv tool install 'diga[ru,parakeet]'",
        "menu.sounds": "Som",
        "sounds.soft": "Suave",
        "sounds.tick": "Clique",
        "sounds.drop": "Gota",
        "sounds.chime": "Sino",
        "sounds.off": "Sem som",
        "sounds.custom": "Personalizado ({name})",
        "menu.open_glossary": "Abrir glossário",
        "menu.quit": "Sair",
        "menu.no_typing": "⚠ O macOS não deixa o diga escrever — veja a consola",
        "status.no_typing": "⚠ O macOS não permite que {app} escreva noutras aplicações. Definições"
        " do Sistema → Privacidade e Segurança → Acessibilidade → ligue {app} e"
        " reinicie o diga.",
        "status.loading": "A carregar {model}…",
        "status.ready_hotkeys": "Pronto. Mantenha o ⌘ direito premido para ditar e solte para "
        "inserir{send}. Toque duas vezes no ⌘ direito para ditados longos.",
        "status.ready_send": " e premir Enter",
        "status.ready_stdin": "Pronto. Enter inicia/para a gravação, Ctrl+C sai.",
        "status.recording_hold": "● a gravar… (solte o ⌘ direito para parar)",
        "status.recording_toggle": "● a gravar… (dois toques no ⌘ direito para parar)",
        "status.stopped": "○ parado, a terminar o último bloco…",
        "status.chunk": "  ✓ bloco {i}: {audio:.1f} s de áudio → {asr:.2f} s  «{text}»",
        "status.done": "  concluído: {audio:.1f} s de áudio, {chunks} bloco(s), "
        "{after:.2f} s após parar",
        "status.sent": "  ⏎ enviado",
        "status.too_short": "  demasiado curto — ignorado",
        "status.nothing": "  (nada reconhecido)",
        "status.cancelled": "  cancelado: foi premida outra tecla enquanto o ⌘ estava premido",
        "status.limit": "  limite de gravação de {seconds:.0f} s atingido — a parar",
        "status.terms_off": "Correção de termos desligada: {reason}",
        "status.quit": "Adeus.",
    },
}

SUPPORTED = tuple(STRINGS)
_current = "en"


def detect_system_language() -> str:
    """First supported language from macOS preferences, then $LANG; English otherwise."""
    candidates: list[str] = []
    try:
        from Foundation import NSLocale  # type: ignore[import-not-found]

        candidates.extend(str(x) for x in NSLocale.preferredLanguages())
    except Exception:
        pass
    candidates.append(os.environ.get("LANG", ""))
    for c in candidates:
        code = c.split("-")[0].split("_")[0].lower()
        if code in STRINGS:
            return code
    return "en"


def set_language(lang: str | None) -> str:
    global _current
    _current = lang if lang in STRINGS else detect_system_language()
    return _current


def current_language() -> str:
    return _current


def t(key: str, **kwargs: object) -> str:
    text = STRINGS.get(_current, {}).get(key) or STRINGS["en"][key]
    return text.format(**kwargs) if kwargs else text
