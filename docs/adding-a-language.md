# Adding a language or a recognizer

## A language an existing recognizer already speaks

Parakeet covers 25 European languages, and with the default `language: auto` it already detects
them — German, French or Polish dictation works out of the box. To pin a language, or to send it
to Whisper (~100 languages), configure it:

```yaml
# ~/.config/diga/config.yaml
language: de
backends: {de: parakeet}   # or whisper
```

Add the language's stop-words to `STOPWORDS` in `src/diga/terms/text.py` (they stop the text
matcher from replacing filler words) and pronunciation variants for your terms in the glossary.

## A new recognizer

Implement the `Transcriber` protocol from `src/diga/asr/base.py`:

```python
class MyTranscriber:
    name = "mine"

    def warmup(self) -> None: ...  # load kernels before the first press
    def transcribe(self, audio: np.ndarray) -> Transcript:
        # audio: 1-D float32, 16 kHz mono, at most 25 s
        return Transcript(text, words)  # words: Word(text, start_s, end_s)
```

Word timings are optional for text matching but required for acoustic correction. If your model
emits sub-word tokens with timings, `words_from_tokens()` groups them into words.

Then register it in `create_transcriber()` (`src/diga/asr/__init__.py`), add an optional
dependency group in `pyproject.toml`, and a `ModelSpec` with its license in `models.py`.

## Acoustic term correction for another language

The spotter needs a CTC model for the language: anything implementing `CtcModel` from
`src/diga/terms/acoustic.py` — `encode(text) → token ids`, `log_probs(audio) → [frames, vocab+1]`,
`blank_id`, `frame_s` and `language`. The search itself is language-agnostic; language-specific
text handling (normalisation, stop-words, transliteration) lives in `terms/text.py`. Wire it in
`build_corrector()` in `app.py` the way Russian is, chained before the text matcher.
