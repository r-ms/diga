# pyright: reportAttributeAccessIssue=false
# (PyObjC exposes macOS framework symbols dynamically, so static checkers cannot see them.)
"""Menu-bar icon (rumps) with sounds.

Icon (SF Symbols, follow the light/dark menu bar): hourglass loading · mic ready ·
red filled mic recording · waveform finishing the last chunk. Sounds (``sounds.py``): start of
recording, and success once the text is typed. Emoji on macOS without SF Symbols.
Menu: a hint, the sound set (picking one plays it), open glossary, quit — and a warning when
macOS does not let diga type. Nothing else to choose: the language is detected per chunk and
the rest are the best defaults (``~/.config/diga/config.yaml`` changes them).

The recorder runs on a background thread; every AppKit change is marshalled to the main thread.
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable

from . import sounds
from .i18n import t

log = logging.getLogger(__name__)

ICONS = {"loading": "⏳", "idle": "🎙️", "rec": "🔴", "asr": "✍️"}  # fallback only
SYMBOLS = {"loading": "hourglass", "idle": "mic", "rec": "mic.fill", "asr": "waveform"}


def _symbol_images() -> dict[str, object]:
    """Template NSImages for the menu bar; empty if SF Symbols are unavailable (macOS < 11)."""
    try:
        from AppKit import NSFontWeightMedium, NSImage, NSImageSymbolConfiguration

        config = NSImageSymbolConfiguration.configurationWithPointSize_weight_(
            14, NSFontWeightMedium
        )
        images: dict[str, object] = {}
        for key, name in SYMBOLS.items():
            image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, "diga")
            if image is None:
                return {}
            if key == "rec":  # recording stands out in red; template images ignore tint colors
                from AppKit import NSColor

                red = NSImageSymbolConfiguration.configurationWithPaletteColors_(
                    [NSColor.systemRedColor()]
                )
                image = image.imageWithSymbolConfiguration_(
                    config.configurationByApplyingConfiguration_(red)
                )
                image.setTemplate_(False)
            else:
                image = image.imageWithSymbolConfiguration_(config)
                image.setTemplate_(True)  # macOS tints it for the light or dark menu bar
            images[key] = image
        return images
    except Exception as e:
        log.debug("SF Symbols unavailable, using emoji: %s", e)
        return {}


def _on_main(fn: Callable[[], None]) -> None:
    from PyObjCTools import AppHelper

    AppHelper.callAfter(fn)


class MenuBar:
    def __init__(self, sound_choice: str = sounds.DEFAULT) -> None:
        import rumps

        self._rumps = rumps
        self.app = rumps.App("diga", quit_button=None)  # pyright: ignore[reportArgumentType]
        self._images = _symbol_images()
        self._icon = "loading"
        rumps.events.before_start.register(lambda: self._apply_icon(self._icon))
        self._on_quit: Callable[[], None] | None = None
        self._on_sounds: Callable[[str], None] | None = None
        self._glossary_path: str | None = None
        self._sound_choice = sound_choice
        self._sounds = sounds.resolve(sound_choice)

        self._warning_key = ""
        self._hint_key = t("menu.hint")
        hint = rumps.MenuItem(self._hint_key)  # no callback: shown greyed out, as a label
        self._glossary_item = rumps.MenuItem(
            t("menu.open_glossary"), callback=self._clicked_glossary
        )
        self._warning_item = rumps.MenuItem("")
        self._quit_item = rumps.MenuItem(t("menu.quit"), callback=self._clicked_quit)
        self._sound_menu = rumps.MenuItem(t("menu.sounds"))
        self._sound_items: dict[str, object] = {}
        choices = [*sounds.SETS, sounds.OFF]
        if sound_choice not in choices:  # a folder of your own, from config.yaml
            choices.insert(0, sound_choice)
        for choice in choices:
            title = (
                t(f"sounds.{choice}")
                if choice in (*sounds.SETS, sounds.OFF)
                else t("sounds.custom", name=choice)
            )
            item = rumps.MenuItem(title, callback=self._clicked_sound)
            item.state = int(choice == sound_choice)
            self._sound_items[choice] = item
            self._sound_menu.add(item)
        self.app.menu = [
            hint,
            None,
            self._sound_menu,
            self._glossary_item,
            None,
            self._quit_item,
        ]
        self._warning_shown = False
        try:  # menu-bar agent: no Dock icon
            from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

            NSApplication.sharedApplication().setActivationPolicy_(
                NSApplicationActivationPolicyAccessory
            )
        except Exception as e:
            log.debug("accessory activation policy failed: %s", e)

    # --- wiring ---

    def bind(
        self,
        *,
        quit: Callable[[], None],
        glossary_path: str | None,
        sounds: Callable[[str], None] | None = None,
    ) -> None:
        self._on_quit = quit
        self._glossary_path = glossary_path
        self._on_sounds = sounds

    def _clicked_sound(self, sender: object) -> None:
        choice = next((c for c, item in self._sound_items.items() if item is sender), None)
        if choice is None:
            return
        for c, item in self._sound_items.items():
            item.state = int(c == choice)  # type: ignore[attr-defined]
        self._sound_choice, self._sounds = choice, sounds.resolve(choice)
        sounds.play(self._sounds.done)  # let you hear what you picked
        if self._on_sounds:
            self._on_sounds(choice)

    def _clicked_glossary(self, _sender: object) -> None:
        if self._glossary_path:
            subprocess.Popen(["open", self._glossary_path])

    def _clicked_quit(self, _sender: object) -> None:
        if self._on_quit:
            self._on_quit()
        else:
            self._rumps.quit_application()

    # --- state updates (any thread) ---

    def _apply_icon(self, key: str) -> None:
        """Main thread only. Before the status item exists, just remember the state."""
        self._icon = key
        nsapp = getattr(self.app, "_nsapp", None)
        item = getattr(nsapp, "nsstatusitem", None)
        image = self._images.get(key)
        if item is None:
            return
        if image is None:
            item.setTitle_(ICONS[key])
            return
        button = item.button()
        button.setImage_(image)
        button.setTitle_("")

    def _set_icon(self, key: str) -> None:
        _on_main(lambda: self._apply_icon(key))

    def loading(self) -> None:
        self._set_icon("loading")

    def ready(self) -> None:
        self._set_icon("idle")

    def recording_state(self, phase: str) -> None:
        if phase == "rec":
            sounds.play(self._sounds.start)
        elif phase == "done":
            sounds.play(self._sounds.done)
        self._set_icon(phase if phase in ICONS else "idle")

    def warning(self, text: str | None) -> None:
        """Show ``text`` as the first menu item, or remove it when ``None``."""

        # rumps keys menu items by the title they had when inserted, so keep that key.
        def update() -> None:
            if text:
                if not self._warning_shown:
                    self._warning_key = text
                    self._warning_item.title = text
                    self.app.menu.insert_before(self._hint_key, self._warning_item)
                    self._warning_shown = True
                else:
                    self._warning_item.title = text
            elif self._warning_shown:
                del self.app.menu[self._warning_key]
                self._warning_shown = False

        _on_main(update)

    def run(self) -> None:
        self.app.run()
