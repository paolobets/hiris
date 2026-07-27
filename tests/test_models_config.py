import os
from hiris.app.api.handlers_models import load_models_config, save_models_config


def test_defaults_when_absent(tmp_path):
    cfg = load_models_config(str(tmp_path))
    assert cfg == {"chain_order": [], "brain_model": "auto"}


def test_roundtrip_and_sanitizes_unknown_backends(tmp_path):
    saved = save_models_config(str(tmp_path), {
        "chain_order": ["ollama", "bogus", "claude"],
        "brain_model": "claude-opus-4-7",
    })
    assert saved["chain_order"] == ["ollama", "claude"]   # 'bogus' rimosso
    assert saved["brain_model"] == "claude-opus-4-7"
    assert os.path.exists(os.path.join(str(tmp_path), "models_config.json"))
    assert load_models_config(str(tmp_path)) == saved


def test_non_string_brain_model_falls_back_to_auto(tmp_path):
    saved = save_models_config(str(tmp_path), {"brain_model": 123})
    assert saved["brain_model"] == "auto"
