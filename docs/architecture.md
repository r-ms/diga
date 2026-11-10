# Architecture

```
hotkeys.py ──hold/toggle──► recorder.py ──chunks──► asr/* ──Transcript──► terms/* ──text──► inject.py
 CGEventTap                   mic + chunking         GigaAM / Parakeet /    acoustic + text      typed key
 (right ⌘)                    worker thread          Whisper                correction           events (+ Return)
                                   ▲
ui.py (menu bar) ─── app.py wires everything, config.py / i18n.py / permissions.py support it
```

| Module | Responsibility |
|---|---|
| `hotkeys.py` | Turns right-⌘ events into *hold start / hold end (cancel?)* and *double-tap*. Pure logic, unit-tested with a fake timer. |
| `recorder.py` | Opens the mic for one recording, cuts it into chunks, recognizes each chunk on a background thread and types it immediately; presses Return after hold-to-talk. |
| `chunking.py` | Where to cut: first pause after `min_chunk_s`, or the quietest frame before `max_chunk_s`. Energy only — no VAD model. |
| `asr/` | `Transcriber` protocol (`transcribe(audio) → Transcript(text, words)`) and three implementations. |
| `asr/auto.py` | The default language `auto`: Parakeet detects each chunk's language, GigaAM re-recognizes Russian chunks. |
| `asr/second_opinion.py` | For Russian: aligns GigaAM's and Parakeet's words and settles disagreements. |
| `asr/plausibility.py` | Small language model (Qwen3 0.6B, MLX) that scores how plausible a sentence is. |
| `terms/` | Glossary, the CTC word spotter, acoustic and text correctors (picked per chunk language in `auto`), and how they choose and apply replacements. |
| `inject.py` | Types Unicode key events with modifier flags cleared; presses Return. |
| `ui.py` | Menu-bar icon, a hint, the sound menu, warning when typing is not allowed. |
| `logfile.py` | The log file `~/Library/Logs/diga/diga.log`, with dictated text replaced by ⋯. |
| `sounds.py` | Sound sets (built in or your own folder) for start of recording and success. |
| `app.py` | Builds the recognizer + corrector for a language, wires recorder, hotkeys and menu, handles Ctrl-C. |
| `config.py` | Dataclass defaults ← `config.yaml` ← menu `settings.json` (the sound) ← CLI. |
| `macos/` | `diga.app`: a tiny launcher so macOS asks for permissions in diga's name (the Homebrew service runs it). |
| `models.py` | Model registry: Hugging Face repo, pinned revision, license, size. |
| `system.py` | The languages this Mac shows (preferred languages, keyboard layouts), used when `languages` is not set. |
| `permissions.py` | Microphone / Accessibility / Input Monitoring checks for `diga doctor`. |

## Design decisions

**The microphone is open only while you dictate.** An always-listening design (VAD + wake word)
would run the recognizer over everything said near the Mac. Push-to-talk keeps the recognizer
idle and the macOS microphone indicator off between dictations.

**Chunks at pauses, typed as they come.** Full-context models such as GigaAM and Parakeet cannot
stream word by word, and none of them accept more than ~25 s. diga cuts the recording at the
first pause after 10 s (or the quietest moment before 20 s) and types each chunk as soon as it is
recognized, so a long dictation shows up progressively and only the last chunk is left after you
stop. The cut uses frame energy relative to the chunk's own quietest frame, so it needs no model.

**Typing instead of pasting.** Pasting through the clipboard overwrites what you copied and
misbehaves in some terminals. Unicode key events avoid both. Modifier flags are cleared on every
event: with progressive typing you may still be holding ⌘ when a chunk arrives, and `w` + ⌘ would
close a tab.

**Hold vs. shortcut.** Recording starts only after ⌘ has been held for 0.3 s; any other key
pressed while ⌘ is down marks it as a shortcut and the recording is discarded. Return is pressed
only after a hold-to-talk recording that actually typed something.

**Acoustic term spotting, then text matching.** Recognizers write unfamiliar terms the way they
sound, sometimes beyond recognition (*пужгид* for "push git"). diga runs a second, CTC model over
the same audio and searches its frame-level probabilities for every spelling of every glossary
term (an exact dynamic programme over a token trie, after NeMo's CTC word spotter). Where a term
is found, the nearby recognized words most similar to it are replaced, unless they already are
the term, an inflected form of it, or just stop-words. Text matching then fixes clean phonetic
spellings the spotter misses (*пайтоне* → Python). See [benchmarks](benchmarks.md).

**Nothing to choose.** Every setting has the default we measured to be best, and the menu holds
no switches. The language is decided per chunk: Parakeet (25 European languages) detects it, and
a chunk it writes mostly in Cyrillic is recognized again by GigaAM, the stronger Russian model,
with Parakeet's words as the second opinion. Since people mostly keep to one language, after a
Russian chunk GigaAM starts on the next one in parallel with Parakeet, so Russian is as fast as
choosing Russian explicitly (0.30 s per chunk) and English or Portuguese costs nothing extra.

**A second opinion where the first is unsure.** GigaAM's decoder exposes how sure it is of every
token (1 − normalised entropy of the output distribution), and its low-confidence words are
largely its errors. Parakeet transcribes the same chunk,
the two word sequences are aligned (as in ROVER), and in each disagreement GigaAM's words are kept
unless GigaAM is unsure there and Parakeet is more confident; words GigaAM dropped are inserted
when Parakeet is confident. A small language model reads both wordings of every disagreement
in context and decides where it clearly prefers one — this catches words GigaAM was sure of
that do not exist (*maby Just Смоу*) and keeps GigaAM's correct words when Parakeet is wrong.
Unlike glossary correction this needs no list of terms.

**Fail open.** A term-correction error never loses dictation — the raw text is typed instead.
A broken glossary edit keeps the previous glossary.

**Pinned models.** Repositories whose code runs at load time (GigaAM uses `trust_remote_code`)
are pinned to a reviewed commit in `models.py`.
