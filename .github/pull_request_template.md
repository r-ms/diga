## What and why

<!-- One or two sentences. Link the issue if there is one. -->

## How it was checked

- [ ] `uv run pytest` (a bug fix comes with a test that fails without it)
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run pyright`
- [ ] Term correction or recognition changed: `benchmarks/terms.py` tables before and after
- [ ] User-facing text: English, Russian and Portuguese in `i18n.py`
