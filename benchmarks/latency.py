"""How long recognition takes per chunk, for each installed recognizer.

    uv run python benchmarks/latency.py

After you release the key, diga only has to recognize the last chunk (≤ 20 s, usually a few
seconds), so "time per chunk" is what you wait for. Median of 3 runs after a warm-up.
"""

from __future__ import annotations

import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import say

TEXTS = {
    "ru": (
        "Milena",
        "Сделай коммит и пуш в гит, потом открой гитхаб и создай пиар на мёрдж в "
        "основную ветку, а после этого проверь, что сборка прошла и тесты зелёные.",
    ),
    "en": (
        "Samantha",
        "Commit the changes and push them to git, then open GitHub and create a "
        "pull request into the main branch, and check that the build and tests pass.",
    ),
    "pt": (
        "Joana",
        "Faz o commit das alterações, envia para o repositório, abre um pedido de "
        "integração para o ramo principal e confirma que a compilação passou.",
    ),
}


def chip() -> str:
    out = subprocess.run(
        ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True
    ).stdout.strip()
    return out or platform.machine()


# (language setting, second opinion, which speech to feed it)
SETUPS = [
    ("ru", False, "ru"),
    ("ru", True, "ru"),
    ("en", False, "en"),
    ("pt", False, "pt"),
    ("auto", True, "ru"),
    ("auto", True, "en"),
    ("auto", True, "pt"),
]


def main() -> None:
    from diga.app import App
    from diga.config import Config
    from diga.terms import prefetch

    glossary = Path(__file__).parent / "results" / "glossary.lat.yaml"
    print(f"\n## Latency per chunk — {chip()}\n")
    print("| Setting | Speech | Recognizer | Audio | Recognition | Term correction | Total |")
    print("|---|---|---|---|---|---|---|")
    engines: dict[tuple[str, bool], tuple] = {}
    for lang, second, speech in SETUPS:
        cfg = Config(language=lang, second_opinion=second)
        cfg.terms.glossary = str(glossary)
        setting = lang + (" + second opinion" if second and lang != "auto" else "")
        try:
            if (lang, second) not in engines:
                engines.clear()  # one setup in memory at a time
                engines[(lang, second)] = App(cfg, with_ui=False).build_engine(lang)
            asr, corrector = engines[(lang, second)]
        except Exception as e:
            print(f"| {setting} | {speech} | — | — | not installed ({e}) | — |")
            continue
        voice, text = TEXTS[speech]
        audio = say(text, voice)
        asr.transcribe(audio)
        rec, cor, total = [], [], []
        for _ in range(3):
            t0 = time.perf_counter()  # as diga runs it: the term model starts in parallel
            if corrector:
                prefetch(corrector, audio)
            tr = asr.transcribe(audio)
            if corrector:
                corrector.correct(audio, tr)
            total.append(time.perf_counter() - t0)
            t0 = time.perf_counter()
            tr = asr.transcribe(audio)
            rec.append(time.perf_counter() - t0)
            if corrector:
                t0 = time.perf_counter()
                corrector.correct(audio, tr)
                cor.append(time.perf_counter() - t0)
        fix = f"{statistics.median(cor) * 1000:.0f} ms" if cor else "—"
        print(
            f"| {setting} | {speech} | {asr.name} | {len(audio) / 16000:.1f} s | "
            f"{statistics.median(rec):.2f} s | {fix} | {statistics.median(total):.2f} s |"
        )


if __name__ == "__main__":
    main()
