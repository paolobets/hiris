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


# ---------------------------------------------------------------------------
# `None` vs `[]` -- UNA sola semantica lungo tutta la catena.
#
# `task_engine._run_action` ha SEMPRE letto `[]` come "nessuna concessione"
# (`if task.allowed_entities is not None`, vedi
# tests/test_task_engine.py::test_task_empty_allow_lists_refuse_everything e
# ::test_task_without_perimeter_is_unconfined_as_before). Il dispatcher lo
# leggeva invece per truthiness, cioe' come "nessuna restrizione": lo STESSO
# valore significava cose OPPOSTE ai due capi della stessa chiamata, e un
# agente objective senza perimetro dichiarato leggeva tutta la casa mentre
# ogni Task che emetteva era silenziosamente inerte.
#
# Questi test inchiodano il capo "dispatcher"; i due citati sopra inchiodano
# il capo "task_engine". Vanno letti insieme.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_get_area_entities_empty_allow_list_denies_everything():
    """`[]` = "nessuna entita' concessa" -> nemmeno una area sopravvive.
    NON e' l'equivalente di `None`."""
    d = ToolDispatcher(_FakeHA(), notify_config={}, entity_cache=_FakeCache(_AREA_MAP))
    out = await d.dispatch("get_area_entities", {}, allowed_entities=[])
    assert out == {}


@pytest.mark.asyncio
async def test_dispatch_none_and_empty_allow_list_are_opposites():
    """Il cuore del fix, in un solo assert: i due valori "vuoti" non sono
    intercambiabili. Se qualcuno rimette la truthiness (`if allowed_entities:`)
    al posto di `is None`, questo test cade."""
    d = ToolDispatcher(_FakeHA(), notify_config={}, entity_cache=_FakeCache(_AREA_MAP))
    unrestricted = await d.dispatch("get_area_entities", {}, allowed_entities=None)
    denied = await d.dispatch("get_area_entities", {}, allowed_entities=[])
    assert unrestricted == _AREA_MAP
    assert denied == {}
    assert unrestricted != denied


@pytest.mark.asyncio
async def test_check_entity_allowed_none_permits_empty_list_denies():
    """Stessa distinzione sull'helper di AZIONE (non di lettura)."""
    from hiris.app.tools.dispatcher import _check_entity_allowed, _check_service_allowed

    assert _check_entity_allowed("light.sala", None) is None
    assert _check_service_allowed("light.turn_on", None) is None

    blocked_entity = _check_entity_allowed("light.sala", [])
    blocked_service = _check_service_allowed("light.turn_on", [])
    assert blocked_entity is not None and "not permitted" in blocked_entity["error"]
    assert blocked_service is not None and "not permitted" in blocked_service["error"]
