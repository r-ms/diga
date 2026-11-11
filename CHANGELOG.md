# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.10] — 2026-11-11

### Fixed
- Input Monitoring and Accessibility stayed empty for the Homebrew service: macOS lists an app
  only when the app's own executable asks, and diga asked from its Python process. diga.app's
  launcher now asks itself, so the prompts appear and "diga" is in both panes.

## [0.1.9] — 2026-11-10

### Fixed
- A false "can't type into other apps" warning on Macs where Accessibility is granted but the
  separate "post events" entry is not; either grant is enough to type.
- Return could become a new line instead of sending the prompt: right after the text, some
  terminals hand both to the app at once, and Claude Code reads that as a paste. diga now
  waits 0.12 s before pressing Return.

## [0.1.8] — 2026-11-10

### Changed
- The permission warning in the menu says what is missing ("⚠ No keyboard access — open
  Settings…"); after you click it, it says what to switch on, and diga restarts itself as soon
  as macOS grants the permission (never in the middle of a dictation).

## [0.1.7] — 2026-11-10

### Changed
- The Homebrew service runs as a small `diga.app`, so macOS asks for the microphone, Input
  Monitoring and Accessibility in diga's name — not "Python 3.12" — and shows why it needs the
  microphone. The bundle does not change between versions, so the permissions survive upgrades.

## [0.1.6] — 2026-11-10

### Fixed
- Started by `brew services`, diga could miss the keyboard for good: macOS silently refuses
  Input Monitoring to a background Python, and diga tried to connect only once. diga now asks
  for every permission at start, retries every 2 s, connects as soon as the permission is on
  (restarting itself once if macOS requires it), and the menu shows what is missing with a click
  to the right page of System Settings.

### Added
- A log file, `~/Library/Logs/diga/diga.log` (never with dictated text): Menu → Show log,
  `diga logs [-f]`, and its path in `diga doctor`.

## [0.1.5] — 2026-11-10

### Added
- `languages`: the languages you dictate in (`languages: [ru, en]`, `--languages ru,en`). By
  default they are read off the Mac: its preferred languages and keyboard layouts. Without
  Russian among them the Russian models are neither downloaded nor loaded (1.6 GB of memory
  instead of 4 GB); Russian speech is then left to Parakeet, with a one-time hint.
- `diga doctor` shows your languages and where they came from.

## [0.1.4] — 2026-11-10

### Changed
- The common developer terms are built into diga and updated with it; your
  `~/.config/diga/glossary.yaml` starts as a short template and holds only your own terms
  (a term in both gets both sets of spellings; `use_builtin: false` keeps only yours).
  An existing glossary is kept as it is.
- Menu → Open glossary always opens the file in your text editor.

## [0.1.3] — 2026-11-10

### Changed
- Menu-bar icon: a speech bubble (red and filled while recording, with … while finishing)
  instead of a microphone, which was easy to mistake for macOS's own microphone indicator.

## [0.1.2] — 2026-11-09

### Added
- Menu → Key: dictate with right ⌘ (default), right ⌥ or Fn (🌐); remembered like the sound.

### Fixed
- `uv run diga` in a clone installs the recognizers (a recreated environment had none).
- Without Parakeet, `auto` falls back to Russian instead of failing to start.
- A failed start no longer ends with "cannot join current thread".

## [0.1.1] — 2026-11-09

### Fixed
- Memory: GPU buffer pools of MLX (Parakeet, the language model) and PyTorch (GigaAM) grew
  with every chunk length — 8.4 GB after a few dictations. They are now capped: about 4 GB
  with every model loaded (3.7 GB without the language model), at the same speed.

## [0.1.0] — 2026-11-09

First public version.

### Added
- Push-to-talk on the right ⌘: hold to dictate and press Return on release, double-tap for long
  dictation, ⌘ + another key cancels.
- Progressive typing: recordings are cut into 10–20 s chunks at pauses and each chunk is typed as
  soon as it is recognized.
- Recognizers: GigaAM v3 (Russian), Parakeet TDT 0.6B v3 (English, Portuguese and 23 more
  European languages), Whisper large-v3-turbo (other languages).
- Term correction from a glossary: acoustic CTC keyword spotting plus text matching for Russian,
  text matching elsewhere; multi-word replacements ("гит лаб" → GitLab).
- Nothing to choose: the default language `auto` detects every chunk's language with Parakeet
  and re-recognizes Russian chunks with GigaAM; the menu has no switches, and
  `~/.config/diga/config.yaml` changes the defaults.
- Second opinion for Russian (on by default): GigaAM and Parakeet both transcribe; disagreements
  are settled by a small language model (Qwen3 0.6B) reading both wordings in context, then by
  GigaAM's word confidence.
- Word-level confidence from every recognizer.
- Faster: the acoustic term model runs alongside the recognizer, and text is typed up to 20
  characters per key event (a long chunk used to take ~0.8 s to type, now ~0.05 s).
- Menu-bar app in English, Russian and Portuguese; a warning when macOS does not let diga type.
- Menu-bar icon drawn with SF Symbols (red while recording).
- Our own quiet sounds — when recording starts and once the text is typed (silent when a
  dictation is cancelled or empty); four sets plus Off in the menu, or a folder of your own.
- `diga -v` shows, for every chunk, what each recognizer heard and how long it took, how the
  second opinion settled each disagreement and which terms were replaced. Logs written to a
  file (autostart) carry timestamps and leave out the dictated text.
- One-command install (`install.sh`: uv, diga, models, start at login); `diga doctor`,
  `diga models --download default`, `diga autostart`.
- Offline after the first download: models load from the local cache, every model is pinned
  to a commit.
- Benchmarks for latency, term correction and word errors.

### Fixed (during development)
- Typing a chunk while holding ⌘ no longer cancels a long hold-to-talk dictation.
- Multi-word replacements ("гит лаб" → GitLab) are applied.
