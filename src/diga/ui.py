# pyright: reportAttributeAccessIssue=false
# (PyObjC exposes macOS framework symbols dynamically, so static checkers cannot see them.)
"""Menu-bar icon (rumps) with sounds.

Icon (SF Symbols, follow the light/dark menu bar): hourglass loading · speech bubble ready ·
red filled bubble recording · bubble with … finishing the last chunk. Emoji on macOS without
SF Symbols. Sounds (``sounds.py``): start of recording, and success once the text is typed.
Menu: a hint, the dictation key, the sound set (picking one plays it), open glossary, quit —
and a warning when macOS does not let diga type. Nothing else to choose: the language is
detected per chunk and the rest are the best defaults (``~/.config/diga/config.yaml``).

The recorder runs on a background thread; every AppKit change is marshalled to the main thread.
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable

from . import sounds
from .hotkeys import DEFAULT_KEY, KEYS
from .i18n import t

log = logging.getLogger(__name__)

ICONS = {"loading": "⏳", "idle": "💬", "rec": "🔴", "asr": "💭"}  # fallback only
# A speech bubble, not a microphone: macOS shows its own microphone indicator in the menu bar
# while any app records, and a second microphone right next to it was easy to mistake for it.
SYMBOLS = {
    "loading": "hourglass",
    "idle": "text.bubble",
    "rec": "text.bubble.fill",
    "asr": "ellipsis.bubble",
}


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
    def __init__(self, sound_choice: str = sounds.DEFAULT, key: str = DEFAULT_KEY) -> None:
        import rumps

        self._rumps = rumps
        self.app = rumps.App("diga", quit_button=None)  # pyright: ignore[reportArgumentType]
        self._images = _symbol_images()
        self._icon = "loading"
        rumps.events.before_start.register(lambda: self._apply_icon(self._icon))
        self._on_quit: Callable[[], None] | None = None
        self._on_sounds: Callable[[str], None] | None = None
        self._on_key: Callable[[str], None] | None = None
        self._glossary_path: str | None = None
        self._sound_choice = sound_choice
        self._sounds = sounds.resolve(sound_choice)

        self._warning_key = ""
        self._hint_key = t("menu.hint", key=t(f"key.{key}"))
        self._hint = rumps.MenuItem(self._hint_key)  # no callback: greyed out, as a label
        self._key_menu = rumps.MenuItem(t("menu.key"))
        self._key_items: dict[str, object] = {}
        for k in KEYS:
            item = rumps.MenuItem(t(f"key.{k}"), callback=self._clicked_key)
            item.state = int(k == key)
            self._key_items[k] = item
            self._key_menu.add(item)
        self._glossary_item = rumps.MenuItem(
            t("menu.open_glossary"), callback=self._clicked_glossary
        )
        self._warning_item = rumps.MenuItem("", callback=self._clicked_warning)
        self._warning_url: str | None = None
        self._log_path: str | None = None
        self._log_item = rumps.MenuItem(t("menu.show_log"), callback=self._clicked_log)
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
            self._hint,
            None,
            self._key_menu,
            self._sound_menu,
            self._glossary_item,
            self._log_item,
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
        key: Callable[[str], None] | None = None,
        log_path: str | None = None,
    ) -> None:
        self._on_quit = quit
        self._glossary_path = glossary_path
        self._log_path = log_path
        self._on_sounds = sounds
        self._on_key = key

    def _clicked_key(self, sender: object) -> None:
        key = next((k for k, item in self._key_items.items() if item is sender), None)
        if key is None:
            return
        for k, item in self._key_items.items():
            item.state = int(k == key)  # type: ignore[attr-defined]
        self._hint.title = t("menu.hint", key=t(f"key.{key}"))  # type: ignore[attr-defined]
        if self._on_key:
            self._on_key(key)

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

    def _clicked_warning(self, _sender: object) -> None:
        if self._warning_url:
            subprocess.Popen(["open", self._warning_url])

    def _clicked_log(self, _sender: object) -> None:
        if self._log_path:
            subprocess.Popen(["open", "-a", "Console", self._log_path])

    def _clicked_glossary(self, _sender: object) -> None:
        if self._glossary_path:
            # -t: the default text editor; a .yaml file may otherwise open in Xcode or nowhere
            subprocess.Popen(["open", "-t", self._glossary_path])

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

    def warning(self, text: str | None, url: str | None = None) -> None:
        """Show ``text`` as the first menu item (clicking opens ``url``), or remove it."""
        self._warning_url = url

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
