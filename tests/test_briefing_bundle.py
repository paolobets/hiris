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
        store, cache, {}, today=today, allow_sensitive=True, horizon_days=7,
    )

    assert [d["content"] for d in bundle["deadlines"]] == ["Vicina"]
    assert bundle["deadlines"][0]["days_left"] == 2
    assert bundle["counts"]["deadlines"] == 1
    store.close()


def test_sensitive_excluded_unless_allowed(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    today = date(2026, 7, 25)
    store.add_item(kind="obligation", content="Segreto", status="approved",
                    due_date="2026-07-26", sensitivity="sensitive")
    cache = FakeEntityCache([])

    hidden = build_briefing_bundle(
        store, cache, {}, today=today, allow_sensitive=False, horizon_days=7,
    )
    assert hidden["deadlines"] == []
    assert hidden["counts"]["hidden_sensitive"] == 1

    shown = build_briefing_bundle(
        store, cache, {}, today=today, allow_sensitive=True, horizon_days=7,
    )
    assert [d["content"] for d in shown["deadlines"]] == ["Segreto"]
    assert shown["counts"]["hidden_sensitive"] == 0
    store.close()


def test_home_open_door_and_low_battery_detected(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    today = date(2026, 7, 25)
    cache = FakeEntityCache([
        _mk_state("binary_sensor.porta", "on", name="porta", device_class="door"),
        _mk_state("binary_sensor.finestra", "off", name="finestra", device_class="window"),
        _mk_state("sensor.batteria_x", "5", name="x", device_class="battery", unit="%"),
        _mk_state("sensor.batteria_y", "80", name="y", device_class="battery", unit="%"),
    ])
    policy = {"detectors": {"battery": {"min_pct": 10}}}

    bundle = build_briefing_bundle(
        store, cache, policy, today=today, allow_sensitive=True, horizon_days=7,
    )

    assert [e["name"] for e in bundle["home"]["open_now"]] == ["porta"]
    assert bundle["home"]["low_batteries"] == [{"name": "x", "pct": 5.0}]
    assert bundle["counts"]["open_now"] == 1
    assert bundle["counts"]["low_batteries"] == 1
    store.close()


def test_none_store_and_cache_never_crash():
    today = date(2026, 7, 25)
    bundle = build_briefing_bundle(
        None, None, {}, today=today, allow_sensitive=True, horizon_days=7,
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
        store, cache, {}, today=today, allow_sensitive=True, horizon_days=7,
    )

    assert bundle["deadlines"] == []
    assert bundle["home"] == {"open_now": [], "low_batteries": []}
    assert bundle["counts"] == {
        "deadlines": 0, "hidden_sensitive": 0, "open_now": 0, "low_batteries": 0,
    }


def test_home_status_capped_at_20_each():
    """T1: more than 20 open entities and more than 20 low-battery entities
    must each be capped at 20 in both the returned lists and the counts."""
    today = date(2026, 7, 25)
    store = FakeKnowledgeStore([])
    states = [
        _mk_state(f"binary_sensor.porta_{i}", "on", name=f"porta{i}", device_class="door")
        for i in range(25)
    ] + [
        _mk_state(f"sensor.batteria_{i}", "5", name=f"batt{i}", device_class="battery", unit="%")
        for i in range(25)
    ]
    cache = FakeEntityCache(states)

    bundle = build_briefing_bundle(
        store, cache, {}, today=today, allow_sensitive=True, horizon_days=7,
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
        store, cache, {}, today=today, allow_sensitive=True, horizon_days=7,
    )

    assert len(bundle["deadlines"]) == 1
    entry = bundle["deadlines"][0]
    assert entry["content"] == "Scadenza corrotta"
    assert entry["due_date"] == "not-a-date"
    assert entry["days_left"] is None


def test_battery_default_threshold_used_when_policy_has_no_min_pct():
    """T1: with policy={} (no detectors.battery.min_pct saved), the battery
    threshold must fall back to build_briefing_bundle's battery_default_pct
    (default 20) -- a battery at 15% is below that default and gets flagged."""
    today = date(2026, 7, 25)
    store = FakeKnowledgeStore([])
    cache = FakeEntityCache([
        _mk_state("sensor.batteria_z", "15", name="z", device_class="battery", unit="%"),
    ])

    bundle = build_briefing_bundle(
        store, cache, {}, today=today, allow_sensitive=True, horizon_days=7,
    )

    assert bundle["home"]["low_batteries"] == [{"name": "z", "pct": 15.0}]
    assert bundle["counts"]["low_batteries"] == 1
