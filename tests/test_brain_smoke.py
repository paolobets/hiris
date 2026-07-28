"""End-to-end smoke test for the brain pipeline (walking skeleton).

Exercises the REAL pipeline: inventory (filter_entities) -> coverage-review
context/message builders -> parse_suggestions (real parser) -> apply_suggestions
(real, writes to policy via watcher.policy) -> undo (real). The ONLY thing
mocked is the LLM reason text itself -- everything downstream of that text
is real production code.
"""
from __future__ import annotations

from hiris.app.api.handlers_entities import filter_entities
from hiris.app.brain.coverage_review import (
    build_review_context,
    build_review_message,
    parse_suggestions,
)
from hiris.app.brain.suggestions import SuggestionStore, apply_suggestions, undo
from hiris.app.watcher.policy import load_policy


def test_brain_pipeline_e2e_inventory_to_undo(tmp_path):
    dd = str(tmp_path)

    # 1) Inventory, built the real way from a minimal entity_cache-like list.
    states = [{"id": "sensor.freezer", "name": "Freezer", "domain": "sensor",
               "device_class": "temperature", "state": "-18"}]
    inventory = filter_entities(states, None, None)
    # Canonical /api/entities shape (SP-4 Fase B Task 1) always includes "state".
    assert inventory == [{"entity_id": "sensor.freezer", "friendly_name": "Freezer",
                           "domain": "sensor", "device_class": "temperature",
                           "state": "-18"}]

    # 2) Coverage-review context/message (real), only the LLM reason is mocked.
    ctx = build_review_context(snapshot={}, inventory=inventory,
                               current_config=load_policy(dd))
    msg = build_review_message(ctx)
    assert "sensor.freezer" in msg

    mocked_reason_text = (
        "Ho analizzato l'inventario.\n"
        "```json\n"
        '{"suggestions":[{"kind":"coverage","title":"Freezer","rationale":"catena del freddo",'
        '"config":{"detector":"fridge_temp","entity":"sensor.freezer","max_temp_c":8}}]}\n'
        "```\n"
    )
    suggs = parse_suggestions(mocked_reason_text)
    assert len(suggs) == 1
    assert suggs[0]["kind"] == "coverage"
    assert suggs[0]["config"]["entity"] == "sensor.freezer"

    # 3) Apply (real): validated coverage suggestion is auto-applied to policy.
    store = SuggestionStore(str(tmp_path / "s.db"))
    try:
        inventory_ids = {e["entity_id"] for e in inventory}
        applied = apply_suggestions(
            suggs, data_dir=dd, store=store, inventory_ids=inventory_ids,
            current_config=load_policy(dd), create_proposal=lambda c: None, cap=5,
        )
        assert len(applied) == 1

        pol = load_policy(dd)
        det = pol["detectors"]["fridge_temp"]
        assert "sensor.freezer" in det["entities"]
        assert det["enabled"] is True

        rows = store.list()
        assert len(rows) == 1
        assert rows[0]["status"] == "applied"

        # 4) Undo (real): removes only the brain-added entity.
        sid = rows[0]["id"]
        assert undo(store, dd, sid) is True

        pol2 = load_policy(dd)
        assert "sensor.freezer" not in pol2["detectors"]["fridge_temp"].get("entities", [])
    finally:
        store.close()
