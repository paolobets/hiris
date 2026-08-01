import sqlite3

from hiris.app.brain.advisory_store import AdvisoryStore

CHECK_IDS = {"low_battery", "entity_unavailable"}


def _cand(ref, check="low_battery", sev="warn"):
    return {"check_id": check, "severity": sev, "title": "t",
            "evidence": {"entity_id": ref}, "suggested_fix": "fix",
            "fix_kind": "manual", "source_ref": ref}


def test_reconcile_insert_then_idempotent_update(tmp_path):
    s = AdvisoryStore(str(tmp_path / "a.db"))
    r1 = s.reconcile([_cand("low_battery:sensor.a")], CHECK_IDS, now="2026-07-28T08:00:00Z")
    assert r1["inserted"] == 1
    r2 = s.reconcile([_cand("low_battery:sensor.a")], CHECK_IDS, now="2026-07-28T09:00:00Z")
    assert r2["inserted"] == 0 and r2["updated"] == 1
    rows = s.list()
    assert len(rows) == 1 and rows[0]["status"] == "open"
    s.close()


def test_reconcile_auto_resolves_when_gone(tmp_path):
    s = AdvisoryStore(str(tmp_path / "a.db"))
    s.reconcile([_cand("low_battery:sensor.a")], CHECK_IDS, now="2026-07-28T08:00:00Z")
    r = s.reconcile([], CHECK_IDS, now="2026-07-28T10:00:00Z")
    assert r["resolved"] == 1
    row = s.list()[0]
    assert row["status"] == "resolved" and row["resolved_auto"] == 1
    s.close()


def test_dismissed_is_suppressed(tmp_path):
    s = AdvisoryStore(str(tmp_path / "a.db"))
    s.reconcile([_cand("low_battery:sensor.a")], CHECK_IDS, now="2026-07-28T08:00:00Z")
    aid = s.list()[0]["id"]
    assert s.set_status(aid, "dismissed") is True
    r = s.reconcile([_cand("low_battery:sensor.a")], CHECK_IDS, now="2026-07-28T09:00:00Z")
    assert r["inserted"] == 0 and r["reopened"] == 0
    assert s.list()[0]["status"] == "dismissed"
    s.close()


def test_resolved_reopens_on_recurrence(tmp_path):
    s = AdvisoryStore(str(tmp_path / "a.db"))
    s.reconcile([_cand("low_battery:sensor.a")], CHECK_IDS, now="2026-07-28T08:00:00Z")
    s.reconcile([], CHECK_IDS, now="2026-07-28T09:00:00Z")  # auto-resolve
    r = s.reconcile([_cand("low_battery:sensor.a")], CHECK_IDS, now="2026-07-28T10:00:00Z")
    assert r["reopened"] == 1
    assert s.list()[0]["status"] == "open"
    s.close()


def test_set_status_rejects_bad_status(tmp_path):
    s = AdvisoryStore(str(tmp_path / "a.db"))
    s.reconcile([_cand("low_battery:sensor.a")], CHECK_IDS, now="2026-07-28T08:00:00Z")
    aid = s.list()[0]["id"]
    assert s.set_status(aid, "applied") is False
    assert s.set_status(9999, "acknowledged") is False
    s.close()


def test_auto_resolve_scoped_to_ran_checks(tmp_path):
    # An advisory whose check did NOT run this scan must NOT be auto-resolved.
    s = AdvisoryStore(str(tmp_path / "a.db"))
    s.reconcile([_cand("entity_unavailable:x", check="entity_unavailable")],
                {"entity_unavailable"}, now="2026-07-28T08:00:00Z")
    r = s.reconcile([], {"low_battery"}, now="2026-07-28T09:00:00Z")
    assert r["resolved"] == 0
    assert s.list()[0]["status"] == "open"
    s.close()


def test_reconcile_riporta_le_voci_inserite(tmp_path):
    """Chi chiama deve sapere QUALI segnalazioni sono nuove, non solo quante.

    I contatori esistenti restano identici (retro-compatibilita'): chi legge
    solo `inserted`/`updated`/`reopened`/`resolved` non si accorge di nulla.
    """
    s = AdvisoryStore(str(tmp_path / "a.db"))
    r = s.reconcile([_cand("low_battery:sensor.a"), _cand("low_battery:sensor.b")],
                    CHECK_IDS, now="2026-07-28T08:00:00Z")
    assert r["inserted"] == 2
    assert r["updated"] == 0 and r["reopened"] == 0 and r["resolved"] == 0
    assert [v["source_ref"] for v in r["inserted_items"]] == [
        "low_battery:sensor.a", "low_battery:sensor.b"]
    assert r["reopened_items"] == [] and r["escalated_items"] == []
    s.close()


def test_reconcile_non_riporta_le_voci_solo_aggiornate(tmp_path):
    """Una segnalazione gia' aperta che cambia solo contenuto non e' un evento."""
    s = AdvisoryStore(str(tmp_path / "a.db"))
    s.reconcile([_cand("low_battery:sensor.a")], CHECK_IDS, now="2026-07-28T08:00:00Z")
    r = s.reconcile([_cand("low_battery:sensor.a")], CHECK_IDS, now="2026-07-28T09:00:00Z")
    assert r["updated"] == 1
    assert r["inserted_items"] == [] and r["reopened_items"] == []
    assert r["escalated_items"] == []
    s.close()


def test_reconcile_riporta_le_voci_riaperte(tmp_path):
    s = AdvisoryStore(str(tmp_path / "a.db"))
    s.reconcile([_cand("low_battery:sensor.a")], CHECK_IDS, now="2026-07-28T08:00:00Z")
    s.reconcile([], CHECK_IDS, now="2026-07-28T09:00:00Z")  # rientrata da sola
    r = s.reconcile([_cand("low_battery:sensor.a")], CHECK_IDS, now="2026-07-28T10:00:00Z")
    assert r["reopened"] == 1
    assert [v["source_ref"] for v in r["reopened_items"]] == ["low_battery:sensor.a"]
    assert r["inserted_items"] == []
    s.close()


def test_reconcile_segnala_innalzamento_a_grave(tmp_path):
    """Un avviso gia' aperto che diventa grave e' un evento nuovo.

    Caso reale: un add-on fermo (avviso) che poi va in errore (grave). Il
    riferimento di deduplica non cambia, quindi per `reconcile` e' un semplice
    aggiornamento: senza questo elenco il guasto vero resterebbe muto.
    """
    s = AdvisoryStore(str(tmp_path / "a.db"))
    s.reconcile([_cand("addon_down:samba", check="entity_unavailable", sev="warn")],
                CHECK_IDS, now="2026-07-28T08:00:00Z")
    r = s.reconcile([_cand("addon_down:samba", check="entity_unavailable", sev="high")],
                    CHECK_IDS, now="2026-07-28T09:00:00Z")
    assert r["updated"] == 1  # resta un aggiornamento per i contatori
    assert [v["source_ref"] for v in r["escalated_items"]] == ["addon_down:samba"]
    assert r["inserted_items"] == [] and r["reopened_items"] == []
    s.close()


def test_reconcile_grave_che_resta_grave_non_e_un_innalzamento(tmp_path):
    """Il disco pieno cambia titolo a ogni scansione ma resta grave: mai un evento."""
    s = AdvisoryStore(str(tmp_path / "a.db"))
    s.reconcile([_cand("disk_space:host", sev="high")], CHECK_IDS,
                now="2026-07-28T08:00:00Z")
    r = s.reconcile([_cand("disk_space:host", sev="high")], CHECK_IDS,
                    now="2026-07-28T09:00:00Z")
    assert r["updated"] == 1
    assert r["escalated_items"] == []
    s.close()


def test_memoria_notifiche_registra_e_rilegge(tmp_path):
    """Fix wave 1 (FIX 1): serve una memoria di "per questo problema ho gia'
    avvisato", altrimenti un valore che sfarfalla attorno a una soglia produce
    notifiche a ripetizione."""
    s = AdvisoryStore(str(tmp_path / "a.db"))
    assert s.notificati_dopo(["disk_space:host"], "2026-07-28T00:00:00Z") == set()
    s.registra_notifica("disk_space:host", now="2026-07-28T08:00:00Z")
    assert s.notificati_dopo(["disk_space:host"], "2026-07-28T00:00:00Z") == {
        "disk_space:host"}
    s.close()


def test_memoria_notifiche_dimentica_le_vecchie(tmp_path):
    """Il silenzio deve scadere: un problema che si ripresenta giorni dopo e'
    una notizia nuova, non una ripetizione."""
    s = AdvisoryStore(str(tmp_path / "a.db"))
    s.registra_notifica("disk_space:host", now="2026-07-28T08:00:00Z")
    assert s.notificati_dopo(["disk_space:host"], "2026-07-29T08:00:00Z") == set()
    s.close()


def test_memoria_notifiche_isola_i_riferimenti(tmp_path):
    """Il silenzio su un problema non deve mai coprirne un altro."""
    s = AdvisoryStore(str(tmp_path / "a.db"))
    s.registra_notifica("disk_space:host", now="2026-07-28T08:00:00Z")
    assert s.notificati_dopo(["disk_space:host", "addon_down:samba"],
                             "2026-07-28T00:00:00Z") == {"disk_space:host"}
    assert s.notificati_dopo([], "2026-07-28T00:00:00Z") == set()
    s.close()


def test_memoria_notifiche_sopravvive_alla_riapertura(tmp_path):
    """Deve stare su disco come il resto dell'archivio: un riavvio dell'add-on
    non deve far ripartire le notifiche gia' date."""
    percorso = str(tmp_path / "a.db")
    s = AdvisoryStore(percorso)
    s.registra_notifica("addon_down:samba", now="2026-07-28T08:00:00Z")
    s.close()
    s2 = AdvisoryStore(percorso)
    assert s2.notificati_dopo(["addon_down:samba"], "2026-07-28T00:00:00Z") == {
        "addon_down:samba"}
    s2.close()


def test_memoria_notifiche_riscrive_l_ultima_data(tmp_path):
    """Notificare di nuovo dopo la scadenza fa ripartire il silenzio da capo."""
    s = AdvisoryStore(str(tmp_path / "a.db"))
    s.registra_notifica("addon_down:samba", now="2026-07-28T08:00:00Z")
    s.registra_notifica("addon_down:samba", now="2026-07-30T08:00:00Z")
    assert s.notificati_dopo(["addon_down:samba"], "2026-07-29T00:00:00Z") == {
        "addon_down:samba"}
    s.close()


def test_memoria_notifiche_si_aggiunge_a_un_archivio_esistente(tmp_path):
    """L'archivio esiste gia' su ogni installazione: aprirlo con lo schema
    nuovo deve aggiungere la memoria senza perdere le segnalazioni."""
    percorso = str(tmp_path / "a.db")
    conn = sqlite3.connect(percorso)
    conn.executescript("""
        CREATE TABLE advisories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, check_id TEXT NOT NULL,
            ts_created TEXT NOT NULL, ts_updated TEXT NOT NULL,
            severity TEXT NOT NULL, title TEXT NOT NULL, evidence TEXT NOT NULL,
            suggested_fix TEXT NOT NULL, fix_kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open', source_ref TEXT NOT NULL UNIQUE,
            resolved_auto INTEGER NOT NULL DEFAULT 0);
    """)
    conn.execute(
        "INSERT INTO advisories(check_id, ts_created, ts_updated, severity, title, "
        "evidence, suggested_fix, fix_kind, status, source_ref, resolved_auto) "
        "VALUES('low_battery','2026-07-01T00:00:00Z','2026-07-01T00:00:00Z','warn',"
        "'t','{}','fix','manual','open','low_battery:sensor.a',0)")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    s = AdvisoryStore(percorso)
    assert [r["source_ref"] for r in s.list()] == ["low_battery:sensor.a"]
    s.registra_notifica("low_battery:sensor.a", now="2026-07-28T08:00:00Z")
    assert s.notificati_dopo(["low_battery:sensor.a"], "2026-07-28T00:00:00Z") == {
        "low_battery:sensor.a"}
    s.close()


def test_reconcile_dedupes_duplicate_source_ref(tmp_path):
    # Test that reconcile dedupes candidates with duplicate source_ref (last-wins).
    # This ensures the UNIQUE(source_ref) constraint never crashes during reconcile.
    s = AdvisoryStore(str(tmp_path / "a.db"))
    ref = "low_battery:sensor.a"
    cands = [
        {"check_id": "low_battery", "severity": "warn", "title": "first",
         "evidence": {"entity_id": ref}, "suggested_fix": "fix1",
         "fix_kind": "manual", "source_ref": ref},
        {"check_id": "low_battery", "severity": "error", "title": "second",
         "evidence": {"entity_id": ref}, "suggested_fix": "fix2",
         "fix_kind": "manual", "source_ref": ref},
    ]
    r = s.reconcile(cands, CHECK_IDS, now="2026-07-28T08:00:00Z")
    assert r["inserted"] == 1
    rows = s.list()
    assert len(rows) == 1
    assert rows[0]["source_ref"] == ref
    assert rows[0]["title"] == "second"  # last-wins
    s.close()
