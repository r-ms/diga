# Benchmarks

Reproduce with `uv run python benchmarks/latency.py` and `uv run python benchmarks/terms.py synthetic`.

## Latency per chunk

Apple M4 Pro, models warm, median of 3 runs. After you release the key diga only recognizes the
last chunk, so this is roughly the wait between releasing ⌘ and the text appearing (plus typing).

| Setting | Speech | Recognizer | Audio | Recognition | Term correction | Total |
|---|---|---|---|---|---|---|
| **auto (default)** | Russian | Parakeet → GigaAM + language model | 8.9 s | 0.29 s | 239 ms | **0.35 s** |
| **auto (default)** | English | Parakeet | 7.6 s | 0.10 s | 36 ms | **0.14 s** |
| **auto (default)** | Portuguese | Parakeet | 9.2 s | 0.12 s | 34 ms | **0.15 s** |
| ru | Russian | GigaAM alone | 8.9 s | 0.13 s | 235 ms | 0.24 s |
| ru + second opinion | Russian | GigaAM + Parakeet + language model | 8.9 s | 0.29 s | 238 ms | 0.35 s |
| en | English | Parakeet | 7.6 s | 0.10 s | 33 ms | 0.14 s |
| pt | Portuguese | Parakeet | 9.2 s | 0.11 s | 27 ms | 0.14 s |

*Total* is what you wait for: the acoustic term model needs only the audio, so diga starts it
together with the recognizer, and most of its time is hidden. Typing goes out in pieces of up
to 20 characters per key event — a 250-character chunk takes about 0.05 s to type.

In `auto`, the first Russian chunk after an English or Portuguese one takes about 0.2 s longer:
GigaAM starts only once Parakeet has shown the chunk is Russian. From then on it starts in
parallel.

## Technical terms in Russian speech

Twenty Russian sentences of the kind you say to a coding agent, with 29 English technical terms
("Сделай коммит и пуш в гит", "Подними докер с редисом и постгресом"…), spoken by the macOS voice
*Milena*, recognized by GigaAM v3, corrected with the [built-in glossary](../src/diga/data/glossary.builtin.yaml).
*Terms right* counts expected terms spelled correctly in the output; *false replacements* counts
words a corrector introduced that were not expected terms.

| Output | Terms right | False replacements |
|---|---|---|
| Recognizer only | 2 / 29 (7%) | — |
| Text matching only | 13 / 29 (45%) | 0 |
| Acoustic spotting only | 14 / 29 (48%) | 1 |
| **Acoustic + text (diga's default for Russian)** | **18 / 29 (62%)** | **1** |

The two methods fix different errors, which is why diga chains them:

| Recognizer wrote | Acoustic spotting | Text matching |
|---|---|---|
| Запусти **Алламу** | ollama ✓ | — (too garbled) |
| Сделай комнаты **пужгид** | git ✓ | — |
| сделай **браничат** девелопа | branch ✓ | — |
| Обнови **Макрус** | macOS ✓ | — |
| тест на **пайтоне** | — (not spotted) | Python ✓ |
| Запусти **вил** | — | vLLM ✓ |
| запусти **клод-код** | — | Claude Code ✓ |

The remaining false replacement is *gid hoppy → git hoppy* (should have been GitHub).

## Second opinion for Russian

The same twenty sentences, ten sentences mixing Russian with English words and phrases ("Это
low probability событие", "Сделай pull request и добавь code review") and ten ordinary Russian
sentences ("Напомни мне купить молоко и хлеб по дороге домой"). *Word errors* is the word-level
edit distance to what was said, before term correction; *terms right* is after diga's default
correction (acoustic + text).

| Recognizer | Word errors: technical | Word errors: mixed ru/en | Word errors: ordinary | Terms right |
|---|---|---|---|---|
| GigaAM | 45 / 126 (36%) | 25 / 74 (34%) | 2 / 83 (2%) | 18 / 29 (62%) |
| GigaAM + Parakeet (by confidence) | 39 / 126 (31%) | 29 / 74 (39%) | 2 / 83 (2%) | 22 / 29 (76%) |
| GigaAM + Parakeet + language model | 36 / 126 (29%) | 30 / 74 (41%) | 2 / 83 (2%) | 22 / 29 (76%) |
| **auto (diga's default)** | **36 / 126 (29%)** | 30 / 74 (41%) | **2 / 83 (2%)** | **22 / 29 (76%)** |

GigaAM's word confidence is low exactly where it errs (*Алламу* 0.66, *пужгид* 0.71, *Макрус*
0.60, *Соберидоробрас* 0.75; correctly heard words are mostly above 0.9), and Parakeet often has
the right word there: *Соберидоробрас и запусти → Собери докер образ и запуши*, *Макрус → Макос*,
*пыд → под*; a word GigaAM dropped altogether (*двух [эл эл эм] моделей*) is inserted from
Parakeet. On ordinary speech GigaAM is rarely unsure, so the merge changes nothing there. The
default `auto` gives exactly the same text: every one of these chunks is detected as Russian and
goes through the same merge.

The language model (Qwen3 0.6B) reads both wordings of each disagreement in context. In a pairwise
check it preferred the right wording in 8 of 9 cases, including *maybe just small* over *maby Just
Смоу* and — in the other direction — GigaAM's correct *логи Редиса* over Parakeet's *логер Диса*.

**The mixed column is not meaningful with a synthetic voice.** The macOS voice reads English
words with Russian phonetics, so Parakeet hears them as Russian and writes Cyrillic
transliterations (*эдж кейс*, *квик фикс*, *муфаст энд брейк сингс*), while the reference is in
Latin script; the edit distance counts every transliteration as an error even where it is closer
to what was said than GigaAM's *Посмотри на этот gase*. With a real speaker Parakeet does write
English in Latin script. Real recordings decide this column.

**Caveats.** A synthetic voice is cleaner and more regular than a person; twenty sentences is a
small set; and the acoustic similarity threshold (0.65), the second-opinion thresholds (0.8, 0.85) and
the language-model margin (0.25) were chosen on this same set. Treat the
numbers as a sanity check, not a result. `benchmarks/terms.py record DIR` records the same
sentences with your own voice and `evaluate DIR` scores them — real-voice numbers will replace
these.
