# diga

[![CI](https://github.com/r-ms/diga/actions/workflows/ci.yml/badge.svg)](https://github.com/r-ms/diga/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11–3.13-blue)](pyproject.toml)
![macOS](https://img.shields.io/badge/macOS-Apple%20Silicon-lightgrey)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Hold a key, speak, and your words are typed into whatever app has focus — fully offline.**
Built for talking to coding agents (Claude Code, Codex, Aider…) in the terminal: release the
key and the prompt is sent.

*Diga* is Portuguese for "go ahead, I'm listening" — how people answer the phone in Portugal.

<!-- docs/demo.gif — hold right ⌘ → speak → Claude Code receives the prompt -->

- **Push-to-talk on the right ⌘.** Hold to dictate; release to type the text and press Return.
  Double-tap for a long dictation without holding. Press another key while holding (⌘C, ⌘Tab)
  and the recording is discarded — it was a shortcut, not dictation.
- **Types, doesn't paste.** Text is sent as Unicode key events: your clipboard is never touched,
  and it works in terminals where pasting behaves differently.
- **Text appears while you speak.** Long dictation is cut into 10–20 s chunks at natural pauses
  and each chunk is typed as soon as it is recognized; after you stop, only the last chunk is
  left (≈0.1–0.5 s on an M4 Pro, see [benchmarks](docs/benchmarks.md)).
- **Technical terms come out right.** A glossary fixes what recognizers mangle — *пужгид → git*,
  *Алламу → ollama*, *cômite → commit*. For Russian, diga listens for the terms in the audio
  itself (CTC keyword spotting) and then also matches text; in our benchmark that lifts correct
  terms from 7% to 62% ([details](docs/benchmarks.md)).
- **Nothing to choose.** Speak Russian, English, Portuguese or switch between them mid-sentence:
  every chunk's language is detected on its own. Russian goes to GigaAM, and where GigaAM and
  Parakeet disagree, a small language model (Qwen3 0.6B) reads both wordings in context and
  picks the likelier one — *maby Just Смоу* becomes *maybe just small* without any glossary.
  In our benchmark: correct terms 62% → 76%, word errors on technical dictation 36% → 29%,
  unchanged on plain speech.
- **Private.** Audio never leaves your Mac; the microphone is open only while you dictate. No
  accounts, no telemetry. Models are downloaded once from Hugging Face.

## Languages

| Language | Recognizer | Download | Term correction |
|---|---|---|---|
| Russian | [GigaAM v3](https://huggingface.co/ai-sage/GigaAM-v3) — state-of-the-art open Russian ASR | 450 MB + 225 MB | acoustic + text |
| English, Portuguese (European) + 23 European languages | [Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) (MLX) | 2.5 GB | text |
| Everything else Whisper knows | [Whisper large-v3-turbo](https://huggingface.co/mlx-community/whisper-large-v3-turbo) (MLX) | 1.6 GB | glossary as prompt + text |

There is no language to pick. Parakeet hears every chunk and detects its language; when it
writes a chunk mostly in Cyrillic, GigaAM recognizes the same audio again, Parakeet's version
serves as a second opinion, and the Russian term correction runs. English and Portuguese come
straight from Parakeet, so they cost nothing extra. Parakeet v3 was trained on European
Portuguese, so Portugal's Portuguese is a first-class citizen. To pin one language (and load
fewer models), set `language: en` in the [configuration](#configuration) or pass `--lang en`.

## Install

Requires a Mac with Apple Silicon (M1 or newer) and macOS 14+.

```bash
brew install r-ms/tools/diga
diga models --download default   # once: diga's Python packages and the models (~3.5 GB)
brew services start diga         # start now and at every login
```

Or without Homebrew, one command that also installs [uv](https://docs.astral.sh/uv/) if needed,
downloads the models and starts diga at login:

```bash
curl -LsSf https://raw.githubusercontent.com/r-ms/diga/main/install.sh | sh
```

Then hold the right ⌘ and speak; `diga doctor` checks permissions, recognizers and models.
With every model loaded diga uses about 4 GB of memory (3.7 GB without the language model).

<details><summary>Step by step with uv</summary>

```bash
uv tool install "diga[ru,parakeet] @ git+https://github.com/r-ms/diga"   # extras: ru, parakeet, whisper, all
diga models --download default   # the models your settings use
diga                             # a microphone icon appears in the menu bar
diga autostart install           # optional: start at login
```

</details>

macOS asks for three permissions for the app that runs diga (your terminal, or Python when it
runs at login): **Microphone**, **Accessibility** and **Input Monitoring** — the last two to see
the ⌘ key and to type. `diga doctor` tells you exactly where to switch them on.

## Use

| Action | What happens |
|---|---|
| Hold right ⌘, speak, release | Text is typed, then Return |
| Hold right ⌘ and press another key | Treated as a shortcut — nothing is typed |
| Double-tap right ⌘ | Start a long dictation; double-tap again to stop (no Return) |
| Menu → Key | Right ⌘ (default), right ⌥ or Fn (🌐) |
| Menu → Sound | Soft, Tick, Drop, Chime or Off — you hear each one as you pick it |
| Menu → Open glossary | Edit your terms; changes apply to the next dictation |

Left ⌘ is not offered on purpose: ⌘-click and ⌘-drag press no other key, so they would start
recordings. With Fn (🌐), set System Settings → Keyboard → "Press 🌐 key to" → *Do Nothing*, or
macOS opens emoji or its own dictation when you release it.

`diga --no-ui` runs without the menu bar (Enter starts and stops); `--print-only` prints instead
of typing — handy for trying it out. `diga -v` explains every chunk: what each recognizer heard,
how disagreements were settled and which terms were replaced.

### Glossary

`~/.config/diga/glossary.yaml` starts from [an example](src/diga/data/glossary.example.yaml)
with common developer terms. Add a term and the ways the recognizer actually writes it:

```yaml
terms:
  - term: Kubernetes
    pron_variants:
      ru: [кубернетес, кубернетис]
      en: [cube ernetes]
```

### Configuration

The defaults are meant to be the best choice, so the menu only lets you pick a sound. To
change anything else,
create `~/.config/diga/config.yaml`:

```yaml
language: en                    # pin one language instead of auto: ru | en | pt | Whisper code
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
right ⌘ ──► recorder ──► chunks at pauses ──► recognizer ──► term correction ──► typed into the
 (hold)     mic open      (energy, no VAD)    GigaAM /        acoustic (ru)       focused app
            only now                          Parakeet /      + text match        (+ Return)
                                              Whisper
```

The [architecture notes](docs/architecture.md) explain each step and the design decisions;
[adding a language](docs/adding-a-language.md) shows how to plug in another recognizer.

## Troubleshooting

- **The icon turns red but nothing is typed.** macOS is not letting the app that runs diga type
  into other apps: check *System Settings → Privacy & Security → Accessibility* for it (diga shows
  a warning in the menu) and restart diga. `diga doctor` checks this.
- **Holding ⌘ does nothing.** Accessibility / Input Monitoring is missing — run `diga doctor`.
- **First dictation is slow.** The models are downloading; `diga models --download all` fetches
  them ahead of time.

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
diga is small (under 3k lines of Python), focused on the terminal and on getting technical
vocabulary right, and easy to read and change.

## Development

```bash
git clone https://github.com/r-ms/diga && cd diga
uv sync --all-extras --group dev
uv run pytest                 # unit tests, no models needed
uv run pytest -m models       # end-to-end with real models and macOS voices
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run python benchmarks/latency.py
uv run python benchmarks/terms.py synthetic
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

diga stands on [GigaAM](https://github.com/salute-developers/GigaAM) (Salute Developers, MIT),
[NVIDIA Parakeet](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) (CC-BY-4.0) via
[parakeet-mlx](https://github.com/senstella/parakeet-mlx), [Whisper](https://github.com/openai/whisper)
via [mlx-whisper](https://github.com/ml-explore/mlx-examples), and the CTC word-spotting idea
from NeMo (Andrusenko et al., 2024). Models are not bundled; see [NOTICE](NOTICE).

MIT © Mikhail Rakutko
