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

def test_cap_and_management(tmp_path, store):
    proposed = []
    suggs = [{"kind":"management","title":"Auto-off bagno","rationale":"r","config":{"x":1}}]
    apply_suggestions(suggs, data_dir=str(tmp_path), store=store, inventory_ids=set(),
                      current_config=load_policy(str(tmp_path)), create_proposal=lambda c: proposed.append(c), cap=5)
    assert proposed == [{"x": 1}] and store.list()[0]["status"] == "proposed"
