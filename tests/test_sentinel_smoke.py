# tests/test_sentinel_smoke.py
import pytest
from hiris.app.watcher.guardian import Guardian
from hiris.app.watcher.sentinel_store import SentinelStore
from hiris.app.watcher.reasoner import reason
from hiris.app.watcher.executor import execute
from hiris.app.watcher.signals import Decision

@pytest.mark.asyncio
async def test_battery_anomaly_end_to_end(tmp_path):
    store = SentinelStore(str(tmp_path / "s.db"))
    notified = []
    async def fake_llm(system, user, *, model, max_tokens):
        return '```json\n{"verdict":"anomalia","severity":"info","message":"Batteria all\'8%","action":null}\n```'
    async def notify(message, *, title): notified.append(message)
    async def act(a): raise AssertionError("non deve agire")
    async def propose(d, w): raise AssertionError("non deve proporre")

    async def on_wake(wake):
        d = await reason(wake, gather_context=lambda w: {"friendly_name": "Batt"}, llm_reason=fake_llm)
        out = await execute(d, wake, tiers={}, entity_tiers={},
                            notify=notify, act=act, propose=propose, allow_green_auto=False)
        store.record_event({"ts": 1.0, "kind": wake.signal_kind, "entity_id": wake.entity_id,
                            "verdict": d.verdict, "severity": d.severity, "outcome": out, "message": d.message})

    pol = {"detectors": {"battery": {"enabled": True, "entities": ["sensor.b"], "min_pct": 10}}}
    g = Guardian(store, lambda: pol, on_wake, clock=lambda: 1.0, today=lambda: "2026-07-20")
    await g.on_state_changed({"entity_id": "sensor.b",
                              "old_state": {"state": "50"}, "new_state": {"state": "8"}})
    assert notified == ["Batteria all'8%"]
    assert store.recent_events(1)[0]["outcome"] == "notify"
    store.close()
