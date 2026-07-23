import pytest
from hiris.app.brain.suggestions import SuggestionStore, validate_coverage, apply_suggestions, undo
from hiris.app.watcher.policy import load_policy

@pytest.fixture
def store(tmp_path):
    s = SuggestionStore(str(tmp_path / "s.db")); yield s; s.close()

def test_validate_coverage(tmp_path):
    inv = {"sensor.freezer"}
    ok = {"kind":"coverage","config":{"detector":"fridge_temp","entity":"sensor.freezer"}}
    assert validate_coverage(ok, inv, {"detectors":{}}) is True
    assert validate_coverage({"kind":"coverage","config":{"detector":"fridge_temp","entity":"sensor.ghost"}}, inv, {"detectors":{}}) is False
    assert validate_coverage({"kind":"coverage","config":{"detector":"bogus","entity":"sensor.freezer"}}, inv, {"detectors":{}}) is False

def test_apply_and_undo_coverage(tmp_path, store):
    dd = str(tmp_path)
    suggs = [{"kind":"coverage","title":"Freezer","rationale":"r","config":{"detector":"fridge_temp","entity":"sensor.freezer","max_temp_c":8}}]
    applied = apply_suggestions(suggs, data_dir=dd, store=store, inventory_ids={"sensor.freezer"},
                                current_config=load_policy(dd), create_proposal=lambda c: None, cap=5)
    assert len(applied) == 1
    pol = load_policy(dd)
    assert "sensor.freezer" in pol["detectors"]["fridge_temp"]["entities"]
    assert pol["detectors"]["fridge_temp"]["enabled"] is True
    sid = store.list()[0]["id"]
    assert undo(store, dd, sid) is True
    pol2 = load_policy(dd)
    assert "sensor.freezer" not in pol2["detectors"]["fridge_temp"].get("entities", [])

def test_hostile_config_cannot_wipe_entities_or_disable(tmp_path, store):
    """A brain suggestion is untrusted LLM output. A crafted config that tries
    to smuggle "entities": [] / "enabled": False through params must NOT wipe
    a pre-existing USER entity nor disable the detector -- it may only add the
    brain's own entity alongside what the user already configured."""
    dd = str(tmp_path)
    # Pre-existing USER-configured entity + enabled detector.
    from hiris.app.watcher.policy import save_policy
    save_policy(dd, {"detectors": {"fridge_temp": {"enabled": True, "entities": ["sensor.user_freezer"]}}})

    suggs = [{"kind": "coverage", "title": "Freezer2", "rationale": "r",
              "config": {"detector": "fridge_temp", "entity": "sensor.brain_freezer",
                         "entities": [], "enabled": False}}]
    applied = apply_suggestions(suggs, data_dir=dd, store=store, inventory_ids={"sensor.brain_freezer"},
                                current_config=load_policy(dd), create_proposal=lambda c: None, cap=5)
    assert len(applied) == 1
    pol = load_policy(dd)
    det = pol["detectors"]["fridge_temp"]
    assert det["enabled"] is True
    assert "sensor.user_freezer" in det["entities"]
    assert "sensor.brain_freezer" in det["entities"]

def test_cap_and_management(tmp_path, store):
    proposed = []
    suggs = [{"kind":"management","title":"Auto-off bagno","rationale":"r","config":{"x":1}}]
    apply_suggestions(suggs, data_dir=str(tmp_path), store=store, inventory_ids=set(),
                      current_config=load_policy(str(tmp_path)), create_proposal=lambda c: proposed.append(c), cap=5)
    assert proposed == [{"x": 1}] and store.list()[0]["status"] == "proposed"

def test_undo_no_op_when_entity_not_in_registry(tmp_path, store):
    """Regression test: undo() should only mark dismissed when removal actually
    succeeds. If the entity is not in the brain sidecar registry (e.g., registry/policy
    desync or double-undo), undo() returns False and status stays 'applied'."""
    dd = str(tmp_path)
    # Manually record an "applied" suggestion with a delta pointing to a detector/entity
    # that was NEVER actually registered via apply_brain_detector.
    delta = {"detector": "fridge_temp", "entity": "sensor.ghost"}
    sid = store.record(kind="coverage", title="Ghost Sensor", rationale="r",
                       config={"detector": "fridge_temp", "entity": "sensor.ghost"},
                       status="applied", delta=delta)
    # Attempt undo: should return False (entity not in registry) and NOT mark dismissed.
    result = undo(store, dd, sid)
    assert result is False
    row = store.get(sid)
    assert row["status"] == "applied", "Status should remain 'applied' when undo fails"
