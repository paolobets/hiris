"""TDD for Slice 5b Task 4 -- EVENT-triggered user Agentbots (renamed from
"lens" in SP-4 Fase A Task 3) via the Guardian.

On a `state_changed` for an entity that is the `trigger.entity_id` of an
enabled, event-type user Agentbot, the Guardian must evaluate
`make_generic_detector(agentbot["trigger"])` and, if it fires (honoring the
SAME duration-timer gating as the built-in DETECTORS), call the injected
`run_agentbot(agentbot, evidence)` -- WITHOUT touching the built-in dispatch
at all (regression-tested at the bottom of this file against the exact
scenarios in `test_sentinel_guardian.py`).
"""
import pytest
from hiris.app.watcher.guardian import Guardian
from hiris.app.watcher.sentinel_store import SentinelStore


@pytest.fixture
def store(tmp_path):
    s = SentinelStore(str(tmp_path / "s.db"))
    yield s
    s.close()


# Shape pinned to the REAL contract (see test_sentinel_guardian.py's own
# comment): ha_client.py:490 dispatches state listeners as
# `cb(event["data"])` -- entity_id/old_state/new_state at the top level.
def _evt(eid, old, new):
    return {"entity_id": eid,
            "old_state": {"state": old, "attributes": {}},
            "new_state": {"state": new, "attributes": {}}}


def _empty_policy():
    return {"detectors": {}}


TEMP_LENS = {
    "id": "aaaaaaaaaaaa", "name": "Temp alta", "enabled": True,
    "trigger": {"type": "event", "entity_id": "sensor.temp", "operator": ">", "threshold": 30},
    "reasoning": {"enabled": False},
    "action": {"type": "notify", "message": "troppo caldo"},
    "severity": "warn",
}

DURATION_LENS = {
    "id": "bbbbbbbbbbbb", "name": "Porta aperta a lungo", "enabled": True,
    "trigger": {"type": "event", "entity_id": "binary_sensor.porta",
                "operator": "==", "threshold": "on", "duration_min": 10},
    "reasoning": {"enabled": False},
    "action": {"type": "notify", "message": "porta aperta"},
    "severity": "warn",
}

DISABLED_LENS = {**TEMP_LENS, "id": "cccccccccccc", "enabled": False}

SCHEDULE_LENS = {
    "id": "dddddddddddd", "name": "Non-event", "enabled": True,
    "trigger": {"type": "schedule", "interval_min": 5},
    "reasoning": {"enabled": False},
    "action": {"type": "notify", "message": "x"},
    "severity": "info",
}


class _Recorder:
    def __init__(self):
        self.calls = []

    async def run_agentbot(self, agentbot, evidence):
        self.calls.append((agentbot, evidence))
        return "woke"


# ---------------------------------------------------------------------------
# Core dispatch: above threshold -> run_agentbot invoked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_event_lens_above_threshold_invokes_run_lens(store):
    rec = _Recorder()
    g = Guardian(store, _empty_policy, lambda we: _noop(),
                 clock=lambda: 1000.0, today=lambda: "2026-07-24",
                 get_user_agentbots=lambda: [TEMP_LENS], run_agentbot=rec.run_agentbot)

    await g.on_state_changed(_evt("sensor.temp", "20", "35"))

    assert len(rec.calls) == 1
    agentbot, evidence = rec.calls[0]
    assert agentbot["id"] == "aaaaaaaaaaaa"
    assert evidence["entity_id"] == "sensor.temp"
    assert evidence["value"] == 35.0


# ---------------------------------------------------------------------------
# Below threshold -> no call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_event_lens_below_threshold_does_not_invoke_run_lens(store):
    rec = _Recorder()
    g = Guardian(store, _empty_policy, lambda we: _noop(),
                 clock=lambda: 1000.0, today=lambda: "2026-07-24",
                 get_user_agentbots=lambda: [TEMP_LENS], run_agentbot=rec.run_agentbot)

    await g.on_state_changed(_evt("sensor.temp", "20", "25"))

    assert rec.calls == []


# ---------------------------------------------------------------------------
# Disabled Agentbot -> no call, even if the entity/threshold would otherwise match
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disabled_lens_never_invokes_run_lens(store):
    rec = _Recorder()
    g = Guardian(store, _empty_policy, lambda we: _noop(),
                 clock=lambda: 1000.0, today=lambda: "2026-07-24",
                 get_user_agentbots=lambda: [DISABLED_LENS], run_agentbot=rec.run_agentbot)

    await g.on_state_changed(_evt("sensor.temp", "20", "999"))

    assert rec.calls == []


# ---------------------------------------------------------------------------
# Non-target entity -> no call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_target_entity_does_not_invoke_run_lens(store):
    rec = _Recorder()
    g = Guardian(store, _empty_policy, lambda we: _noop(),
                 clock=lambda: 1000.0, today=lambda: "2026-07-24",
                 get_user_agentbots=lambda: [TEMP_LENS], run_agentbot=rec.run_agentbot)

    await g.on_state_changed(_evt("sensor.other", "20", "999"))

    assert rec.calls == []


# ---------------------------------------------------------------------------
# A schedule-type Agentbot must never be picked up by the event dispatch path
# (defense-in-depth: `get_user_agentbots` is documented to already filter to
# event-type, but the Guardian must not blindly trust that).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_schedule_type_lens_is_ignored_by_event_dispatch(store):
    rec = _Recorder()
    g = Guardian(store, _empty_policy, lambda we: _noop(),
                 clock=lambda: 1000.0, today=lambda: "2026-07-24",
                 get_user_agentbots=lambda: [SCHEDULE_LENS], run_agentbot=rec.run_agentbot)

    await g.on_state_changed(_evt("sensor.whatever", "1", "2"))

    assert rec.calls == []


# ---------------------------------------------------------------------------
# Duration gating: identical semantics to the built-ins (open timer, wait,
# fire only once the threshold_min has elapsed).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_duration_gate_waits_before_invoking_run_lens(store):
    rec = _Recorder()
    t = {"v": 0.0}
    g = Guardian(store, _empty_policy, lambda we: _noop(),
                 clock=lambda: t["v"], today=lambda: "2026-07-24",
                 get_user_agentbots=lambda: [DURATION_LENS], run_agentbot=rec.run_agentbot)

    await g.on_state_changed(_evt("binary_sensor.porta", "off", "on"))  # apre timer
    assert rec.calls == []

    t["v"] = 11 * 60  # oltre i 10 minuti configurati
    await g.on_state_changed(_evt("binary_sensor.porta", "on", "on"))
    assert len(rec.calls) == 1
    assert rec.calls[0][1]["entity_id"] == "binary_sensor.porta"
    assert rec.calls[0][1]["minutes"] >= 10


@pytest.mark.asyncio
async def test_duration_gate_timer_cleared_when_condition_clears(store):
    rec = _Recorder()
    t = {"v": 0.0}
    g = Guardian(store, _empty_policy, lambda we: _noop(),
                 clock=lambda: t["v"], today=lambda: "2026-07-24",
                 get_user_agentbots=lambda: [DURATION_LENS], run_agentbot=rec.run_agentbot)

    await g.on_state_changed(_evt("binary_sensor.porta", "off", "on"))   # apre timer
    assert store.timer_started_at("agentbot:bbbbbbbbbbbb:binary_sensor.porta") == 0.0

    await g.on_state_changed(_evt("binary_sensor.porta", "on", "off"))   # rientra -> detector None
    assert store.timer_started_at("agentbot:bbbbbbbbbbbb:binary_sensor.porta") is None

    t["v"] = 20 * 60
    await g.on_state_changed(_evt("binary_sensor.porta", "off", "on"))   # riparte da capo
    assert rec.calls == []  # timer riaperto ora, non ancora scaduto


# ---------------------------------------------------------------------------
# A broken run_agentbot must not crash the listener, nor block other
# Agentbots in the same dispatch batch.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_lens_exception_is_swallowed_and_other_lenses_still_run(store):
    calls = []

    async def _broken_run_agentbot(agentbot, evidence):
        raise RuntimeError("boom")

    other_lens = {**TEMP_LENS, "id": "eeeeeeeeeeee",
                  "trigger": {"type": "event", "entity_id": "sensor.temp2", "operator": ">", "threshold": 5}}

    async def _dispatch(agentbot, evidence):
        if agentbot["id"] == "aaaaaaaaaaaa":
            raise RuntimeError("boom")
        calls.append((agentbot, evidence))
        return "woke"

    g = Guardian(store, _empty_policy, lambda we: _noop(),
                 clock=lambda: 1000.0, today=lambda: "2026-07-24",
                 get_user_agentbots=lambda: [TEMP_LENS, other_lens], run_agentbot=_dispatch)

    # Two separate events, each matching a different Agentbot; the first
    # Agentbot's run_agentbot raises, but that must not prevent the second
    # event (on a different entity, evaluated in its own call) from working
    # either.
    await g.on_state_changed(_evt("sensor.temp", "0", "999"))   # TEMP_LENS -> raises, swallowed
    await g.on_state_changed(_evt("sensor.temp2", "0", "999"))  # other_lens -> succeeds

    assert calls and calls[0][0]["id"] == "eeeeeeeeeeee"


@pytest.mark.asyncio
async def test_run_lens_exception_within_same_batch_does_not_block_sibling_lens(store):
    """Two Agentbots matching the SAME entity in the SAME dispatch call: the
    first's run_agentbot raising must not stop the second from being
    evaluated and invoked."""
    calls = []

    lens_a = {**TEMP_LENS, "id": "111111111111",
              "trigger": {"type": "event", "entity_id": "sensor.multi", "operator": ">", "threshold": 5}}
    lens_b = {**TEMP_LENS, "id": "222222222222",
              "trigger": {"type": "event", "entity_id": "sensor.multi", "operator": ">", "threshold": 5}}

    async def _dispatch(agentbot, evidence):
        if agentbot["id"] == "111111111111":
            raise RuntimeError("boom")
        calls.append(agentbot["id"])
        return "woke"

    g = Guardian(store, _empty_policy, lambda we: _noop(),
                 clock=lambda: 1000.0, today=lambda: "2026-07-24",
                 get_user_agentbots=lambda: [lens_a, lens_b], run_agentbot=_dispatch)

    await g.on_state_changed(_evt("sensor.multi", "0", "999"))

    assert calls == ["222222222222"]


# ---------------------------------------------------------------------------
# No get_user_agentbots/run_agentbot injected at all (default None) -> no
# crash, behaves exactly like a plain built-in-only Guardian.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_guardian_without_user_lens_wiring_still_works(store):
    g = Guardian(store, _empty_policy, lambda we: _noop(),
                 clock=lambda: 1000.0, today=lambda: "2026-07-24")
    await g.on_state_changed(_evt("sensor.temp", "0", "999"))  # no crash, no-op


async def _noop():
    return None


# ---------------------------------------------------------------------------
# Regression: the built-in DETECTORS dispatch must behave EXACTLY as before,
# even with user-Agentbot wiring present alongside it (mirrors
# test_sentinel_guardian.py's own scenarios, now run with a
# get_user_agentbots/run_agentbot pair also wired in, to prove the two paths
# are independent).
# ---------------------------------------------------------------------------

def _builtin_policy():
    return {"detectors": {
        "battery": {"enabled": True, "entities": ["sensor.batt"], "min_pct": 10},
        "opening": {"enabled": True, "entities": ["binary_sensor.porta"], "open_minutes": 10},
    }}


@pytest.mark.asyncio
async def test_builtin_instant_detector_still_wakes_with_lens_wiring_present(store):
    woke = []
    rec = _Recorder()
    g = Guardian(store, _builtin_policy, lambda we: woke.append(we) or _noop(),
                 clock=lambda: 1000.0, today=lambda: "2026-07-20",
                 get_user_agentbots=lambda: [], run_agentbot=rec.run_agentbot)
    await g.on_state_changed(_evt("sensor.batt", "50", "8"))
    assert len(woke) == 1 and woke[0].signal_kind == "battery"
    assert rec.calls == []  # no user Agentbot matched this entity


@pytest.mark.asyncio
async def test_builtin_duration_detector_still_waits_with_lens_wiring_present(store):
    woke = []
    rec = _Recorder()
    t = {"v": 0.0}
    g = Guardian(store, _builtin_policy, lambda we: woke.append(we) or _noop(),
                 clock=lambda: t["v"], today=lambda: "2026-07-20",
                 get_user_agentbots=lambda: [], run_agentbot=rec.run_agentbot)
    await g.on_state_changed(_evt("binary_sensor.porta", "off", "on"))
    assert woke == []
    t["v"] = 11 * 60
    await g.on_state_changed(_evt("binary_sensor.porta", "on", "on"))
    assert len(woke) == 1 and woke[0].signal_kind == "opening"


@pytest.mark.asyncio
async def test_builtin_and_user_lens_can_both_fire_on_same_event(store):
    """A built-in detector and a user Agentbot both targeting the SAME
    entity must both fire independently -- Task 4 must not short-circuit
    the built-in loop nor vice versa."""
    woke = []
    rec = _Recorder()
    battery_lens = {**TEMP_LENS, "id": "333333333333",
                     "trigger": {"type": "event", "entity_id": "sensor.batt", "operator": "<", "threshold": 10}}
    g = Guardian(store, _builtin_policy, lambda we: woke.append(we) or _noop(),
                 clock=lambda: 1000.0, today=lambda: "2026-07-20",
                 get_user_agentbots=lambda: [battery_lens], run_agentbot=rec.run_agentbot)

    await g.on_state_changed(_evt("sensor.batt", "50", "8"))

    assert len(woke) == 1 and woke[0].signal_kind == "battery"
    assert len(rec.calls) == 1 and rec.calls[0][0]["id"] == "333333333333"
