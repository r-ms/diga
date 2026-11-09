"""Sound sets: built-in names, off, your own folder — no audio is played."""

from __future__ import annotations

from diga import sounds
from diga.config import load_config, save_setting


def test_every_built_in_set_has_both_sounds():
    for name in sounds.SETS:
        chosen = sounds.resolve(name)
        assert chosen.start and chosen.start.is_file(), name
        assert chosen.done and chosen.done.is_file(), name


def test_off_is_silent_and_unknown_falls_back_to_the_default(caplog):
    assert sounds.resolve("off") == sounds.Sounds()
    assert sounds.resolve("no-such-set") == sounds.resolve(sounds.DEFAULT)
    assert "not found" in caplog.text


def test_your_own_folder_may_have_only_one_of_the_sounds(tmp_path):
    (tmp_path / "done.wav").write_bytes(b"RIFF")
    chosen = sounds.resolve(str(tmp_path))
    assert chosen.start is None and chosen.done == tmp_path / "done.wav"


def test_the_sound_picked_in_the_menu_is_remembered(isolated_config):
    assert load_config().sounds == sounds.DEFAULT
    save_setting("sounds", "tick")
    assert load_config().sounds == "tick"


def test_the_key_picked_in_the_menu_is_remembered(isolated_config):
    assert load_config().hotkey.key == "right_cmd"
    save_setting("hotkey", {"key": "fn"})
    cfg = load_config()
    assert cfg.hotkey.key == "fn" and cfg.hotkey.hold_s == 0.3  # other hotkey settings kept
