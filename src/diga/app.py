"""Wiring: recognizer + term corrector + recorder + hotkeys + menu bar."""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from collections.abc import Callable

from .asr import MissingBackend, Transcriber, create_transcriber
from .config import Config, save_setting
from .i18n import t
from .permissions import can_post_events, host_app
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

    # --- engine (recognizer + corrector) ---

    def build_engine(self, language: str) -> tuple[Transcriber, Corrector | None]:
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
        detector = create_transcriber("auto", self.cfg, prompt=whisper_prompt(self.glossary))
        try:
            log.info(t("status.loading", model=self.cfg.backend_for("ru")))
            russian = create_transcriber("ru", self.cfg)
        except MissingBackend:
            log.info(t("status.russian_missing"))
            return detector, False
        from .asr.auto import AutoTranscriber

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
        allowed = can_post_events()
        if allowed is False:
            log.warning(t("status.no_typing", app=host_app()))
        if self.menu:
            self.menu.warning(t("menu.no_typing") if allowed is False else None)

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
        from .hotkeys import HotkeyManager
        from .ui import MenuBar

        self.menu = MenuBar(self.cfg.sounds)
        hotkeys = HotkeyManager(self.cfg.hotkey.hold_s, self.cfg.hotkey.double_tap_s)
        hotkeys.start()  # must be attached before the run loop starts

        # Ctrl-C used to crash inside native code (onnxruntime, CoreAudio) when SIGINT landed
        # on a worker thread. Block it everywhere and handle it on one dedicated thread.
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT})
        worker: threading.Thread | None = None

        def shutdown() -> None:
            self.stop.set()
            if worker is not None:
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
                quit=shutdown,
                glossary_path=str(self.glossary.path),
                sounds=lambda choice: save_setting("sounds", choice),
            )
            hotkeys.bind(
                toggle=self.recorder.toggle,
                hold_start=self.recorder.hold_start,
                hold_end=self.recorder.hold_end,
            )
            self.menu.ready()
            send = t("status.ready_send") if self.cfg.send_return_after_hold else ""
            log.info(t("status.ready_hotkeys", send=send))
            self.recorder.run(self.stop)

        worker = threading.Thread(target=start, name="diga-recorder", daemon=True)
        worker.start()
        threading.Thread(target=sigint_waiter, daemon=True).start()
        self.menu.run()
