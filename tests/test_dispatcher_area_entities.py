import pytest
from hiris.app.tools.dispatcher import ToolDispatcher


class _FakeCache:
    def __init__(self, area_map):
        self._area_map = area_map

    def get_area_map(self):
        return self._area_map


class _FakeHA:
    pass


_AREA_MAP = {
    "Soggiorno": ["light.sala", "lock.front_door", "camera.sala"],
    "Ingresso": ["alarm_control_panel.home", "person.paolo"],
    "__no_area__": ["device_tracker.phone"],
}


@pytest.mark.asyncio
async def test_dispatch_get_area_entities_unscoped_agent_gets_full_map():
    # allowed_entities=None (unscoped agent) -> no filtering, full map returned.
    d = ToolDispatcher(_FakeHA(), notify_config={}, entity_cache=_FakeCache(_AREA_MAP))
    out = await d.dispatch("get_area_entities", {})
    assert out == _AREA_MAP


@pytest.mark.asyncio
async def test_dispatch_get_area_entities_filters_by_allowed_entities():
    # review B/#11: an entity-scoped agent (e.g. guest persona scoped to
    # light.*) must only see permitted entities within each area, never
    # lock/alarm/camera/person/device_tracker entities from other areas.
    d = ToolDispatcher(_FakeHA(), notify_config={}, entity_cache=_FakeCache(_AREA_MAP))
    out = await d.dispatch("get_area_entities", {}, allowed_entities=["light.*"])
    assert out == {"Soggiorno": ["light.sala"]}
    all_ids = [eid for eids in out.values() for eid in eids]
    for blocked in ("lock.front_door", "camera.sala", "alarm_control_panel.home",
                    "person.paolo", "device_tracker.phone"):
        assert blocked not in all_ids


@pytest.mark.asyncio
async def test_dispatch_get_area_entities_drops_areas_left_empty():
    # An area with no permitted entities must not appear at all (matches
    # SemanticContextMap._filter_by_allowed grouped-area behavior).
    d = ToolDispatcher(_FakeHA(), notify_config={}, entity_cache=_FakeCache(_AREA_MAP))
    out = await d.dispatch("get_area_entities", {}, allowed_entities=["light.*"])
    assert "Ingresso" not in out
    assert "__no_area__" not in out
