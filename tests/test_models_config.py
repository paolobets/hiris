import os
from hiris.app.api.handlers_models import load_models_config, save_models_config


def test_defaults_when_absent(tmp_path):
    """Task 6: le chiavi sono SETTE, e questo test le pinna per INSIEME ESATTO,
    non per presenza. Cinque sono arrivate con la versione A della migrazione
    (le decisioni che escono dalle opzioni dell'add-on): se una si perdesse per
    strada, l'archivio smetterebbe di essere la fonte di verita' in silenzio."""
    cfg = load_models_config(str(tmp_path))
    assert cfg == {
        "chain_order": [],
        "provider_models": {"claude": "", "openai": "", "openrouter": ""},
        "ponte": {"attivo": False, "scadenza_min": 5, "tetto_giornaliero": 50},
        "ollama": {"modello": "", "timeout_s": 120},
        "nascondi_gratuiti": False,
        "strategia_ultima": "",
        "seminato": False,
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


# ---------------------------------------------------------------------------
# fetta «la catena diventa l'unica verita'», Task 6 (versione A della
# migrazione): le decisioni che oggi stanno nelle opzioni dell'add-on vengono a
# vivere qui. Il lettore e lo scrittore le conoscono; i lettori di
# comportamento no -- quelli si spostano ai Task 7 e 10.
# ---------------------------------------------------------------------------


def test_le_nuove_chiavi_hanno_i_predefiniti_quando_il_file_non_esiste(tmp_path):
    cfg = load_models_config(str(tmp_path))
    assert cfg["ponte"] == {"attivo": False, "scadenza_min": 5, "tetto_giornaliero": 50}
    assert cfg["ollama"] == {"modello": "", "timeout_s": 120}
    assert cfg["nascondi_gratuiti"] is False
    assert cfg["strategia_ultima"] == ""
    assert cfg["seminato"] is False


def test_i_valori_fuori_range_rientrano_invece_di_sollevare(tmp_path):
    """Lo `schema:` di config.yaml li faceva rispettare (`int(1,120)`,
    `int(0,1000)`, `int(10,1800)`). Da quando il valore arriva da una PUT
    dobbiamo farlo noi -- e riportarlo dentro, come faceva il modulo, non
    rifiutare il salvataggio intero."""
    save_models_config(str(tmp_path), {
        "ponte": {"attivo": True, "scadenza_min": 999, "tetto_giornaliero": -5},
        "ollama": {"modello": "llama3", "timeout_s": 1},
    })
    cfg = load_models_config(str(tmp_path))
    assert cfg["ponte"]["scadenza_min"] == 120
    assert cfg["ponte"]["tetto_giornaliero"] == 0
    assert cfg["ollama"]["timeout_s"] == 10
    assert cfg["ollama"]["modello"] == "llama3"


def test_un_salvataggio_non_cancella_le_chiavi_che_questa_versione_non_conosce(tmp_path):
    """La lettura-modifica-scrittura che c'era gia', riverificata ora che le
    chiavi scritte sono sette invece di due."""
    import json
    (tmp_path / "models_config.json").write_text(
        json.dumps({"brain_model": "vecchio", "chain_order": ["claude"]}), encoding="utf-8")
    save_models_config(str(tmp_path), {"chain_order": ["openrouter"]})
    disco = json.loads((tmp_path / "models_config.json").read_text(encoding="utf-8"))
    assert disco["brain_model"] == "vecchio"
    assert disco["chain_order"] == ["openrouter"]


def test_un_salvataggio_parziale_non_azzera_le_decisioni_gia_prese(tmp_path):
    """Il contratto della PUT e' «sempre l'oggetto intero» (models-route.js), e
    il frontend lo rispetta. Ma un salvataggio parziale non deve poter azzerare
    il ponte: sarebbe una perdita di configurazione silenziosa, e un client
    diverso dalla pagina esiste (il gateway MCP)."""
    save_models_config(str(tmp_path), {
        "chain_order": ["claude"],
        "ponte": {"attivo": True, "scadenza_min": 20, "tetto_giornaliero": 200},
    })
    save_models_config(str(tmp_path), {"chain_order": ["openrouter"]})
    cfg = load_models_config(str(tmp_path))
    assert cfg["chain_order"] == ["openrouter"]
    assert cfg["ponte"] == {"attivo": True, "scadenza_min": 20, "tetto_giornaliero": 200}
