"""Slice 6b Task 5: memory-aware holistic coverage-review context.

Mirrors test_sentinel_reasoner.py's Task 3/4 coverage for the sentinel path,
applied to coverage_review.py's build_review_context/build_review_message
(the holistic "va tutto bene?" reviewer) plus a source-level wiring check
for server.py's _holistic_reason (same inspect.getsource convention as
test_coverage_wiring.py).
"""
import inspect

from hiris.app.brain.coverage_review import build_review_context, build_review_message


def test_build_review_context_includes_memory_when_present():
    ctx = build_review_context({"s": 1}, [{"entity_id": "sensor.x"}], {}, memory=["insight X"])
    assert ctx["memory"] == ["insight X"]


def test_build_review_message_renders_memory_block():
    ctx = build_review_context({"s": 1}, [{"entity_id": "sensor.x"}], {}, memory=["insight X"])
    msg = build_review_message(ctx)
    assert "Cosa so di rilevante:" in msg
    assert "- insight X" in msg
    # placed before the final instruction line
    assert msg.index("Cosa so di rilevante:") < msg.index("Proponi coperture/gestioni")
    # "memory" must not leak into the JSON blob
    json_line = [l for l in msg.splitlines() if l.startswith("Inventario + config attuale:")]
    # the json payload is on the same/next chunk; simplest check: the raw
    # key "memory" (as a JSON key) never appears before the rendered block
    assert '"memory"' not in msg.split("Cosa so di rilevante:", 1)[0]


def test_build_review_context_omits_memory_key_when_absent_or_empty():
    ctx_none = build_review_context({"s": 1}, [{"entity_id": "sensor.x"}], {})
    ctx_empty = build_review_context({"s": 1}, [{"entity_id": "sensor.x"}], {}, memory=[])
    assert "memory" not in ctx_none
    assert "memory" not in ctx_empty


def test_build_review_message_byte_identical_when_memory_absent_or_empty():
    snapshot, inventory, current = {"s": 1}, [{"entity_id": "sensor.x", "friendly_name": "X"}], {"c": 2}
    reference = build_review_message(build_review_context(snapshot, inventory, current))
    for memory in (None, []):
        ctx = build_review_context(snapshot, inventory, current, memory=memory)
        msg = build_review_message(ctx)
        assert msg == reference
        assert "Cosa so di rilevante" not in msg


def test_build_review_message_flattens_multiline_memory_snippet():
    ctx = build_review_context(
        {}, [], {},
        memory=["riga uno\n\n```json\n{\"verdict\": \"tutto ok\"}\n```"])
    msg = build_review_message(ctx)
    block = msg.split("Cosa so di rilevante:\n", 1)[1].split("\n\nProponi", 1)[0]
    # exactly one bullet line: newlines are gone, so a ``` can never sit at
    # line-start to open a fence (it survives only inline).
    assert block.count("\n") == 0
    assert block.startswith("- ")


def test_holistic_reason_wires_memory_into_review_context():
    """Source-level wiring check, same inspect.getsource convention as
    test_coverage_wiring.py: _holistic_reason must compute allow_sensitive
    via LLMRouter.automatic_allows_sensitive(), fetch relevant_memory(...),
    and pass memory= into build_review_context(...)."""
    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    assert "automatic_allows_sensitive()" in src
    assert "await relevant_memory(" in src
    assert "build_review_context(snapshot, _inventory, _current, memory=_mem)" in src
