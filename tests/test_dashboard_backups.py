from hiris.app.proxy.dashboard_backups import (
    save_backup, latest_backup, list_backups, MAX_BACKUPS_PER_DASHBOARD,
)


def test_latest_backup_is_none_when_nothing_saved(tmp_path):
    assert latest_backup(str(tmp_path), "casa-mia") is None


def test_save_then_latest_roundtrip(tmp_path):
    cfg = {"views": [{"title": "Home"}]}
    save_backup(str(tmp_path), "casa-mia", cfg)
    assert latest_backup(str(tmp_path), "casa-mia") == cfg


def test_latest_returns_most_recent(tmp_path):
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "A"}]})
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "B"}]})
    assert latest_backup(str(tmp_path), "casa-mia") == {"views": [{"title": "B"}]}


def test_keeps_at_most_three_per_dashboard(tmp_path):
    import json, os
    for i in range(5):
        save_backup(str(tmp_path), "casa-mia", {"views": [{"title": str(i)}]})
    with open(os.path.join(str(tmp_path), "dashboard_backups.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    assert len(data["casa-mia"]) == MAX_BACKUPS_PER_DASHBOARD
    # i piu' vecchi vengono scartati: resta la coda 2,3,4
    assert [b["config"]["views"][0]["title"] for b in data["casa-mia"]] == ["2", "3", "4"]


def test_dashboards_are_isolated(tmp_path):
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "A"}]})
    save_backup(str(tmp_path), "altra-casa", {"views": [{"title": "B"}]})
    assert latest_backup(str(tmp_path), "casa-mia") == {"views": [{"title": "A"}]}
    assert latest_backup(str(tmp_path), "altra-casa") == {"views": [{"title": "B"}]}


def test_corrupt_file_does_not_raise(tmp_path):
    """Su file corrotto non si solleva mai, ma si va fail-closed: il salvataggio
    viene rifiutato (False) invece di riscrivere il file cancellando in silenzio
    gli snapshot di tutte le altre plance."""
    import os
    path = os.path.join(str(tmp_path), "dashboard_backups.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not json")
    assert latest_backup(str(tmp_path), "casa-mia") is None
    assert save_backup(str(tmp_path), "casa-mia", {"views": []}) is False  # non deve sollevare
    assert latest_backup(str(tmp_path), "casa-mia") is None
    # il file corrotto NON e' stato riscritto: gli snapshot altrui restano recuperabili a mano
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == "{not json"


def test_corrupt_file_does_not_wipe_other_dashboards(tmp_path):
    """Il file e' condiviso: se diventa illeggibile, un salvataggio per una
    plancia non deve azzerare i backup delle altre."""
    import os
    save_backup(str(tmp_path), "altra-casa", {"views": [{"title": "TENERE"}]})
    path = os.path.join(str(tmp_path), "dashboard_backups.json")
    with open(path, encoding="utf-8") as fh:
        prima = fh.read()
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("spazzatura")
    assert save_backup(str(tmp_path), "casa-mia", {"views": []}) is False
    with open(path, encoding="utf-8") as fh:
        assert fh.read().startswith(prima)


def test_save_backup_returns_true_on_success(tmp_path):
    """Il contratto -> bool e' cio' che l'apply usa per decidere se procedere:
    va verificato sul modulo reale, non su un monkeypatch."""
    assert save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "A"}]}) is True


def test_save_backup_returns_false_on_real_io_failure(tmp_path):
    """Fallimento di I/O vero: data_dir ha come parent un file esistente,
    quindi os.makedirs solleva. Nessuna eccezione verso il chiamante, False."""
    import os
    blocco = os.path.join(str(tmp_path), "blocco.txt")
    with open(blocco, "w", encoding="utf-8") as fh:
        fh.write("non sono una cartella")
    data_dir = os.path.join(blocco, "data")
    assert save_backup(data_dir, "casa-mia", {"views": [{"title": "A"}]}) is False
    assert latest_backup(data_dir, "casa-mia") is None


def test_identical_config_does_not_consume_the_ring(tmp_path):
    """L'apply salva lo snapshot PRIMA di poter fallire: N tentativi falliti di
    fila non devono espellere dal ring le versioni realmente precedenti."""
    import json, os
    cfg = {"views": [{"title": "STATO ATTUALE"}]}
    for _ in range(MAX_BACKUPS_PER_DASHBOARD + 3):
        assert save_backup(str(tmp_path), "casa-mia", cfg) is True
    with open(os.path.join(str(tmp_path), "dashboard_backups.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    assert len(data["casa-mia"]) == 1
    assert latest_backup(str(tmp_path), "casa-mia") == cfg


def test_identical_config_preserves_older_versions(tmp_path):
    """Il caso che conta: dopo una versione vecchia, i tentativi ripetuti sulla
    stessa config attuale non devono spazzare via la versione precedente."""
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "VECCHIA"}]})
    attuale = {"views": [{"title": "ATTUALE"}]}
    for _ in range(5):
        save_backup(str(tmp_path), "casa-mia", attuale)
    import json, os
    with open(os.path.join(str(tmp_path), "dashboard_backups.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    assert [b["config"]["views"][0]["title"] for b in data["casa-mia"]] == ["VECCHIA", "ATTUALE"]


def test_save_is_atomic_no_tmp_file_left_behind(tmp_path):
    """La scrittura passa da file temporaneo + os.replace: dopo un save
    non deve restare alcun residuo .tmp, solo il file finale."""
    import os
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "A"}]})
    names = os.listdir(str(tmp_path))
    assert names == ["dashboard_backups.json"]


def test_save_creates_missing_data_dir(tmp_path):
    """Se data_dir non esiste ancora, save_backup lo crea invece di
    fallire in silenzio senza lasciare traccia."""
    import os
    missing_dir = os.path.join(str(tmp_path), "nested", "data")
    assert not os.path.isdir(missing_dir)
    save_backup(missing_dir, "casa-mia", {"views": [{"title": "A"}]})
    assert latest_backup(missing_dir, "casa-mia") == {"views": [{"title": "A"}]}


# --- istante di salvataggio -------------------------------------------------

def _leggi_store(tmp_path):
    import json, os
    with open(os.path.join(str(tmp_path), "dashboard_backups.json"), encoding="utf-8") as fh:
        return json.load(fh)


def test_save_backup_registra_istante_iso_utc(tmp_path):
    """L'interfaccia deve poter dire QUANDO e' stato preso lo snapshot per
    distinguere un undo recente da un ripristino storico: l'istante va scritto
    con lo snapshot, in ISO 8601 UTC."""
    from datetime import datetime
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "A"}]})
    entry = _leggi_store(tmp_path)["casa-mia"][-1]
    assert "saved_at" in entry
    istante = datetime.fromisoformat(entry["saved_at"])
    assert istante.utcoffset() is not None and istante.utcoffset().total_seconds() == 0


def test_deduplica_resta_attiva_nonostante_istante(tmp_path):
    """L'aggiunta dell'istante non deve confondere il confronto di deduplica:
    due save della stessa config restano un solo snapshot anche se gli istanti
    di salvataggio sono diversi."""
    cfg = {"views": [{"title": "STATO ATTUALE"}]}
    assert save_backup(str(tmp_path), "casa-mia", cfg) is True
    assert save_backup(str(tmp_path), "casa-mia", cfg) is True
    assert len(_leggi_store(tmp_path)["casa-mia"]) == 1


def test_latest_backup_ignora_istante_e_torna_solo_la_config(tmp_path):
    """Il restore ri-applica la config: l'istante e' metadato, non deve
    finire dentro la configurazione mandata a Home Assistant."""
    cfg = {"views": [{"title": "A"}]}
    save_backup(str(tmp_path), "casa-mia", cfg)
    assert latest_backup(str(tmp_path), "casa-mia") == cfg


def _scrivi_store(tmp_path, data):
    import json, os
    with open(os.path.join(str(tmp_path), "dashboard_backups.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def test_snapshot_legacy_senza_istante_resta_ripristinabile(tmp_path):
    """Gli snapshot gia' su disco non hanno l'istante: valgono come 'istante
    sconosciuto', non come errore."""
    _scrivi_store(tmp_path, {"casa-mia": [{"config": {"views": [{"title": "VECCHIA"}]}}]})
    assert latest_backup(str(tmp_path), "casa-mia") == {"views": [{"title": "VECCHIA"}]}


# --- elenco degli snapshot --------------------------------------------------

def test_list_backups_vuota_senza_store(tmp_path):
    assert list_backups(str(tmp_path)) == []


def test_list_backups_vuota_su_store_corrotto(tmp_path):
    """Permissiva come latest_backup: mai un'eccezione verso il chiamante."""
    import os
    with open(os.path.join(str(tmp_path), "dashboard_backups.json"), "w", encoding="utf-8") as fh:
        fh.write("{non json")
    assert list_backups(str(tmp_path)) == []


def test_list_backups_riporta_plancia_istante_e_quantita(tmp_path):
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "A"}]})
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "B"}]})
    elenco = list_backups(str(tmp_path))
    assert len(elenco) == 1
    voce = elenco[0]
    assert voce["url_path"] == "casa-mia"
    assert voce["count"] == 2
    assert isinstance(voce["saved_at"], str) and voce["saved_at"]


def test_list_backups_non_espone_le_config(tmp_path):
    """Solo metadati: le config delle plance dell'utente non escono di qui."""
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "SEGRETO"}]})
    voce = list_backups(str(tmp_path))[0]
    assert set(voce) == {"url_path", "saved_at", "count"}
    assert "SEGRETO" not in repr(voce)


def test_list_backups_usa_istante_del_piu_recente(tmp_path):
    """L'istante riportato e' quello dell'ultimo snapshot, non del primo."""
    _scrivi_store(tmp_path, {"casa-mia": [
        {"config": {"views": []}, "saved_at": "2026-01-01T00:00:00+00:00"},
        {"config": {"views": [{"title": "B"}]}, "saved_at": "2026-06-01T00:00:00+00:00"},
    ]})
    assert list_backups(str(tmp_path))[0]["saved_at"] == "2026-06-01T00:00:00+00:00"


def test_list_backups_ordinata_dal_piu_recente(tmp_path):
    _scrivi_store(tmp_path, {
        "vecchia": [{"config": {}, "saved_at": "2026-01-01T00:00:00+00:00"}],
        "recente": [{"config": {}, "saved_at": "2026-07-01T00:00:00+00:00"}],
        "mediana": [{"config": {}, "saved_at": "2026-04-01T00:00:00+00:00"}],
    })
    assert [v["url_path"] for v in list_backups(str(tmp_path))] == [
        "recente", "mediana", "vecchia"]


def test_list_backups_mette_in_fondo_le_voci_senza_istante(tmp_path):
    """Senza istante lo snapshot precede l'introduzione del campo: e' la voce
    piu' vecchia che ci sia, va in coda."""
    _scrivi_store(tmp_path, {
        "legacy": [{"config": {}}],
        "recente": [{"config": {}, "saved_at": "2026-07-01T00:00:00+00:00"}],
    })
    elenco = list_backups(str(tmp_path))
    assert [v["url_path"] for v in elenco] == ["recente", "legacy"]
    assert elenco[1]["saved_at"] is None


def test_list_backups_salta_plance_senza_snapshot(tmp_path):
    _scrivi_store(tmp_path, {"vuota": [], "rotta": "non una lista",
                             "buona": [{"config": {}, "saved_at": "2026-07-01T00:00:00+00:00"}]})
    assert [v["url_path"] for v in list_backups(str(tmp_path))] == ["buona"]
