import numpy as np

from diga.chunking import FRAME, find_pause, quiet_cut

SR = 16_000


def test_find_pause_on_trailing_silence():
    rms = [0.3] * 300 + [0.002] * 8
    assert find_pause(rms, pause_frames=8) == len(rms) - 4  # middle of the pause


def test_find_pause_ignores_speech_tail():
    rms = [0.3] * 300 + [0.002] * 8 + [0.3] * 3  # there was a pause, but we are speaking now
    assert find_pause(rms, pause_frames=8) is None


def test_find_pause_needs_contrast():
    assert find_pause([0.1] * 400, pause_frames=8) is None  # steady noise: don't guess


def test_find_pause_with_rare_pauses():
    # pauses well under 10% of the chunk must still be found (regression)
    rms = [0.3] * 600 + [0.002] * 8
    assert find_pause(rms, pause_frames=8) is not None


def test_quiet_cut_inside_window_only():
    wave = np.ones(20 * SR, dtype=np.float32)
    quiet = int(17.3 * SR)
    wave[quiet : quiet + 2 * FRAME] = 0.0
    wave[5 * SR : 6 * SR] = 0.0  # quiet, but before the minimum: not chosen
    cut = quiet_cut(wave, 10 * SR, 20 * SR)
    assert abs(cut - quiet) <= 2 * FRAME
