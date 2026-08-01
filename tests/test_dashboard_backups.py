from hiris.app.proxy.dashboard_backups import (
    save_backup, latest_backup, MAX_BACKUPS_PER_DASHBOARD,
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
