# Contributing

Thanks for helping! Issues and pull requests are welcome.

```bash
uv sync --all-extras --group dev
uv run pytest                    # fast, no models
uv run pytest -m models          # end-to-end; downloads models, needs macOS voices
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run pre-commit install        # optional: ruff on every commit
```

- Keep the unit tests model-free: fake the recognizer, the microphone or the CTC model (see
  `tests/test_recorder.py` and `tests/test_terms.py`).
- A bug fix comes with a test that fails without it.
- Changes to term correction: run `benchmarks/terms.py` before and after and put both tables in
  the pull request.
- User-facing strings go through `i18n.t()` with English, Russian and Portuguese versions.
- Code, comments and commit messages in English; commits follow
  [Conventional Commits](https://www.conventionalcommits.org/).
