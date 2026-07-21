from hiris.app.watcher.off_task import build_off_task


def test_build_off_task_for_irrigation():
    a = {"domain": "switch", "service": "turn_on", "entity_id": "switch.irr", "data": {}, "off_after_min": 5}
    t = build_off_task(a)
    assert t["trigger"] == {"type": "delay", "minutes": 5}
    assert t["actions"][0] == {"type": "call_ha_service", "domain": "switch",
                               "service": "turn_off", "data": {"entity_id": "switch.irr"}}
    assert t["one_shot"] is True


def test_build_off_task_none_when_no_off():
    assert build_off_task({"domain": "switch", "service": "turn_on", "entity_id": "switch.irr"}) is None
    assert build_off_task({"off_after_min": 0, "entity_id": "switch.irr", "service": "turn_on"}) is None
