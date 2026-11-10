"""Command line: ``diga`` (run), ``diga doctor``, ``diga models``, ``diga autostart``."""

from __future__ import annotations

import argparse
import logging
import sys
import threading

from . import __version__
from .config import load_config
from .i18n import set_language


def _setup_logging(verbose: bool) -> None:
    """Plain messages in a terminal; timestamps when the log goes to a file (autostart).

    ``-v`` adds, for every chunk, what each recognizer heard and how long it took, how the
    second opinion settled each disagreement, and which terms were replaced.
    """
    in_terminal = sys.stderr.isatty()
    fmt = "%(message)s" if in_terminal else "%(asctime)s %(levelname)s %(message)s"
    if verbose and not in_terminal:
        fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format=fmt,
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    from .logfile import attach

    attach()
    for noisy in ("httpx", "huggingface_hub", "transformers", "urllib3", "filelock", "numba"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _config(args: argparse.Namespace):
    """config.yaml and menu settings, then the command-line overrides."""
    cfg = load_config()
    if getattr(args, "lang", None):
        cfg.language = args.lang
    if getattr(args, "languages", None):
        cfg.languages = [x.strip() for x in args.languages.split(",") if x.strip()]
    return cfg


def cmd_run(args: argparse.Namespace) -> int:
    cfg = _config(args)
    set_language(cfg.ui_language)
    from .app import App

    App(cfg, with_ui=not args.no_ui, print_only=args.print_only).run()
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from . import models
    from .asr import BACKENDS, installed
    from .permissions import host_app, run_checks

    cfg = _config(args)
    print(f"diga {__version__} · Python {sys.version.split()[0]} · host app: {host_app()}\n")
    print("Permissions")
    failed = False
    for check in run_checks():
        mark = {True: "✓", False: "✗", None: "?"}[check.ok]
        failed |= check.ok is False
        print(f"  {mark} {check.name}" + (f" — {check.detail}" if check.ok is not True else ""))
    print("\nRecognizers")
    for backend, (extra, langs) in BACKENDS.items():
        state = "installed" if installed(backend) else f"not installed (diga[{extra}])"
        print(f"  {backend:<9} {state:<34} {langs}")
    if cfg.language == "auto":
        langs, source = cfg.spoken_languages()
        print(f"\nYour languages: {', '.join(langs) or '—'} (from {source})")
        if cfg.wants_russian():
            russian = cfg.backend_for("ru") + (" + second opinion" if cfg.second_opinion else "")
        else:
            russian = f"{cfg.backend_for('auto')} (ru is not among your languages)"
        route = f"{cfg.backend_for('auto')}; Russian → {russian}"
    else:
        route = cfg.backend_for(cfg.language)
    print(f"Language: {cfg.language} → {route}")
    print(f"Glossary: {cfg.glossary_path()}")
    from .logfile import LOG_FILE

    print(f"Log: {LOG_FILE}  (diga logs, or Menu → Show log)")
    print("\nModels (downloaded on first use)")
    for spec in models.REGISTRY:
        cached = "✓ cached" if models.is_cached(spec) else "  —"
        print(
            f"  {cached:<9} {spec.key:<28} {spec.size_mb:>5} MB  {spec.license:<10} {spec.purpose}"
        )
    return 1 if failed else 0


def cmd_models(args: argparse.Namespace) -> int:
    from . import models

    wanted = set(args.download or [])
    default = {spec.key for spec in models.needed(_config(args))}
    for spec in models.REGISTRY:
        if spec.key in wanted or "all" in wanted or ("default" in wanted and spec.key in default):
            if not models.is_cached(spec):
                print(f"downloading {spec.key} ({spec.size_mb} MB)…")
            models.fetch(spec)
        cached = "✓" if models.is_cached(spec) else " "
        used = "  (used now)" if spec.key in default else ""
        print(f"  {cached} {spec.key:<28} {spec.repo}{used}")
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    from .logfile import LOG_FILE

    if not LOG_FILE.exists():
        print(f"no log yet: {LOG_FILE}")
        return 1
    print(f"==> {LOG_FILE}", flush=True)
    tail = ["tail", "-n", str(args.lines)] + (["-F"] if args.follow else [])
    import subprocess

    try:
        return subprocess.call([*tail, str(LOG_FILE)])
    except KeyboardInterrupt:
        return 0


def cmd_autostart(args: argparse.Namespace) -> int:
    from . import autostart

    if args.action == "install":
        extra = ["--lang", args.lang] if args.lang else []
        print(f"installed {autostart.install(extra)} — diga starts at login; log: {autostart.LOG}")
    elif autostart.uninstall():
        print("removed — diga no longer starts at login")
    else:
        print("autostart was not installed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="diga", description="Offline push-to-talk dictation.")
    p.add_argument("--version", action="version", version=f"diga {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = p.add_subparsers(dest="command")

    run = sub.add_parser("run", help="start dictation (default)")
    for target in (p, run):
        target.add_argument(
            "--lang", help="auto (default), ru, en, pt or any Whisper language code"
        )
        target.add_argument(
            "--languages",
            metavar="LIST",
            help="languages you dictate in, e.g. ru,en (default: this Mac's languages)",
        )
        target.add_argument(
            "--no-ui",
            action="store_true",
            help="no menu-bar icon; Enter in the terminal starts/stops",
        )
        target.add_argument(
            "--print-only", action="store_true", help="print the text instead of typing it"
        )
    run.set_defaults(func=cmd_run)
    sub.add_parser("doctor", help="check permissions, recognizers and models").set_defaults(
        func=cmd_doctor
    )
    models = sub.add_parser("models", help="list or download models")
    models.add_argument(
        "--download",
        nargs="*",
        metavar="KEY",
        help="model keys, 'default' (what your settings use) or 'all'",
    )
    models.set_defaults(func=cmd_models)
    logs = sub.add_parser("logs", help="show diga's log (what you dictated is never in it)")
    logs.add_argument("-n", "--lines", type=int, default=60)
    logs.add_argument("-f", "--follow", action="store_true", help="keep printing new lines")
    logs.set_defaults(func=cmd_logs)
    auto = sub.add_parser("autostart", help="start diga at login")
    auto.add_argument("action", choices=["install", "uninstall"])
    auto.add_argument("--lang", help="language to start with")
    auto.set_defaults(func=cmd_autostart)
    p.set_defaults(func=cmd_run)
    return p


def _thread_lock_for_progress_bars() -> None:
    """Give tqdm (Hugging Face's download bars) a plain thread lock.

    By default it creates a multiprocessing semaphore; diga exits with ``os._exit`` (the
    menu-bar run loop never returns), so the semaphore was never released and Python printed
    "resource_tracker: There appear to be 1 leaked semaphore objects" on quit.
    """
    try:
        from tqdm import tqdm
    except ImportError:
        return
    tqdm.set_lock(threading.RLock())


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    _thread_lock_for_progress_bars()
    sys.exit(args.func(args))
