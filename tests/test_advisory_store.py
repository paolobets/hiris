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
