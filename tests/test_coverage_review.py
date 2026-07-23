from hiris.app.brain.coverage_review import parse_suggestions, build_review_message, COVERAGE_REVIEW_SYSTEM

def test_parse_suggestions_reads_json():
    t = 'x\n```json\n{"suggestions":[{"kind":"coverage","title":"Freezer","rationale":"r","config":{"detector":"fridge_temp","entity":"sensor.freezer"}}]}\n```'
    s = parse_suggestions(t)
    assert len(s) == 1 and s[0]["kind"] == "coverage" and s[0]["config"]["entity"] == "sensor.freezer"

def test_parse_suggestions_failclosed():
    assert parse_suggestions("nessun json") == []
    assert parse_suggestions('```json\n{"suggestions":"notalist"}\n```') == []

def test_build_review_message_has_context_and_json():
    ctx = {"inventory": [{"entity_id": "sensor.freezer"}], "current": {}}
    m = build_review_message(ctx)
    assert "json" in m.lower() and "sensor.freezer" in m
