# diga

[![CI](https://github.com/r-ms/diga/actions/workflows/ci.yml/badge.svg)](https://github.com/r-ms/diga/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11–3.13-blue)](pyproject.toml)
![macOS](https://img.shields.io/badge/macOS-Apple%20Silicon-lightgrey)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Hold a key, speak, and your words are typed into whatever app has focus — fully offline.**
Built for talking to coding agents (Claude Code, Codex, Aider…) in the terminal: release the
key and the prompt is sent.

*Diga* is Portuguese for "go ahead, I'm listening" — how people answer the phone in Portugal.

```bash
brew install r-ms/tools/diga && diga models --download default && brew services start diga
```

<!-- docs/demo.gif — hold right ⌘ → speak → Claude Code receives the prompt -->

- **Push-to-talk on the right ⌘.** Hold to dictate; release to type the text and press Return.
  Double-tap for a long dictation without holding. Press another key while holding (⌘C, ⌘Tab)
  and the recording is discarded — it was a shortcut, not dictation.
- **Types, doesn't paste.** Text is sent as Unicode key events: your clipboard is never touched,
  and it works in terminals where pasting behaves differently.
- **Text appears while you speak.** Long dictation is cut into 10–20 s chunks at natural pauses
  and each chunk is typed as soon as it is recognized; after you stop, only the last chunk is
  left (≈0.1–0.5 s on an M4 Pro, see [benchmarks](docs/benchmarks.md)).
- **Technical terms come out right.** A glossary fixes what recognizers mangle — *cube ernetes →
  Kubernetes*, *cômite → commit*, *пужгид → git* — with about 30 common developer terms built in
  and your own on top.
- **Nothing to choose.** Speak English, Portuguese or any of 23 more European languages, and
  switch between them mid-sentence: every chunk's language is detected on its own.
- **Extra-strong Russian, including Russian mixed with English.** If you speak Russian, diga
  adds GigaAM, the strongest open Russian recognizer, listens for technical terms in the audio
  itself, and lets a small language model (Qwen3 0.6B) settle where GigaAM and Parakeet
  disagree — *maby Just Смоу* becomes *maybe just small*. In our benchmark correct terms go from
  7% to 76% ([details](docs/benchmarks.md)). If you don't, none of it is downloaded or loaded.
- **Private.** Audio never leaves your Mac; the microphone is open only while you dictate. No
  accounts, no telemetry. Models are downloaded once from Hugging Face.

## Install

Requires a Mac with Apple Silicon (M1 or newer) and macOS 14+, and [Homebrew](https://brew.sh).

```bash
brew install r-ms/tools/diga
diga models --download default   # once: diga's Python packages and the models
brew services start diga         # start now and at every login
```

Then hold the right ⌘ and speak. Upgrade with `brew upgrade diga`.

macOS asks for three permissions for diga: **Microphone**, **Accessibility** and **Input
Monitoring** — the last two to see the ⌘ key and to type. `diga doctor` shows what is missing
and where to switch it on. diga uses about 4 GB of memory with Russian among your languages
and 1.6 GB without.

<details><summary>Other ways to install (without Homebrew)</summary>

One script that installs [uv](https://docs.astral.sh/uv/) if needed, then diga, the models and
the login item:

```bash
curl -LsSf https://raw.githubusercontent.com/r-ms/diga/main/install.sh | sh
```

Or step by step with uv:

```bash
uv tool install "diga[ru,parakeet] @ git+https://github.com/r-ms/diga"   # extras: ru, parakeet, whisper, all
diga models --download default
diga autostart install           # start at login
```

</details>

## Languages

| Language | Recognizer | Download | Term correction |
|---|---|---|---|
| Russian | [GigaAM v3](https://huggingface.co/ai-sage/GigaAM-v3) — state-of-the-art open Russian ASR | 450 MB + 225 MB | acoustic + text |
| English, Portuguese (European) + 23 European languages | [Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) (MLX) | 2.5 GB | text |
| Everything else Whisper knows | [Whisper large-v3-turbo](https://huggingface.co/mlx-community/whisper-large-v3-turbo) (MLX) | 1.6 GB | glossary as prompt + text |

There is no language to pick. Parakeet hears every chunk and detects its language, so English,
Portuguese and the rest come straight from it. Parakeet v3 was trained on European Portuguese,
so Portugal's Portuguese is a first-class citizen.

Russian is handled by GigaAM when Russian is among **your languages**: by default the languages
your Mac shows (System Settings → General → Language & Region, and your keyboard layouts), or
the list you set yourself — `languages: [ru, en]` in the [configuration](#configuration), or
`--languages ru,en`. Then a chunk Parakeet writes mostly in Cyrillic is recognized again by
GigaAM, with Parakeet's version as a second opinion and the Russian term correction. Without
Russian, diga uses about 1.6 GB of memory instead of 4 GB, and if it hears Russian anyway it
says once how to turn the Russian recognizer on. To pin one language, set `language: en`.

## Use

| Action | What happens |
|---|---|
| Hold right ⌘, speak, release | Text is typed, then Return |
| Hold right ⌘ and press another key | Treated as a shortcut — nothing is typed |
| Double-tap right ⌘ | Start a long dictation; double-tap again to stop (no Return) |
| Menu → Key | Right ⌘ (default), right ⌥ or Fn (🌐) |
| Menu → Sound | Soft, Tick, Drop, Chime or Off — you hear each one as you pick it |
| Menu → Open glossary | Edit your terms; changes apply to the next dictation |
| Menu → Show log | What diga is doing, in Console (never what you dictated); also `diga logs` |

Left ⌘ is not offered on purpose: ⌘-click and ⌘-drag press no other key, so they would start
recordings. With Fn (🌐), set System Settings → Keyboard → "Press 🌐 key to" → *Do Nothing*, or
macOS opens emoji or its own dictation when you release it.

`diga --no-ui` runs without the menu bar (Enter starts and stops); `--print-only` prints instead
of typing — handy for trying it out. `diga -v` explains every chunk: what each recognizer heard,
how disagreements were settled and which terms were replaced.

### Glossary

diga already knows about 30 common developer terms ([the built-in list](src/diga/data/glossary.builtin.yaml):
git, GitHub, Docker, Redis, Kubernetes, ollama, Claude Code…); they come with diga and are
updated with it. Menu → Open glossary opens your own `~/.config/diga/glossary.yaml` in your text
editor — it starts as a short template. Add your terms and the ways the recognizer actually
writes them (`diga -v` shows every chunk), per language or as one list for all:

```yaml
terms:
  - term: Grafana
    pron_variants:
      ru: [графана, графона]
      en: [graph ana]
  - term: Mikhail
    pron_variants: [michael, mikael]
```

A built-in term listed again gets your spellings as well; `use_builtin: false` keeps only
yours. Changes apply to the next dictation.

### Configuration

The defaults are meant to be the best choice, so the menu only lets you pick a sound. To
change anything else,
create `~/.config/diga/config.yaml`:

```yaml
language: en                    # pin one language instead of auto: ru | en | pt | Whisper code
languages: [ru, en]             # the languages you dictate in (default: your Mac's languages)
send_return_after_hold: false   # type the text but don't press Return
sounds: ~/my-sounds             # your own start.wav / done.wav (or soft, tick, drop, chime, off)
second_opinion: false           # Russian: GigaAM alone (with language: ru, Parakeet is not loaded)
second_opinion_lm: false        # no language model judge (~0.4 GB; off by default on 8 GB Macs)
backends: {de: whisper}         # which recognizer handles which language
hotkey: {key: fn}               # right_cmd (default), right_option or fn
chunking: {min_chunk_s: 8}      # cut at the first pause after 8 s instead of 10
terms: {ctc_precision: fp32}    # full-precision spotter (886 MB) instead of int8 (225 MB)
```

See [`config.py`](src/diga/config.py) for every setting.

## How it works

```
hold the key ──► recorder ──► chunks at pauses ──► Parakeet: text + language ──► typed into
 (right ⌘)       mic open     (10–20 s, energy)     Russian? GigaAM re-hears it,    the focused
                 only now                           a small LM settles disagreements app (+ Return)
                                                    then glossary terms are fixed
```

The [architecture notes](docs/architecture.md) explain each step and the design decisions;
[adding a language](docs/adding-a-language.md) shows how to plug in another recognizer.

## Troubleshooting

- **Nothing happens when you hold the key.** The menu shows ⚠ with what is missing ("No keyboard
  access — open Settings…"). Click it, turn **diga** on in the page that opens (Input Monitoring,
  Accessibility or Microphone; run from a terminal, it is the terminal app instead), and diga
  restarts itself as soon as macOS allows it. `diga doctor` lists what is missing.
- **What is diga doing?** Menu → Show log, or `diga logs -f` in a terminal. What you dictated is
  never written there.
- **`brew upgrade diga` says the latest version is installed.** Homebrew refreshes its formulas
  at most once a day: run `brew update` first.
- **First dictation is slow.** The models are still downloading; `diga models --download default`
  fetches the ones your settings use ahead of time.

## How diga compares

As of November 2026; corrections welcome.

| | diga | [Handy](https://github.com/cjpais/Handy) | [VoiceInk](https://github.com/Beingpax/VoiceInk) | [OpenWhispr](https://github.com/OpenWhispr/openwhispr) |
|---|---|---|---|---|
| License | MIT | MIT | GPL-3.0, paid builds | MIT |
| Platforms | macOS (Apple Silicon) | macOS, Windows, Linux | macOS | macOS, Windows, Linux |
| Inserts text by | typing key events | clipboard paste (typing optional) | clipboard paste (typing optional) | clipboard paste |
| Press Return after dictation | yes, after hold-to-talk | optional | optional | no, by design |
| Custom terms | acoustic spotting (ru) + text matching | text fuzzy matching | phonetic text matching | passed to the model as context |

Handy is the more complete cross-platform app; VoiceInk the more polished native Mac app.
diga is small (about 4k lines of Python), focused on the terminal and on getting technical
vocabulary right, and easy to read and change.

## Development

```bash
git clone https://github.com/r-ms/diga && cd diga
uv sync                       # dev tools and every recognizer
uv run diga                   # run from the source tree (permissions go to your terminal)
uv run pytest                 # unit tests, no models needed
uv run pytest -m models       # end-to-end with real models and macOS voices
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run pre-commit install     # optional: ruff on every commit
uv run python benchmarks/latency.py
uv run python benchmarks/terms.py synthetic
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

diga stands on [GigaAM](https://github.com/salute-developers/GigaAM) (Salute Developers, MIT),
[NVIDIA Parakeet](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) (CC-BY-4.0) via
[parakeet-mlx](https://github.com/senstella/parakeet-mlx), [Whisper](https://github.com/openai/whisper)
via [mlx-whisper](https://github.com/ml-explore/mlx-examples), [Qwen3](https://huggingface.co/Qwen/Qwen3-0.6B)
(Apache-2.0) via [mlx-lm](https://github.com/ml-explore/mlx-lm), and the CTC word-spotting idea
from NeMo (Andrusenko et al., 2024). Models are not bundled; see [NOTICE](NOTICE).

MIT © Mikhail Rakutko
