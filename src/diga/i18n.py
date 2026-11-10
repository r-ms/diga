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
        "menu.hint": "Hold {key} and speak",
        "menu.show_log": "Show log",
        "menu.need_keyboard": "⚠ Allow Input Monitoring for {app} — click here",
        "menu.need_typing": "⚠ Allow Accessibility for {app} — click here",
        "menu.need_microphone": "⚠ Allow the microphone for {app} — click here",
        "status.need_keyboard": "⚠ diga can't see the keyboard. System Settings → Privacy & "
        "Security → Input Monitoring → turn on {app}. diga connects by itself once it's on.",
        "status.need_typing": "⚠ macOS doesn't let diga type. System Settings → Privacy & "
        "Security → Accessibility → turn on {app}.",
        "status.need_microphone": "⚠ diga can't use the microphone. System Settings → Privacy & "
        "Security → Microphone → turn on {app}.",
        "status.keyboard_ready": "Keyboard connected: hold {key} and speak.",
        "status.restarting": "Input Monitoring is on, but macOS shows the keyboard only to a new "
        "process: restarting diga…",
        "status.languages": "Your languages: {langs} ({source})",
        "status.from_config": "from your settings",
        "status.from_mac": "from macOS",
        "status.russian_off": "Russian is not among them: the Russian models are not loaded. "
        "Dictate in Russian? Add ru to `languages` in ~/.config/diga/config.yaml.",
        "status.russian_heard": "That sounded like Russian, which is not among your languages, "
        "so Parakeet alone recognized it. For the stronger Russian recognizer add ru to "
        "`languages` in ~/.config/diga/config.yaml and restart diga.",
        "menu.key": "Key",
        "status.key": "Dictation key: {key}",
        "key.right_cmd": "right ⌘",
        "key.right_option": "right ⌥",
        "key.fn": "Fn (🌐)",
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
        "status.loading": "Loading {model}…",
        "status.ready_hotkeys": "Ready. Hold {key} to dictate, release to insert{send}. "
        "Double-tap {key} for long dictation.",
        "status.ready_send": " and press Return",
        "status.ready_stdin": "Ready. Press Enter to start/stop recording, Ctrl+C to quit.",
        "status.recording_hold": "● recording… (release the key to stop)",
        "status.recording_toggle": "● recording… (double-tap the key to stop)",
        "status.stopped": "○ stopped, finishing the last chunk…",
        "status.chunk": "  ✓ chunk {i}: {audio:.1f} s of audio → {asr:.2f} s  «{text}»",
        "status.done": "  done: {audio:.1f} s of audio, {chunks} chunk(s), "
        "{after:.2f} s after stop",
        "status.sent": "  ⏎ sent",
        "status.too_short": "  too short — skipped",
        "status.nothing": "  (nothing recognized)",
        "status.cancelled": "  cancelled: another key was pressed while holding the key",
        "status.limit": "  recording limit of {seconds:.0f} s reached — stopping",
        "status.terms_off": "Term correction is off: {reason}",
        "status.quit": "Bye.",
    },
    "ru": {
        "status.second_opinion_missing": "Для второго мнения нужен Parakeet: "
        "uv tool install 'diga[ru,parakeet]'",
        "menu.hint": "Держи {key} и говори",
        "menu.show_log": "Показать журнал",
        "menu.need_keyboard": "⚠ Разреши «Мониторинг ввода» для {app} — нажми сюда",
        "menu.need_typing": "⚠ Разреши «Универсальный доступ» для {app} — нажми сюда",
        "menu.need_microphone": "⚠ Разреши микрофон для {app} — нажми сюда",
        "status.need_keyboard": "⚠ diga не видит клавиатуру. Системные настройки → "
        "Конфиденциальность и безопасность → Мониторинг ввода → включи {app}. diga подключится "
        "сама, как только включишь.",
        "status.need_typing": "⚠ macOS не даёт diga печатать. Системные настройки → "
        "Конфиденциальность и безопасность → Универсальный доступ → включи {app}.",
        "status.need_microphone": "⚠ diga не может включить микрофон. Системные настройки → "
        "Конфиденциальность и безопасность → Микрофон → включи {app}.",
        "status.keyboard_ready": "Клавиатура подключена: держи {key} и говори.",
        "status.restarting": "«Мониторинг ввода» включён, но macOS показывает клавиатуру только "
        "новому процессу: перезапускаю diga…",
        "status.languages": "Твои языки: {langs} ({source})",
        "status.from_config": "из настроек",
        "status.from_mac": "из macOS",
        "status.russian_off": "Русского среди них нет: русские модели не загружаются. "
        "Диктуешь по-русски? Добавь ru в `languages` в ~/.config/diga/config.yaml.",
        "status.russian_heard": "Похоже на русскую речь, а русского нет среди твоих языков, "
        "поэтому её распознал один Parakeet. Для сильного русского распознавания добавь ru в "
        "`languages` в ~/.config/diga/config.yaml и перезапусти diga.",
        "menu.key": "Клавиша",
        "status.key": "Клавиша диктовки: {key}",
        "key.right_cmd": "правый ⌘",
        "key.right_option": "правый ⌥",
        "key.fn": "Fn (🌐)",
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
        "status.loading": "Загружаю {model}…",
        "status.ready_hotkeys": "Готово. Держи {key} — диктовка, отпустил — вставка{send}. "
        "Нажми {key} дважды — длинная диктовка.",
        "status.ready_send": " и Enter",
        "status.ready_stdin": "Готово. Enter — старт/стоп записи, Ctrl+C — выход.",
        "status.recording_hold": "● запись… (отпусти клавишу — стоп)",
        "status.recording_toggle": "● запись… (нажми клавишу дважды — стоп)",
        "status.stopped": "○ стоп, досчитываю последний кусок…",
        "status.chunk": "  ✓ кусок {i}: {audio:.1f} с звука → {asr:.2f} с  «{text}»",
        "status.done": "  готово: {audio:.1f} с звука, кусков: {chunks}, после стопа {after:.2f} с",
        "status.sent": "  ⏎ отправлено",
        "status.too_short": "  слишком коротко — пропускаю",
        "status.nothing": "  (ничего не распознано)",
        "status.cancelled": "  отменено: пока держал клавишу, была нажата другая",
        "status.limit": "  достигнут лимит записи {seconds:.0f} с — останавливаю",
        "status.terms_off": "Исправление терминов выключено: {reason}",
        "status.quit": "Выход.",
    },
    "pt": {
        "status.second_opinion_missing": "A segunda opinião precisa do Parakeet: "
        "uv tool install 'diga[ru,parakeet]'",
        "menu.hint": "{key}: mantenha premido e fale",
        "menu.show_log": "Mostrar registo",
        "menu.need_keyboard": "⚠ Permita «Monitorização de entrada» para {app} — clique aqui",
        "menu.need_typing": "⚠ Permita «Acessibilidade» para {app} — clique aqui",
        "menu.need_microphone": "⚠ Permita o microfone para {app} — clique aqui",
        "status.need_keyboard": "⚠ O diga não vê o teclado. Definições do Sistema → Privacidade e "
        "Segurança → Monitorização de entrada → ligue {app}. O diga liga-se sozinho.",
        "status.need_typing": "⚠ O macOS não deixa o diga escrever. Definições do Sistema → "
        "Privacidade e Segurança → Acessibilidade → ligue {app}.",
        "status.need_microphone": "⚠ O diga não pode usar o microfone. Definições do Sistema → "
        "Privacidade e Segurança → Microfone → ligue {app}.",
        "status.keyboard_ready": "Teclado ligado: mantenha {key} premido e fale.",
        "status.restarting": "A «Monitorização de entrada» está ligada, mas o macOS só mostra o "
        "teclado a um processo novo: a reiniciar o diga…",
        "status.languages": "Os seus idiomas: {langs} ({source})",
        "status.from_config": "das suas definições",
        "status.from_mac": "do macOS",
        "status.russian_off": "O russo não está entre eles: os modelos russos não são carregados. "
        "Dita em russo? Acrescente ru a `languages` em ~/.config/diga/config.yaml.",
        "status.russian_heard": "Isto pareceu russo, que não está entre os seus idiomas, por isso "
        "foi reconhecido só pelo Parakeet. Para o reconhecimento russo mais forte, acrescente ru "
        "a `languages` em ~/.config/diga/config.yaml e reinicie o diga.",
        "menu.key": "Tecla",
        "status.key": "Tecla de ditado: {key}",
        "key.right_cmd": "⌘ direito",
        "key.right_option": "⌥ direito",
        "key.fn": "Fn (🌐)",
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
        "status.loading": "A carregar {model}…",
        "status.ready_hotkeys": "Pronto. {key}: mantenha premido para ditar e solte para "
        "inserir{send}; dois toques para ditados longos.",
        "status.ready_send": " e premir Enter",
        "status.ready_stdin": "Pronto. Enter inicia/para a gravação, Ctrl+C sai.",
        "status.recording_hold": "● a gravar… (solte a tecla para parar)",
        "status.recording_toggle": "● a gravar… (dois toques na tecla para parar)",
        "status.stopped": "○ parado, a terminar o último bloco…",
        "status.chunk": "  ✓ bloco {i}: {audio:.1f} s de áudio → {asr:.2f} s  «{text}»",
        "status.done": "  concluído: {audio:.1f} s de áudio, {chunks} bloco(s), "
        "{after:.2f} s após parar",
        "status.sent": "  ⏎ enviado",
        "status.too_short": "  demasiado curto — ignorado",
        "status.nothing": "  (nada reconhecido)",
        "status.cancelled": "  cancelado: foi premida outra tecla enquanto a tecla estava premida",
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


def t(key: str, /, **kwargs: object) -> str:
    text = STRINGS.get(_current, {}).get(key) or STRINGS["en"][key]
    return text.format(**kwargs) if kwargs else text
