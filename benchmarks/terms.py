"""How many technical terms come out right, and how many words overall.

Compares term correction methods (text matching, acoustic spotting, both) and recognizer
setups (GigaAM alone vs. GigaAM with Parakeet as a second opinion).

    uv run python benchmarks/terms.py synthetic            # macOS voice, quick sanity check
    uv run python benchmarks/terms.py record DIR           # record the phrases with your voice
    uv run python benchmarks/terms.py evaluate DIR         # score your recordings

Metrics: term recall — the share of expected terms that appear, spelled correctly, in the
output; false replacements — words a corrector introduced that are not expected terms; word
errors — edit distance to what was said (before term correction), on the phrases with terms and
separately on ordinary phrases, so a change that helps terms cannot silently hurt plain speech.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from common import read_wav, say, word_errors, write_wav

# Russian dictation with English tech terms: what you say to a coding agent.
PHRASES: list[tuple[str, list[str]]] = [
    ("Запусти оллама и проверь, что модель скачалась.", ["ollama"]),
    ("Сделай коммит и пуш в гит.", ["commit", "push", "git"]),
    ("Открой гитхаб и создай пиар на мёрдж в мейн.", ["GitHub", "PR", "merge"]),
    ("Подними докер с редисом и постгресом.", ["Docker", "Redis", "PostgreSQL"]),
    ("Перезапусти под в кубернетесе.", ["Kubernetes"]),
    ("Проверь эндпоинт апи и посмотри джейсон в ответе.", ["endpoint", "API", "JSON"]),
    ("Поправь ямл конфиг и закоммить.", ["YAML"]),
    ("Напиши тест на пайтоне для этой функции.", ["Python"]),
    ("Переведи модуль на тайпскрипт.", ["TypeScript"]),
    ("Обнови пакеты через энпиэм.", ["npm"]),
    ("Подключи эм си пи сервер к клоду.", ["MCP"]),
    ("Сравни ответы двух эл эл эм моделей.", ["LLM"]),
    ("Запусти виллм на второй видеокарте.", ["vLLM"]),
    ("Открой проект в курсоре и найди этот класс.", ["Cursor"]),
    ("Создай ветку и сделай бранч от девелопа.", ["branch"]),
    ("Открой айтерм и запусти клод код.", ["iTerm", "Claude Code"]),
    ("Залей изменения в гитлаб и проверь пайплайн.", ["GitLab"]),
    ("Собери докер образ и запушь его в реестр.", ["Docker"]),
    ("Посмотри логи редиса за последний час.", ["Redis"]),
    ("Обнови макос и перезагрузи машину.", ["macOS"]),
]

# Ordinary Russian dictation without technical terms: a change must not make these worse.
ORDINARY: list[str] = [
    "Привет, давай созвонимся завтра в десять утра.",
    "Напомни мне купить молоко и хлеб по дороге домой.",
    "Я думаю, что нам стоит перенести встречу на следующую неделю.",
    "Сегодня в Лиссабоне солнечно и довольно тепло.",
    "Пожалуйста, перечитай этот абзац и сделай его короче.",
    "Мы обсудили бюджет и решили сократить расходы на рекламу.",
    "Отправь клиенту письмо с итогами нашей встречи.",
    "Сколько времени займёт эта задача, если начать прямо сейчас?",
    "Мне кажется, этот вариант понятнее для обычного пользователя.",
    "Добавь в отчёт таблицу с результатами за прошлый месяц.",
]
# Russian with English words and phrases mixed in — how many people actually talk.
MIXED: list[str] = [
    "Давай попробуем maybe just small pieces of text и посмотрим.",
    "Это low probability событие, но проверить стоит.",
    "Я думаю, что это best practice для нашего проекта.",
    "Сделай pull request и добавь code review.",
    "Нам нужен feature flag для этой функции.",
    "Посмотри на этот edge case в тестах.",
    "Это просто proof of concept, а не продакшн.",
    "Давай сделаем quick fix, а потом refactoring.",
    "Как говорится, move fast and break things.",
    "Проверь, что deadline не сдвигается.",
]
MIXED_SET = set(MIXED)
ALL_PHRASES: list[tuple[str, list[str]]] = (
    PHRASES + [(p, []) for p in MIXED] + [(p, []) for p in ORDINARY]
)


def term_hits(text: str, terms: list[str]) -> int:
    return sum(term in text for term in terms)


def changed_non_terms(raw: str, fixed: str, terms: list[str]) -> int:
    """Words the corrector introduced that are not expected terms (false replacements)."""
    raw_words = set(raw.replace(",", " ").replace(".", " ").split())
    new = [w for w in fixed.replace(",", " ").replace(".", " ").split() if w not in raw_words]
    allowed = {part for t in terms for part in t.split()}
    return sum(w not in allowed for w in new)


AUTO_SETUP = "Auto (diga's default)"


def load_engines() -> tuple[Any, dict[str, Any], dict[str, tuple[Any, Any]]]:
    """Recognizer setups and correction variants, sharing one glossary and CTC model."""
    from diga.asr import create_transcriber
    from diga.config import Config
    from diga.terms import ByLanguage, ChainCorrector
    from diga.terms.acoustic import AcousticCorrector
    from diga.terms.ctc import GigaAMCtc
    from diga.terms.fuzzy import FuzzyCorrector
    from diga.terms.glossary import GlossaryFile, ensure_glossary

    cfg = Config(language="ru")
    glossary_path = Path(__file__).parent / "results" / "glossary.bench.yaml"
    glossary_path.unlink(missing_ok=True)
    glossary = GlossaryFile(ensure_glossary(glossary_path))  # the bundled example glossary
    asr = create_transcriber("ru", cfg)
    asr.warmup()
    ctc = GigaAMCtc.from_hub(cfg.terms.ctc_precision)
    text = FuzzyCorrector(glossary, "ru", cfg.terms.fuzzy_threshold)
    variants: dict[str, Any] = {"text matching": text}
    for sim in (0.55, 0.65):
        acoustic = AcousticCorrector(ctc, glossary, min_similarity=sim)
        variants[f"acoustic (sim ≥ {sim})"] = acoustic
        variants[f"acoustic + text (sim ≥ {sim})"] = ChainCorrector(acoustic, text)
    default = ChainCorrector(
        AcousticCorrector(ctc, glossary, min_similarity=cfg.terms.acoustic_min_similarity), text
    )
    recognizers: dict[str, Any] = {"GigaAM": asr}
    try:
        from diga.asr.parakeet import ParakeetTranscriber
        from diga.asr.second_opinion import SecondOpinionTranscriber

        second = ParakeetTranscriber()
        second.warmup()
        recognizers["GigaAM + second opinion (Parakeet)"] = SecondOpinionTranscriber(
            asr, second, cfg.second_opinion_unsure, cfg.second_opinion_insert
        )
        from diga.asr.plausibility import PlausibilityModel

        lm = PlausibilityModel()
        lm.warmup()
        recognizers["GigaAM + second opinion + language model"] = SecondOpinionTranscriber(
            asr,
            second,
            cfg.second_opinion_unsure,
            cfg.second_opinion_insert,
            lm.score,
            cfg.second_opinion_lm_margin,
        )
        from diga.asr.auto import AutoTranscriber

        # diga's default: language "auto" — Parakeet detects, GigaAM re-hears Russian chunks
        recognizers[AUTO_SETUP] = AutoTranscriber(
            second,
            asr,
            unsure=cfg.second_opinion_unsure,
            insert=cfg.second_opinion_insert,
            judge=lm.score,
            margin=cfg.second_opinion_lm_margin,
        )
        auto_fix = ByLanguage(
            FuzzyCorrector(glossary, "auto", cfg.terms.fuzzy_threshold), ru=default
        )
        recognizers[AUTO_SETUP] = (recognizers[AUTO_SETUP], auto_fix)
    except ImportError:
        print("(Parakeet not installed — skipping the second-opinion comparison)")
    # name → (recognizer, corrector); the Russian setups all use diga's Russian correction
    setups = {k: v if isinstance(v, tuple) else (v, default) for k, v in recognizers.items()}
    return asr, variants, setups


def score(samples: list[tuple[np.ndarray, str, list[str]]], label: str) -> None:
    asr, variants, recognizers = load_engines()
    with_terms = [x for x in samples if x[2]]
    n = sum(len(terms) for _, _, terms in with_terms)
    raw_hits = 0
    hits = dict.fromkeys(variants, 0)
    damage = dict.fromkeys(variants, 0)
    rows = []
    for audio, phrase, terms in with_terms:
        tr = asr.transcribe(audio)
        raw_hits += term_hits(tr.text, terms)
        row = {"phrase": phrase, "raw": tr.text}
        for name, corrector in variants.items():
            out = corrector.correct(audio, tr)
            hits[name] += term_hits(out, terms)
            damage[name] += changed_non_terms(tr.text, out, terms)
            row[name] = out
        rows.append(row)
    print(f"\n## Term correction — {label} ({len(with_terms)} phrases, {n} terms, GigaAM)\n")
    print("| Output | Terms right | False replacements |")
    print("|---|---|---|")
    print(f"| Recognizer only (GigaAM) | {raw_hits}/{n} ({raw_hits / n:.0%}) | — |")
    for name in variants:
        print(f"| {name} | {hits[name]}/{n} ({hits[name] / n:.0%}) | {damage[name]} |")

    print(f"\n## Recognizer setups — {label}\n")
    print(
        "| Recognizer | Word errors: technical | Word errors: mixed ru/en "
        "| Word errors: ordinary | Terms right after correction |"
    )
    print("|---|---|---|---|---|")
    for name, (rec, fixer) in recognizers.items():
        errors = {"terms": [0, 0], "mixed": [0, 0], "plain": [0, 0]}
        right = 0
        for audio, phrase, terms in samples:
            tr = rec.transcribe(audio)
            kind = "terms" if terms else ("mixed" if phrase in MIXED_SET else "plain")
            e, m = word_errors(phrase, tr.text)
            errors[kind][0] += e
            errors[kind][1] += m
            if terms:
                right += term_hits(fixer.correct(audio, tr), terms)
            row = next((r for r in rows if r["phrase"] == phrase), None)
            if row is None:
                row = {"phrase": phrase}
                rows.append(row)
            row[name] = tr.text
        cells = [f"{e}/{m} ({e / m:.0%})" if m else "—" for e, m in errors.values()]
        print(f"| {name} | {' | '.join(cells)} | {right}/{n} ({right / n:.0%}) |")
    out_path = Path(__file__).parent / "results" / f"terms-{label}.local.jsonl"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), "utf-8")
    print(f"\nper-phrase output: {out_path}")


def cmd_synthetic(args: argparse.Namespace) -> None:
    samples = [(say(p, args.voice), p, t) for p, t in ALL_PHRASES]
    score(samples, f"synthetic-{args.voice}")


def cmd_record(args: argparse.Namespace) -> None:
    from diga.audio import Microphone

    out = Path(args.dir)
    out.mkdir(parents=True, exist_ok=True)
    meta = []
    for i, (phrase, terms) in enumerate(ALL_PHRASES, 1):
        input(f"\n[{i}/{len(ALL_PHRASES)}] {phrase}\n  Enter — start, then read the phrase…")
        frames: list[np.ndarray] = []
        stop = False
        import threading

        def wait_enter() -> None:
            nonlocal stop
            input("  recording… Enter — stop")
            stop = True

        threading.Thread(target=wait_enter, daemon=True).start()
        with Microphone() as mic:
            while not stop:
                f = mic.read(0.1)
                if f is not None:
                    frames.append(f)
        path = out / f"{i:02d}.wav"
        write_wav(path, np.concatenate(frames))
        meta.append({"audio": path.name, "text": phrase, "terms": terms})
    (out / "phrases.jsonl").write_text(
        "\n".join(json.dumps(m, ensure_ascii=False) for m in meta), encoding="utf-8"
    )
    print(f"\nsaved {len(meta)} recordings to {out}")


def cmd_evaluate(args: argparse.Namespace) -> None:
    d = Path(args.dir)
    rows = [json.loads(line) for line in (d / "phrases.jsonl").read_text().splitlines() if line]
    samples = [(read_wav(d / r["audio"]), r["text"], r["terms"]) for r in rows]
    score(samples, d.name)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("synthetic")
    s.add_argument("--voice", default="Milena")
    s.set_defaults(func=cmd_synthetic)
    r = sub.add_parser("record")
    r.add_argument("dir")
    r.set_defaults(func=cmd_record)
    e = sub.add_parser("evaluate")
    e.add_argument("dir")
    e.set_defaults(func=cmd_evaluate)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
