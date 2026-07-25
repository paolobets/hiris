import pytest
from hiris.app.tools.dispatcher import ToolDispatcher


class _FakeHA:
    async def get_history(self, entity_ids, days):
        return [{"entity_id": eid, "last_changed": "2026-06-26T10:00:00+00:00",
                 "state": "21.0"} for eid in entity_ids]

    async def get_statistics(self, statistic_ids, period, days):
        return {}


@pytest.mark.asyncio
async def test_dispatch_get_history_returns_series():
    d = ToolDispatcher(_FakeHA(), notify_config={})
    out = await d.dispatch("get_history",
                           {"entity_ids": ["sensor.temp"], "days": 3})
    assert isinstance(out, list)
    assert out[0]["id"] == "sensor.temp"


@pytest.mark.asyncio
async def test_dispatch_get_history_unscoped_agent_gets_full_results():
    # allowed_entities=None (unscoped agent) -> no filtering, full results.
    d = ToolDispatcher(_FakeHA(), notify_config={})
    out = await d.dispatch("get_history", {"entity_ids": ["sensor.temp"], "days": 3},
                           allowed_entities=None)
    assert out[0]["id"] == "sensor.temp"


@pytest.mark.asyncio
async def test_dispatch_get_history_filters_by_allowed_entities():
    # review B/#12: get_history must filter caller-supplied entity_ids against
    # allowed_entities, exactly like the parallel get_entity_states branch —
    # an entity-scoped agent must not be able to pull history for entities
    # outside its scope (e.g. lock/alarm/presence).
    d = ToolDispatcher(_FakeHA(), notify_config={})
    out = await d.dispatch("get_history",
                           {"entity_ids": ["light.a", "lock.front"], "days": 3},
                           allowed_entities=["light.*"])
    ids = [s["id"] for s in out]
    assert ids == ["light.a"]
    assert "lock.front" not in ids


@pytest.mark.asyncio
async def test_dispatch_get_history_filters_by_visible_entity_ids():
    d = ToolDispatcher(_FakeHA(), notify_config={})
    out = await d.dispatch("get_history",
                           {"entity_ids": ["light.a", "lock.front"], "days": 3},
                           visible_entity_ids=frozenset({"light.a"}))
    ids = [s["id"] for s in out]
    assert ids == ["light.a"]


class _StoreFake:
    def has_entity(self, eid): return True
    def query(self, eid, days, today):
        return {"id": eid, "source": "store", "unit": None,
                "buckets": [{"t": "2026-06-19", "mean": 2.0, "min": 1.0, "max": 3.0, "n": 4}]}


@pytest.mark.asyncio
async def test_dispatch_get_history_prefers_store_when_present():
    d = ToolDispatcher(_FakeHA(), notify_config={}, history_store=_StoreFake())
    out = await d.dispatch("get_history", {"entity_ids": ["climate.x"], "days": 30})
    assert out[0]["source"] == "store"
