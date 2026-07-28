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
