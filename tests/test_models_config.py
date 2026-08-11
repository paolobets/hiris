import os
from hiris.app.api.handlers_models import load_models_config, save_models_config


def test_defaults_when_absent(tmp_path):
    cfg = load_models_config(str(tmp_path))
    assert cfg == {
        "chain_order": [],
        "provider_models": {"claude": "", "openai": "", "openrouter": ""},
    }


def test_roundtrip_and_sanitizes_unknown_backends(tmp_path):
    saved = save_models_config(str(tmp_path), {
        "chain_order": ["ollama", "bogus", "claude"],
    })
    assert saved["chain_order"] == ["ollama", "claude"]   # 'bogus' rimosso
    assert os.path.exists(os.path.join(str(tmp_path), "models_config.json"))
    assert load_models_config(str(tmp_path)) == saved


# fetta E5 Task 7 ("Consumi e Modelli smettono di mentire"): brain_model esce
# per intero -- il Brain che lo leggeva e' uscito con la E3, zero lettori di
# produzione da allora. Non e' un'opzione dell'add-on (vive solo in
# models_config.json): un file scritto da una versione precedente con la
# chiave popolata non viene ne' migrato ne' cancellato (mai dati utente
# rimossi silenziosamente), ma il silenzio si dichiara -- stessa disciplina
# di tests/test_startup_legacy_db_silence.py e dello stesso identico
# precedente in claude_runner._load_usage per 'per_agent' di usage.json
# (tests/test_claude_runner.py:721-780), copiato qui nella stessa forma
# incluso il caso "sopravvive a un salvataggio".


def test_brain_model_legacy_logged_when_present(tmp_path, caplog):
    import json as _json
    cfg_file = tmp_path / "models_config.json"
    cfg_file.write_text(_json.dumps({
        "chain_order": [], "brain_model": "claude-opus-4-7", "provider_models": {},
    }), encoding="utf-8")
    with caplog.at_level("INFO"):
        load_models_config(str(tmp_path))
    assert any(
        "brain_model" in rec.message and "installazione precedente" in rec.message
        for rec in caplog.records
    )


def test_brain_model_silent_when_absent(tmp_path, caplog):
    with caplog.at_level("INFO"):
        load_models_config(str(tmp_path))
    assert not any("brain_model" in rec.message for rec in caplog.records)


def test_brain_model_legacy_survives_a_save(tmp_path):
    """fix round 1 di claude_runner._save_usage per 'per_agent' (stesso
    identico bug qui): save_models_config ricostruiva models_config.json da
    zero scrivendo SOLO le chiavi che questa versione conosce -- il PRIMO
    salvataggio dopo un upgrade avrebbe cancellato silenziosamente
    'brain_model' di un'installazione precedente, il contrario di quanto
    dichiara il log dei due test gemelli sopra ("non piu' letto ne' scritto",
    che un operatore legge come "e' ancora li'"). save_models_config fa
    lettura-modifica-scrittura: la chiave sopravvive a un salvataggio reale,
    non solo al load."""
    import json as _json
    cfg_file = tmp_path / "models_config.json"
    cfg_file.write_text(_json.dumps({
        "chain_order": [], "brain_model": "claude-opus-4-7", "provider_models": {},
    }), encoding="utf-8")
    save_models_config(str(tmp_path), {"chain_order": ["claude"]})
    with open(cfg_file, encoding="utf-8") as f:
        data = _json.load(f)
    assert data.get("brain_model") == "claude-opus-4-7"
    assert data["chain_order"] == ["claude"]


def test_provider_models_defaults_empty(tmp_path):
    from hiris.app.api.handlers_models import load_models_config
    cfg = load_models_config(str(tmp_path))
    assert cfg["provider_models"] == {"claude": "", "openai": "", "openrouter": ""}


def test_provider_models_roundtrip_and_sanitizes(tmp_path):
    from hiris.app.api.handlers_models import save_models_config, load_models_config
    saved = save_models_config(str(tmp_path), {"provider_models": {
        "claude": "claude-opus-4-7", "openai": 123, "bogus": "x"}})
    assert saved["provider_models"]["claude"] == "claude-opus-4-7"
    assert saved["provider_models"]["openai"] == ""   # non-string -> ""
    assert "bogus" not in saved["provider_models"]     # unknown key dropped
    assert load_models_config(str(tmp_path))["provider_models"] == saved["provider_models"]
