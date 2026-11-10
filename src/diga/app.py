"""Wiring: recognizer + term corrector + recorder + hotkeys + menu bar."""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from collections.abc import Callable

from .asr import MissingBackend, Transcriber, create_transcriber, installed
from .config import Config, save_setting
from .hotkeys import HotkeyManager
from .i18n import t
from .logfile import LOG_FILE
from .permissions import (
    SETTINGS_URL,
    can_post_events,
    host_app,
    missing_all,
    request_all,
)
from .recorder import Recorder
from .terms import ByLanguage, ChainCorrector, Corrector, GlossaryFile, ensure_glossary

log = logging.getLogger(__name__)


def build_corrector(
    language: str, cfg: Config, glossary: GlossaryFile, russian_chunks: bool = False
) -> Corrector | None:
    """Text matching everywhere; for Russian, acoustic spotting first, then text matching.

    The two catch different errors: the acoustic spotter recovers words the recognizer
    garbled ("пужгид" → git), text matching fixes clean phonetic spellings it never spots
    ("пайтоне" → Python). See benchmarks/terms.py. ``russian_chunks``: in ``auto``, GigaAM
    re-recognizes the chunks that are in Russian, and those get the Russian correction.
    """
    if not cfg.terms.enabled:
        return None
    try:
        from .terms.fuzzy import FuzzyCorrector

        text = FuzzyCorrector(glossary, language, cfg.terms.fuzzy_threshold)
        acoustic_ok = cfg.backend_for("ru") == "gigaam"
        if not acoustic_ok or not (language == "ru" or (language == "auto" and russian_chunks)):
            return text
        from .terms.acoustic import AcousticCorrector
        from .terms.ctc import GigaAMCtc

        acoustic = AcousticCorrector(
            GigaAMCtc.from_hub(cfg.terms.ctc_precision),
            glossary,
            cfg.terms.ctc_weight,
            cfg.terms.max_frames_per_token,
            cfg.terms.acoustic_min_similarity,
        )
        if language == "ru":
            return ChainCorrector(acoustic, text)
        russian_text = FuzzyCorrector(glossary, "ru", cfg.terms.fuzzy_threshold)
        return ByLanguage(text, ru=ChainCorrector(acoustic, russian_text))
    except Exception as e:  # fail open: dictation without term correction still works
        log.warning(t("status.terms_off", reason=e))
        return None


MLX_CACHE_BYTES = 256 * 2**20


def limit_gpu_cache() -> None:
    """Cap MLX's pool of freed GPU buffers (Parakeet, Whisper, the language model).

    By default MLX keeps every freed buffer for reuse, and chunks of every length make that
    pool grow: diga's footprint reached 8.4 GB over a few dictations. With a 256 MB pool it
    stays at ~3.5 GB with every model loaded, at the same speed.
    """
    try:
        import mlx.core as mx
    except ImportError:
        return
    mx.set_cache_limit(MLX_CACHE_BYTES)


def whisper_prompt(glossary: GlossaryFile) -> str | None:
    terms = [term.term for term in glossary.terms]
    return ", ".join(terms) if terms else None


class App:
    def __init__(self, cfg: Config, *, with_ui: bool = True, print_only: bool = False) -> None:
        self.cfg = cfg
        self.with_ui = with_ui
        self.print_only = print_only
        self.stop = threading.Event()
        self.glossary = GlossaryFile(ensure_glossary(cfg.glossary_path()))
        self.menu = None
        self.recorder: Recorder | None = None
        self._missing_shown: str | None = None
        self._waiting = False  # the user opened System Settings from the warning

    # --- engine (recognizer + corrector) ---

    def build_engine(self, language: str) -> tuple[Transcriber, Corrector | None]:
        limit_gpu_cache()
        if language == "auto":
            transcriber, russian = self._auto()
        else:
            backend = self.cfg.backend_for(language)
            log.info(t("status.loading", model=backend))
            prompt = whisper_prompt(self.glossary)
            transcriber = create_transcriber(language, self.cfg, prompt=prompt)
            russian = backend == "gigaam"
            if russian and self.cfg.second_opinion:
                transcriber = self._with_second_opinion(transcriber)
        transcriber.warmup()
        return transcriber, build_corrector(language, self.cfg, self.glossary, russian)

    def _auto(self) -> tuple[Transcriber, bool]:
        """Parakeet for every chunk; GigaAM (+ Parakeet + language model) for Russian ones."""
        log.info(t("status.loading", model=self.cfg.backend_for("auto")))
        try:
            detector = create_transcriber("auto", self.cfg, prompt=whisper_prompt(self.glossary))
        except MissingBackend as missing:
            if not installed(self.cfg.backend_for("ru")):
                raise
            log.warning(t("status.auto_without_detector", reason=missing))
            russian = create_transcriber("ru", self.cfg)
            return russian, True
        from .asr.auto import AutoTranscriber

        langs, source = self.cfg.spoken_languages()
        where = t("status.from_config" if source == "config" else "status.from_mac")
        log.info(t("status.languages", langs=", ".join(langs) or "—", source=where))
        if not self.cfg.wants_russian():
            log.info(t("status.russian_off"))
            hint = lambda: log.warning(t("status.russian_heard"))  # noqa: E731
            return AutoTranscriber(detector, None, on_russian_unhandled=hint), False
        try:
            log.info(t("status.loading", model=self.cfg.backend_for("ru")))
            russian = create_transcriber("ru", self.cfg)
        except MissingBackend:
            log.info(t("status.russian_missing"))
            return detector, False

        auto = AutoTranscriber(
            detector,
            russian,
            second_opinion=self.cfg.second_opinion,
            unsure=self.cfg.second_opinion_unsure,
            insert=self.cfg.second_opinion_insert,
            judge=self._judge() if self.cfg.second_opinion else None,
            margin=self.cfg.second_opinion_lm_margin,
        )
        return auto, True

    def _judge(self) -> Callable[[str], float] | None:
        """The small language model that settles disagreements, if enabled and installed."""
        if not self.cfg.use_language_model():
            return None
        try:
            from .asr.plausibility import PlausibilityModel

            log.info(t("status.loading", model="qwen3-0.6b"))
            lm = PlausibilityModel()
            lm.warmup()
            return lm.score
        except ImportError:
            log.warning(t("status.second_opinion_missing"))
            return None

    def _with_second_opinion(self, primary: Transcriber) -> Transcriber:
        try:
            from .asr.parakeet import ParakeetTranscriber
            from .asr.second_opinion import SecondOpinionTranscriber

            log.info(t("status.loading", model="parakeet"))
            secondary = ParakeetTranscriber(self.cfg.models.get("parakeet"))
        except ImportError:
            log.warning(t("status.second_opinion_missing"))
            return primary
        return SecondOpinionTranscriber(
            primary,
            secondary,
            self.cfg.second_opinion_unsure,
            self.cfg.second_opinion_insert,
            self._judge(),
            self.cfg.second_opinion_lm_margin,
        )

    # --- RecorderUI ---

    def recording_state(self, phase: str) -> None:
        if self.menu:
            self.menu.recording_state(phase)
        if phase == "rec":
            threading.Thread(target=self._check_typing_allowed, daemon=True).start()

    def _check_typing_allowed(self) -> None:
        """Warn when macOS would silently drop diga's typed text (no Accessibility permission)."""
        if can_post_events() is False:
            self._show_missing("typing")

    def _show_missing(self, what: str | None) -> None:
        """Log (once per change) and show in the menu what diga is not allowed to do."""
        if what == self._missing_shown:
            return
        self._missing_shown = what
        self._waiting = False
        if what:
            log.warning(t(f"status.need_{what}", app=host_app()))
        self._render_warning()

    def _render_warning(self) -> None:
        if not self.menu:
            return
        what = self._missing_shown
        if not what:
            self.menu.warning(None)
        elif self._waiting:  # Settings are open: say what to switch on, and that we follow
            self.menu.warning(t(f"menu.waiting_{what}", app=host_app()), SETTINGS_URL[what])
        else:
            self.menu.warning(t(f"menu.need_{what}"), SETTINGS_URL[what])

    def _warning_clicked(self) -> None:
        self._waiting = True
        self._render_warning()

    def _watch_permissions(self, hotkeys: HotkeyManager) -> None:
        """Every 2 s on the main thread: keep the menu warning up to date, and restart diga as
        soon as macOS grants a permission it lacked — a fresh process sees every permission at
        once (some macOS versions show the keyboard only to a new process). Never in the middle
        of a dictation: then it waits for the next tick."""
        import rumps

        state: dict[str, set[str]] = {"lacked": set()}

        def tick(_timer: object) -> None:
            if not hotkeys.started and hotkeys.start():
                log.info(t("status.keyboard_ready", key=t(f"key.{self.cfg.hotkey.key}")))
            gaps = missing_all()
            if not hotkeys.started and "keyboard" not in gaps:
                gaps.insert(0, "keyboard")  # allowed, yet the keyboard is still not visible
            busy = self.recorder is not None and self.recorder.recording
            granted, state["lacked"] = newly_granted(state["lacked"], gaps, busy)
            if granted:
                log.info(t("status.granted", what=", ".join(sorted(granted))))
                restart()
            self._show_missing(gaps[0] if gaps else None)

        tick(None)
        rumps.Timer(tick, 2).start()

    # --- running ---

    def _typing(self):
        if self.print_only:
            return (lambda text: print(f"  [type] {text}")), (lambda: print("  [Return]"))
        from .inject import KeystrokeTyper

        typer = KeystrokeTyper()
        return typer.type_text, typer.press_return

    def _make_recorder(self, transcriber: Transcriber, corrector: Corrector | None) -> Recorder:
        type_text, press_return = self._typing()
        return Recorder(
            transcriber,
            type_text,
            corrector=corrector,
            ui=self,
            chunking=self.cfg.chunking,
            press_return=press_return,
            send_after_hold=self.cfg.send_return_after_hold,
            log_text=sys.stderr.isatty() if self.cfg.log_text is None else self.cfg.log_text,
        )

    def run(self) -> None:
        if self.with_ui:
            self._run_menu_bar()
        else:
            self._run_headless()

    def _run_headless(self) -> None:
        self.recorder = self._make_recorder(*self.build_engine(self.cfg.language))

        def stdin_toggle() -> None:
            for _ in sys.stdin:
                assert self.recorder is not None
                self.recorder.toggle()

        threading.Thread(target=stdin_toggle, daemon=True).start()
        log.info(t("status.ready_stdin"))
        try:
            self.recorder.run(self.stop)
        except KeyboardInterrupt:
            log.info(t("status.quit"))

    def _run_menu_bar(self) -> None:
        from .hotkeys import DEFAULT_KEY, KEYS
        from .ui import MenuBar

        self.menu = MenuBar(self.cfg.sounds, self.cfg.hotkey.key)
        if self.cfg.hotkey.key not in KEYS:
            log.warning("unknown hotkey %r, using %s", self.cfg.hotkey.key, DEFAULT_KEY)
            self.cfg.hotkey.key = DEFAULT_KEY
        hotkeys = HotkeyManager(
            self.cfg.hotkey.hold_s, self.cfg.hotkey.double_tap_s, key=self.cfg.hotkey.key
        )

        def set_key(key: str) -> None:
            hotkeys.set_key(key)
            self.cfg.hotkey.key = key
            save_setting("hotkey", {"key": key})
            log.info(t("status.key", key=t(f"key.{key}")))

        request_all()  # the macOS prompts, at start rather than in the first dictation
        hotkeys.start()  # attached before the run loop starts; retried until allowed

        # Ctrl-C used to crash inside native code (onnxruntime, CoreAudio) when SIGINT landed
        # on a worker thread. Block it everywhere and handle it on one dedicated thread.
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT})
        worker: threading.Thread | None = None

        def shutdown() -> None:
            self.stop.set()
            if worker is not None and worker is not threading.current_thread():
                worker.join(timeout=3)
            log.info(t("status.quit"))
            os._exit(0)  # rumps' run loop does not return on its own

        def sigint_waiter() -> None:
            signal.sigwait({signal.SIGINT})
            shutdown()

        def start() -> None:
            try:
                transcriber, corrector = self.build_engine(self.cfg.language)
            except Exception as e:
                log.error("%s", e)
                shutdown()
                return
            self.recorder = self._make_recorder(transcriber, corrector)
            assert self.menu is not None
            self.menu.bind(
                warning_clicked=self._warning_clicked,
                quit=shutdown,
                glossary_path=str(self.glossary.path),
                log_path=str(LOG_FILE),
                sounds=lambda choice: save_setting("sounds", choice),
                key=set_key,
            )
            hotkeys.bind(
                toggle=self.recorder.toggle,
                hold_start=self.recorder.hold_start,
                hold_end=self.recorder.hold_end,
            )
            self.menu.ready()
            _on_main_thread(lambda: self._watch_permissions(hotkeys))
            send = t("status.ready_send") if self.cfg.send_return_after_hold else ""
            log.info(t("status.ready_hotkeys", send=send, key=t(f"key.{self.cfg.hotkey.key}")))
            self.recorder.run(self.stop)

        worker = threading.Thread(target=start, name="diga-recorder", daemon=True)
        worker.start()
        threading.Thread(target=sigint_waiter, daemon=True).start()
        self.menu.run()


def _on_main_thread(fn: Callable[[], None]) -> None:
    from PyObjCTools import AppHelper

    AppHelper.callAfter(fn)


def newly_granted(lacked: set[str], gaps: list[str], busy: bool) -> tuple[set[str], set[str]]:
    """(permissions granted since the last check, what is still lacking).

    While a dictation is running nothing counts as granted yet: the restart waits for it."""
    if busy:
        return set(), lacked
    return lacked - set(gaps), set(gaps)


def restart() -> None:
    """Replace this process with a fresh diga, same arguments (under diga.app too: same PID)."""
    os.execv(sys.executable, [sys.executable, *sys.argv])
