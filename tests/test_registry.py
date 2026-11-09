from diga import models


def test_every_model_has_a_license_and_a_file_to_check():
    for spec in models.REGISTRY:
        assert spec.license and spec.check_file, spec.key


def test_every_model_is_pinned_to_a_commit():
    # Reproducible results, reviewed code (GigaAM runs its own at load time), and loading from
    # the local cache without asking Hugging Face what the latest version is.
    for spec in models.REGISTRY:
        assert spec.revision and len(spec.revision) == 40, spec.key


def test_is_cached_looks_for_the_weights_file(monkeypatch):
    seen = []

    def fake(repo, filename, revision=None):
        seen.append((repo, filename, revision))
        return None

    monkeypatch.setattr("huggingface_hub.try_to_load_from_cache", fake)
    assert models.is_cached(models.PARAKEET_V3) is False
    assert seen == [
        ("mlx-community/parakeet-tdt-0.6b-v3", "model.safetensors", models.PARAKEET_V3.revision)
    ]


def test_default_settings_need_both_russian_models_and_the_judge():
    from diga.config import Config

    keys = {spec.key for spec in models.needed(Config())}
    assert keys == {
        "gigaam-v3-e2e-rnnt",
        "gigaam-v3-e2e-ctc-int8",
        "gigaam-v3-e2e-ctc-tokenizer",
        "parakeet-tdt-0.6b-v3",
        "qwen3-0.6b-4bit",
    }
    english_only = {spec.key for spec in models.needed(Config(language="en"))}
    assert english_only == {"parakeet-tdt-0.6b-v3"}
