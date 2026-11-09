from __future__ import annotations

import pytest

from diga import i18n


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Every test gets its own config directory and English messages."""
    monkeypatch.setenv("DIGA_CONFIG_DIR", str(tmp_path / "config"))
    i18n.set_language("en")
    return tmp_path / "config"
