# tests/test_sentinel_smoke.py
import pytest
from hiris.app.watcher.guardian import Guardian
from hiris.app.watcher.sentinel_store import SentinelStore
from hiris.app.watcher.reasoner import reason
from hiris.app.watcher.executor import execute

@pytest.mark.asyncio
async def test_battery_anomaly_end_to_end(tmp_path):
    store = SentinelStore(str(tmp_path / "s.db"))
    notified = []
    async def fake_llm(system, user, *, model, max_tokens):
        return '```json\n{"verdict":"anomalia","severity":"info","message":"Batteria all\'8%","action":null}\n```'
    async def notify(message, *, title): notified.append(message)
    async def propose(d, w): raise AssertionError("non deve proporre")

    async def on_wake(wake):
        d = await reason(wake, gather_context=lambda w: {"friendly_name": "Batt"}, llm_reason=fake_llm)
        out = await execute(d, wake, tiers={}, entity_tiers={},
                            notify=notify, propose=propose)
        store.record_event({"ts": 1.0, "kind": wake.signal_kind, "entity_id": wake.entity_id,
                            "verdict": d.verdict, "severity": d.severity, "outcome": out, "message": d.message})

    pol = {"detectors": {"battery": {"enabled": True, "entities": ["sensor.b"], "min_pct": 10}}}
    g = Guardian(store, lambda: pol, on_wake, clock=lambda: 1.0, today=lambda: "2026-07-20")
    await g.on_state_changed({"entity_id": "sensor.b",
                              "old_state": {"state": "50"}, "new_state": {"state": "8"}})
    assert notified == ["Batteria all'8%"]
    assert store.recent_events(1)[0]["outcome"] == "notify"
    store.close()

# fetta E3 Task 4: test_situation_hot_away_end_to_end e test_evening_arrival_
# end_to_end sono usciti insieme al loro soggetto -- guidavano rispettivamente
# `SituationEvaluator` (watcher/evaluator.py + watcher/situations.py) e
# `ArrivalWatcher` (watcher/arrival.py), entrambi cancellati con la ronda:
# nessun successore a cui spostarli, il "verde propone non agisce" che
# verificavano resta comunque coperto da test_battery_anomaly_end_to_end
# sopra (via Guardian/executor, il percorso che sopravvive) e da
# tests/test_sentinel_executor.py per l'executor stesso.
