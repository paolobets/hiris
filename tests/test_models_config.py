import os

from hiris.app.api.handlers_models import load_models_config, save_models_config


def test_defaults_when_absent(tmp_path):
    """Task 6: le chiavi sono NOVE, e questo test le pinna per INSIEME ESATTO,
    non per presenza. Cinque sono arrivate con la versione A della migrazione
    (le decisioni che escono dalle opzioni dell'add-on): se una si perdesse per
    strada, l'archivio smetterebbe di essere la fonte di verita' in silenzio.
    Tre -- `seminato`, `catena_seminata` e `piano_seminato` -- non sono
    decisioni ma SEGNI di migrazione: stanno nell'archivio, si leggono sempre,
    e li scrive solo l'avvio (`_MIGRATION_FLAGS`).

    `ponte.modello` e' arrivato con la fetta «il modello del piano»: il modello
    del Piano Claude Max, che fino alla 3.1.0 era un effetto collaterale di
    `provider_models["claude"]` e non aveva una casa sua."""
    cfg = load_models_config(str(tmp_path))
    assert cfg == {
        "chain_order": [],
        "provider_models": {"claude": "", "openai": "", "openrouter": ""},
        "ponte": {"attivo": False, "scadenza_min": 5, "tetto_giornaliero": 50,
                  "modello": "sonnet"},
        "ollama": {"modello": "", "timeout_s": 120},
        "nascondi_gratuiti": False,
        # Debito F del Task 6, chiuso al Task 7: il predefinito del campo e'
        # quello dell'opzione da cui viene (`llm_strategy: "balanced"`).
        # Valeva "", e la differenza faceva contare come «copiato» un valore
        # che nessuno aveva scelto -- ogni installazione, anche nuova.
        "strategia_ultima": "balanced",
        "seminato": False,
        "catena_seminata": False,
        "piano_seminato": False,
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
    from hiris.app.api.handlers_models import load_models_config, save_models_config
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
    assert cfg["ponte"] == {"attivo": False, "scadenza_min": 5,
                            "tetto_giornaliero": 50, "modello": "sonnet"}
    assert cfg["ollama"] == {"modello": "", "timeout_s": 120}
    assert cfg["nascondi_gratuiti"] is False
    assert cfg["strategia_ultima"] == "balanced"
    assert cfg["seminato"] is False
    assert cfg["piano_seminato"] is False


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
        "ponte": {"attivo": True, "scadenza_min": 20, "tetto_giornaliero": 200,
                  "modello": "opus"},
    })
    save_models_config(str(tmp_path), {"chain_order": ["openrouter"]})
    cfg = load_models_config(str(tmp_path))
    assert cfg["chain_order"] == ["openrouter"]
    assert cfg["ponte"] == {"attivo": True, "scadenza_min": 20,
                            "tetto_giornaliero": 200, "modello": "opus"}


def test_il_piano_non_puo_essere_salvato_dentro_chain_order(tmp_path):
    """`chain_order` porta i QUATTRO backend del router. Il piano non e' un suo
    membro: sta in testa alla catena quando il ponte e' acceso, e lo dice
    `ponte.attivo`. Se `subscription` potesse entrare qui, esisterebbero due
    modi di metterlo in catena -- cioe' due rappresentazioni della stessa cosa,
    che e' esattamente il difetto che questa fetta chiude."""
    saved = save_models_config(str(tmp_path), {
        "chain_order": ["subscription", "claude"],
    })
    assert saved["chain_order"] == ["claude"]
    assert load_models_config(str(tmp_path))["chain_order"] == ["claude"]


def test_una_put_non_puo_riscrivere_i_segni_della_migrazione(tmp_path):
    """**C1 della revisione finale, meta' backend.**

    `seminato`, `catena_seminata` e `piano_seminato` non sono decisioni: sono i
    segni che le tre migrazioni sono avvenute. Stavano in `_OUR_KEYS`, cioe'
    una PUT poteva riscriverli -- e la pagina lo faceva davvero: dopo un GET
    fallito i tre bottoni «Rifai la catena» restavano a schermo e mandavano lo
    `state.cfg` DI DEFAULT DEL MODULO, `seminato: false` compreso.

    La conseguenza non e' un campo sbagliato in un file: al riavvio successivo
    la semina RIGIRA. Sulla 2.5.0 ricopia le opzioni dell'add-on sopra le
    decisioni prese dalla pagina; dopo la versione B, con l'ambiente muto,
    ricopia i PREDEFINITI -- cioe' la perdita silenziosa che l'esistenza di due
    versioni della migrazione serve a evitare, innescata da un click. Lo stesso
    vale per un gateway MCP che rimandasse uno snapshot stale.

    Il terzo segno e' arrivato con la fetta «il modello del piano», e la sua
    conseguenza e' la piu' visibile delle tre: la semina RICOPRE
    `ponte.modello` col valore derivato da Claude API, cioe' cancella la scelta
    che l'utente ha appena fatto sulla riga del piano.

    Rimettere i tre nomi in `_OUR_KEYS` fa cadere questo test."""
    save_models_config(str(tmp_path), {"chain_order": ["claude"]}, flags=True)
    save_models_config(
        str(tmp_path),
        {"seminato": True, "catena_seminata": True, "piano_seminato": True,
         "chain_order": ["claude"]},
        flags=True,
    )
    assert load_models_config(str(tmp_path))["seminato"] is True

    # La PUT: l'oggetto intero come lo manda la pagina, con i due segni a
    # `false` come li porta lo `state.cfg` di default.
    save_models_config(str(tmp_path), {
        "chain_order": [],
        "provider_models": {"claude": "", "openai": "", "openrouter": ""},
        "ponte": {"attivo": False, "scadenza_min": 5, "tetto_giornaliero": 50,
                  "modello": "sonnet"},
        "ollama": {"modello": "", "timeout_s": 120},
        "nascondi_gratuiti": False,
        "strategia_ultima": "balanced",
        "seminato": False,
        "catena_seminata": False,
        "piano_seminato": False,
    })
    cfg = load_models_config(str(tmp_path))
    assert cfg["seminato"] is True, (
        "una PUT ha riportato `seminato` a false: al riavvio la semina delle "
        "opzioni rigira e sovrascrive le decisioni della pagina"
    )
    assert cfg["catena_seminata"] is True, (
        "una PUT ha riportato `catena_seminata` a false: al riavvio la catena "
        "si ripopola dalla regola `legacy`"
    )
    assert cfg["piano_seminato"] is True, (
        "una PUT ha riportato `piano_seminato` a false: al riavvio la semina "
        "del modello del piano rigira e ricopre la scelta dell'utente col "
        "valore derivato da Claude API"
    )
    # E le sei decisioni, quelle si', sono passate: il filtro toglie i segni,
    # non la scrittura.
    assert cfg["chain_order"] == []


# ---------------------------------------------------------------------------
# C2 della revisione del commit 3.0.0: **la quinta porta della regola
# «legacy»**, ed e' questa versione a renderla irreversibile.
#
# `load_models_config` inghiottiva OGNI eccezione di lettura in `raw = {}`
# senza una riga di log. Con un file troncato -- una scrittura interrotta su
# una scheda SD -- l'avvio ripartiva dai predefiniti, ricomponeva la catena con
# la regola di compatibilita', e `save_models_config` (che parte dal disco)
# sovrascriveva il file. Dodici decisioni dell'utente sparivano, e le due sole
# righe che parlavano affermavano ENTRAMBE il falso: «erano tutti ai
# predefiniti» e «la catena che HIRIS stava usando e' stata copiata».
#
# Fino alla 2.5.0 era in buona parte recuperabile: l'ambiente era popolato e la
# semina ricopiava i valori dalle opzioni. Da questa versione le quattordici
# opzioni sono uscite dallo schema e l'archivio e' l'UNICA copia esistente.
# ---------------------------------------------------------------------------

_ARCHIVIO_DELL_UTENTE = (
    '{"chain_order": ["ollama"], "ponte": {"attivo": true, "scadenza_min": 30,'
    ' "tetto_giornaliero": 500}, "ollama": {"modello": "gemma3:27b", "timeo'
)   # troncato a meta', come lo lascia una scrittura interrotta


def test_un_archivio_illeggibile_lo_dice_invece_di_azzerarsi_in_silenzio(tmp_path, caplog):
    (tmp_path / "models_config.json").write_text(_ARCHIVIO_DELL_UTENTE,
                                                 encoding="utf-8")
    with caplog.at_level("ERROR"):
        cfg = load_models_config(str(tmp_path))

    assert cfg["chain_order"] == []          # i predefiniti, come prima
    errori = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert any("non si e' potuto leggere" in m for m in errori), (
        "dodici decisioni dell'utente sono sparite e nessuna riga dice che il "
        "file non si e' potuto leggere: le uniche due che parlano sono quelle "
        "della semina, e affermano il contrario"
    )


def test_un_archivio_illeggibile_si_mette_da_parte_invece_di_essere_sovrascritto(tmp_path):
    """Un byte di disco contro dodici decisioni. Senza il rinomino, il primo
    salvataggio -- che dall'avvio arriva da solo, con la semina -- porta via i
    byte per sempre, e da questa versione non c'e' piu' niente da cui
    rileggerli."""
    (tmp_path / "models_config.json").write_text(_ARCHIVIO_DELL_UTENTE,
                                                 encoding="utf-8")
    load_models_config(str(tmp_path))

    guasto = tmp_path / "models_config.json.corrotto"
    assert guasto.exists(), (
        "il file illeggibile e' rimasto al suo posto, e il prossimo "
        "salvataggio ci scrive sopra"
    )
    assert guasto.read_text(encoding="utf-8") == _ARCHIVIO_DELL_UTENTE
    assert not (tmp_path / "models_config.json").exists()

    # E il salvataggio che segue non tocca la copia messa da parte.
    save_models_config(str(tmp_path), {"chain_order": ["claude"]})
    assert guasto.read_text(encoding="utf-8") == _ARCHIVIO_DELL_UTENTE


def test_il_corrotto_piu_vecchio_non_si_sovrascrive(tmp_path):
    """Il secondo guasto ci scriverebbe sopra l'archivio dei predefiniti gia'
    riscritto, cioe' niente: la copia che vale e' la PRIMA."""
    (tmp_path / "models_config.json.corrotto").write_text(
        _ARCHIVIO_DELL_UTENTE, encoding="utf-8")
    (tmp_path / "models_config.json").write_text("{rotto di nuovo",
                                                 encoding="utf-8")
    load_models_config(str(tmp_path))
    assert (tmp_path / "models_config.json.corrotto").read_text(
        encoding="utf-8") == _ARCHIVIO_DELL_UTENTE


def test_un_archivio_assente_resta_silenzioso(tmp_path, caplog):
    """Il gemello obbligatorio: al primo avvio il file non c'e', ed e' normale.
    Un errore che compare sempre e' rumore, e il rumore e' cio' che ha fatto
    scorrere via un avvio dal registro consegnato col cancello di questa
    fetta."""
    with caplog.at_level("ERROR"):
        load_models_config(str(tmp_path))
    assert [r for r in caplog.records if r.levelname == "ERROR"] == []
    assert not (tmp_path / "models_config.json.corrotto").exists()


def test_un_archivio_che_non_e_un_oggetto_conta_come_illeggibile(tmp_path, caplog):
    """JSON valido, ma non un dizionario: si azzerava nello stesso silenzio,
    una riga piu' sotto."""
    (tmp_path / "models_config.json").write_text('["claude"]', encoding="utf-8")
    with caplog.at_level("ERROR"):
        load_models_config(str(tmp_path))
    assert any("invece di un oggetto JSON" in r.getMessage()
               for r in caplog.records if r.levelname == "ERROR")
    assert (tmp_path / "models_config.json.corrotto").exists()
