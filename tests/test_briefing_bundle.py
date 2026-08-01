from datetime import date

from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.brain.briefing import build_briefing_bundle


class FakeEntityCache:
    """Minimal stand-in for hiris.app.proxy.entity_cache.EntityCache.all_states(),
    which returns a LIST of dicts shaped like entity_cache._to_minimal():
    {"id","state","name","unit","domain","device_class",("attributes")}."""

    def __init__(self, states: list[dict]) -> None:
        self._states = states

    def all_states(self) -> list[dict]:
        return list(self._states)


class RaisingEntityCache:
    """Stand-in whose all_states() always raises, to exercise the T1
    defensive path around home-status collection."""

    def all_states(self) -> list[dict]:
        raise RuntimeError("boom")


class FakeKnowledgeStore:
    """Minimal stand-in for KnowledgeStore.upcoming_obligations(). Lets tests
    hand back arbitrary/malformed rows directly (bypassing the real store's
    SQL lexicographic due_date filter) or force a raise, to exercise the T1
    defensive path around deadline collection."""

    def __init__(self, rows: list[dict] | None = None, *, raises: bool = False) -> None:
        self._rows = rows or []
        self._raises = raises

    def upcoming_obligations(self, *, before: str, owner: str | None = None) -> list[dict]:
        if self._raises:
            raise RuntimeError("boom")
        return list(self._rows)


class FakeAdvisoryStore:
    """Stand-in per AdvisoryStore.list(status=...): restituisce righe gia'
    deserializzate (evidence come dict), la stessa forma dello store vero."""

    def __init__(self, rows: list[dict] | None = None, *, raises: bool = False) -> None:
        self._rows = rows or []
        self._raises = raises

    def list(self, *, status: str | None = None) -> list[dict]:
        if self._raises:
            raise RuntimeError("boom")
        if status is None:
            return list(self._rows)
        return [r for r in self._rows if r.get("status") == status]


def _mk_advisory(eid, pct, *, name="", status="open", check_id="low_battery"):
    """Riga di segnalazione come la produce check_low_battery + AdvisoryStore."""
    return {
        "id": 1, "check_id": check_id, "severity": "warn",
        "title": f"Batteria scarica: {name or eid}",
        "evidence": {"entity_id": eid, "pct": pct},
        "suggested_fix": "Sostituisci le pile.", "fix_kind": "manual",
        "status": status, "source_ref": f"{check_id}:{eid}",
    }


def _mk_state(eid, state, *, name="", device_class=None, unit=""):
    return {
        "id": eid,
        "state": state,
        "name": name,
        "unit": unit,
        "domain": eid.split(".", 1)[0],
        "device_class": device_class,
    }


def test_horizon_filters_and_days_left(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    today = date(2026, 7, 25)
    store.add_item(kind="obligation", content="Vicina", status="approved",
                    due_date="2026-07-27", sensitivity="normal")
    store.add_item(kind="obligation", content="Lontana", status="approved",
                    due_date="2026-08-04", sensitivity="normal")
    cache = FakeEntityCache([])

    bundle = build_briefing_bundle(
        store, cache, today=today, allow_sensitive=True, horizon_days=7,
    )

    assert [d["content"] for d in bundle["deadlines"]] == ["Vicina"]
    assert bundle["deadlines"][0]["days_left"] == 2
    assert bundle["counts"]["deadlines"] == 1
    store.close()


def test_owner_scoping_home_broadcast_vs_per_user(tmp_path):
    # review C/#2 follow-up: default owner="home" (scheduled broadcast) shows
    # only shared obligations; the on-demand tool passing owner=<user> also
    # shows that user's OWN private obligations, but never another user's.
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    today = date(2026, 7, 25)
    store.add_item(kind="obligation", content="Bolletta casa", status="approved",
                   owner="home", due_date="2026-07-27", sensitivity="normal")
    store.add_item(kind="obligation", content="Privata di Alice", status="approved",
                   owner="alice", due_date="2026-07-27", sensitivity="normal")
    cache = FakeEntityCache([])

    home = build_briefing_bundle(store, cache, today=today, allow_sensitive=True)
    assert [d["content"] for d in home["deadlines"]] == ["Bolletta casa"]  # no private leak

    alice = build_briefing_bundle(store, cache, today=today, allow_sensitive=True, owner="alice")
    contents = {d["content"] for d in alice["deadlines"]}
    assert contents == {"Bolletta casa", "Privata di Alice"}  # own + home

    bob = build_briefing_bundle(store, cache, today=today, allow_sensitive=True, owner="bob")
    assert [d["content"] for d in bob["deadlines"]] == ["Bolletta casa"]  # not alice's
    store.close()


def test_sensitive_excluded_unless_allowed(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    today = date(2026, 7, 25)
    store.add_item(kind="obligation", content="Segreto", status="approved",
                    due_date="2026-07-26", sensitivity="sensitive")
    cache = FakeEntityCache([])

    hidden = build_briefing_bundle(
        store, cache, today=today, allow_sensitive=False, horizon_days=7,
    )
    assert hidden["deadlines"] == []
    assert hidden["counts"]["hidden_sensitive"] == 1

    shown = build_briefing_bundle(
        store, cache, today=today, allow_sensitive=True, horizon_days=7,
    )
    assert [d["content"] for d in shown["deadlines"]] == ["Segreto"]
    assert shown["counts"]["hidden_sensitive"] == 0
    store.close()


def test_home_open_door_from_cache_and_low_battery_from_advisories(tmp_path):
    """Le aperture restano di competenza della EntityCache; le batterie
    arrivano dalle segnalazioni del Brain e NON sono piu' ricalcolate qui:
    il sensore scarico in cache non basta a farle comparire."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    today = date(2026, 7, 25)
    cache = FakeEntityCache([
        _mk_state("binary_sensor.porta", "on", name="porta", device_class="door"),
        _mk_state("binary_sensor.finestra", "off", name="finestra", device_class="window"),
        _mk_state("sensor.batteria_x", "5", name="x", device_class="battery", unit="%"),
        _mk_state("sensor.batteria_y", "80", name="y", device_class="battery", unit="%"),
    ])
    advisories = FakeAdvisoryStore([_mk_advisory("sensor.batteria_w", 4.0, name="w")])

    bundle = build_briefing_bundle(
        store, cache, today=today, allow_sensitive=True, horizon_days=7,
        advisory_store=advisories,
    )

    assert [e["name"] for e in bundle["home"]["open_now"]] == ["porta"]
    assert bundle["home"]["low_batteries"] == [{"name": "w", "pct": 4.0}]
    assert bundle["counts"]["open_now"] == 1
    assert bundle["counts"]["low_batteries"] == 1
    store.close()


def test_batteries_only_from_active_advisories():
    """Solo `open` e `acknowledged` sono attive: una risolta e' rientrata, una
    messa a tacere dall'utente non deve riemergere. Le segnalazioni di altri
    controlli non finiscono fra le batterie."""
    today = date(2026, 7, 25)
    advisories = FakeAdvisoryStore([
        _mk_advisory("sensor.b_open", 5.0, name="aperta", status="open"),
        _mk_advisory("sensor.b_ack", 6.0, name="presa_atto", status="acknowledged"),
        _mk_advisory("sensor.b_res", 7.0, name="rientrata", status="resolved"),
        _mk_advisory("sensor.b_dis", 8.0, name="tacitata", status="dismissed"),
        {"id": 9, "check_id": "disk_space", "severity": "high",
         "title": "Spazio su disco quasi esaurito: 5% libero",
         "evidence": {"free_pct": 5}, "suggested_fix": "Libera spazio.",
         "fix_kind": "manual", "status": "open", "source_ref": "disk_space:host"},
    ])

    bundle = build_briefing_bundle(
        FakeKnowledgeStore([]), FakeEntityCache([]), today=today,
        allow_sensitive=True, advisory_store=advisories,
    )

    assert [e["name"] for e in bundle["home"]["low_batteries"]] == ["aperta", "presa_atto"]
    assert bundle["counts"]["low_batteries"] == 2


def test_raising_advisory_store_degrades_to_no_batteries():
    """Uno store che solleva non deve propagare ne' far ricadere il briefing
    sul vecchio calcolo: le batterie degradano a nessuna voce."""
    today = date(2026, 7, 25)
    cache = FakeEntityCache([
        _mk_state("sensor.batteria_x", "1", name="x", device_class="battery", unit="%"),
    ])

    bundle = build_briefing_bundle(
        FakeKnowledgeStore([]), cache, today=today, allow_sensitive=True,
        advisory_store=FakeAdvisoryStore(raises=True),
    )

    assert bundle["home"]["low_batteries"] == []
    assert bundle["counts"]["low_batteries"] == 0


def test_missing_advisory_store_means_no_batteries():
    """Fonte unica anche quando manca: senza store non si ricalcola nulla."""
    today = date(2026, 7, 25)
    cache = FakeEntityCache([
        _mk_state("sensor.batteria_x", "1", name="x", device_class="battery", unit="%"),
    ])

    bundle = build_briefing_bundle(
        FakeKnowledgeStore([]), cache, today=today, allow_sensitive=True,
    )

    assert bundle["home"]["low_batteries"] == []
    assert bundle["counts"]["low_batteries"] == 0


def test_none_store_and_cache_never_crash():
    today = date(2026, 7, 25)
    bundle = build_briefing_bundle(
        None, None, today=today, allow_sensitive=True, horizon_days=7,
    )
    assert bundle["deadlines"] == []
    assert bundle["home"] == {"open_now": [], "low_batteries": []}
    assert bundle["counts"] == {
        "deadlines": 0, "hidden_sensitive": 0, "open_now": 0, "low_batteries": 0,
    }
    assert bundle["generated_for"] == "2026-07-25"


def test_raising_store_and_cache_degrade_to_empty_without_crash():
    """T1: a store whose upcoming_obligations() raises must not propagate --
    deadlines degrade to empty. Same for a cache whose all_states() raises --
    home degrades to empty. Neither failure should affect the other section."""
    today = date(2026, 7, 25)
    store = FakeKnowledgeStore(raises=True)
    cache = RaisingEntityCache()

    bundle = build_briefing_bundle(
        store, cache, today=today, allow_sensitive=True, horizon_days=7,
    )

    assert bundle["deadlines"] == []
    assert bundle["home"] == {"open_now": [], "low_batteries": []}
    assert bundle["counts"] == {
        "deadlines": 0, "hidden_sensitive": 0, "open_now": 0, "low_batteries": 0,
    }


def test_home_status_capped_at_20_each():
    """T1: more than 20 open entities and more than 20 low-battery entities
    must each be capped at 20 in both the returned lists and the counts.
    Il cap sulle batterie vale ora sulle segnalazioni lette, non sulla cache."""
    today = date(2026, 7, 25)
    store = FakeKnowledgeStore([])
    cache = FakeEntityCache([
        _mk_state(f"binary_sensor.porta_{i}", "on", name=f"porta{i}", device_class="door")
        for i in range(25)
    ])
    advisories = FakeAdvisoryStore([
        _mk_advisory(f"sensor.batteria_{i}", 5.0, name=f"batt{i}") for i in range(25)
    ])

    bundle = build_briefing_bundle(
        store, cache, today=today, allow_sensitive=True, horizon_days=7,
        advisory_store=advisories,
    )

    assert len(bundle["home"]["open_now"]) == 20
    assert len(bundle["home"]["low_batteries"]) == 20
    assert bundle["counts"]["open_now"] == 20
    assert bundle["counts"]["low_batteries"] == 20


def test_invalid_due_date_degrades_days_left_without_crash():
    """T1: an obligation with an unparseable due_date must still be included
    (content preserved) but with days_left degraded to None, never raising."""
    today = date(2026, 7, 25)
    store = FakeKnowledgeStore([
        {"content": "Scadenza corrotta", "due_date": "not-a-date", "sensitivity": "normal"},
    ])
    cache = FakeEntityCache([])

    bundle = build_briefing_bundle(
        store, cache, today=today, allow_sensitive=True, horizon_days=7,
    )

    assert len(bundle["deadlines"]) == 1
    entry = bundle["deadlines"][0]
    assert entry["content"] == "Scadenza corrotta"
    assert entry["due_date"] == "not-a-date"
    assert entry["days_left"] is None


def test_private_obligation_excluded_from_home_wide_briefing(tmp_path):
    """Review C/#2: a PRIVATE obligation (owner='paolo') must never appear in
    the home-wide daily briefing -- only owner='home' (shared) obligations
    are visible here, since the briefing broadcasts to a single shared
    channel with no per-user delivery."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    today = date(2026, 7, 25)
    store.add_item(kind="obligation", content="Segreto di Paolo", owner="paolo",
                   status="approved", due_date="2026-07-26", sensitivity="normal")
    store.add_item(kind="obligation", content="Bolletta di casa", owner="home",
                   status="approved", due_date="2026-07-27", sensitivity="normal")
    cache = FakeEntityCache([])

    bundle = build_briefing_bundle(
        store, cache, today=today, allow_sensitive=True, horizon_days=7,
    )

    contents = [d["content"] for d in bundle["deadlines"]]
    assert "Bolletta di casa" in contents
    assert "Segreto di Paolo" not in contents
    assert bundle["counts"]["deadlines"] == 1
    store.close()


def test_battery_evidence_without_pct_still_lists_the_device():
    """Un'evidenza senza percentuale utilizzabile non fa sparire la voce: il
    dispositivo resta citato, la carica residua semplicemente non si dichiara."""
    today = date(2026, 7, 25)
    riga = _mk_advisory("sensor.batteria_muta", None, name="muta")

    bundle = build_briefing_bundle(
        FakeKnowledgeStore([]), FakeEntityCache([]), today=today,
        allow_sensitive=True, advisory_store=FakeAdvisoryStore([riga]),
    )

    assert bundle["home"]["low_batteries"] == [{"name": "muta", "pct": None}]
