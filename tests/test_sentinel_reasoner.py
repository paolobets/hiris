import pytest
from hiris.app.watcher.signals import WakeEvent, Decision
from hiris.app.watcher.reasoner import parse_decision, build_user_message, reason

def test_parse_decision_reads_json_block():
    txt = 'Ragionamento...\n```json\n{"verdict":"anomalia","severity":"warn","message":"Frigo caldo","action":null}\n```'
    d = parse_decision(txt)
    assert d.verdict == "anomalia" and d.severity == "warn" and d.action is None

def test_parse_decision_fallback_never_crashes():
    d = parse_decision("nessun json qui")
    assert isinstance(d, Decision) and d.verdict == "anomalia"

def test_build_user_message_sanitizes_and_asks_json():
    we = WakeEvent("battery", "sensor.b", "info", {"pct": 8}, 1.0)
    msg = build_user_message(we, {"friendly_name": "Batteria <script>x", "history": []})
    assert "json" in msg.lower()
    assert "<script>" not in msg  # sanitizzato

@pytest.mark.asyncio
async def test_reason_uses_injected_llm():
    we = WakeEvent("battery", "sensor.b", "info", {"pct": 8}, 1.0)
    async def fake_llm(system, user, *, model, max_tokens):
        return '```json\n{"verdict":"anomalia","severity":"info","message":"Batteria al 8%","action":null}\n```'
    d = await reason(we, gather_context=lambda w: {"friendly_name": "Batt"},
                     llm_reason=fake_llm)
    assert d.message == "Batteria al 8%"
