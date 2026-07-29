"""Tests for the shared `_run_agentbot` flow (Slice 5b, Task 3; renamed lens
-> Agentbot in SP-4 Fase A Task 3; the module file itself was renamed to
`agentbot_runner.py` in SP-4 Fase B Task 5):
`hiris.app.watcher.agentbot_runner.run_agentbot` + its pure helpers
(`agentbot_action`, `agentbot_message`, `normalize_agentbot_severity`).

`run_agentbot` is the function `server.py`'s `_on_startup` binds onto
`app["run_agentbot"]` (a thin closure over the real sentinel_store/execute/
_run_decision/notify/act/propose adapters) -- it lives in its own module
precisely so it can be exercised here with real collaborators
(`watcher.reasoner.reason`, `watcher.executor.execute`, a real
`SentinelStore`) plus fakes only at the true I/O edges (the LLM call,
notify/act/propose), instead of needing to boot the whole aiohttp app
(`_on_startup` connects to HA, writes ingress config, etc. -- not
practical in a unit test, same reasoning as the existing
`test_sentinel_evaluator.py`/`test_sentinel_executor.py` suites).

SECURITY FOCUS: the executed action must always be the Agentbot's own
deterministic config (`agentbot_action(agentbot)`), never derived from the
LLM's output, even when a malicious/broken LLM fake tries to propose a
different target. See `test_ai_lens_llm_attempts_to_override_action_*`.
"""
import inspect
import logging
import textwrap
from unittest.mock import AsyncMock, MagicMock

import pytest

from hiris.app import server
from hiris.app.task_engine import TaskEngine
from hiris.app.tools.dispatcher import ToolDispatcher
from hiris.app.watcher.agentbots import validate_agentbot
from hiris.app.watcher.executor import execute as real_execute
from hiris.app.watcher.agentbot_runner import (
    agentbot_action,
    agentbot_message,
    normalize_agentbot_severity,
    run_agentbot,
)
from hiris.app.watcher.reasoner import SENTINEL_SYSTEM, reason
from hiris.app.watcher.sentinel_store import SentinelStore


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_normalize_lens_severity_maps_alert_to_critico():
    assert normalize_agentbot_severity("alert") == "critico"


def test_normalize_lens_severity_passes_through_info_and_warn():
    assert normalize_agentbot_severity("info") == "info"
    assert normalize_agentbot_severity("warn") == "warn"


def test_normalize_lens_severity_unknown_defaults_to_info():
    assert normalize_agentbot_severity("bogus") == "info"
    assert normalize_agentbot_severity(None) == "info"
    assert normalize_agentbot_severity(123) == "info"


def test_lens_action_service_type_returns_deterministic_shape():
    lens = {"action": {"type": "service", "domain": "switch", "service": "turn_off",
                        "entity_id": "switch.stufa", "off_after_min": 5, "message": "x"}}
    assert agentbot_action(lens) == {"domain": "switch", "service": "turn_off",
                                      "entity_id": "switch.stufa", "off_after_min": 5}


def test_lens_action_service_type_without_off_after_min_omits_key():
    lens = {"action": {"type": "service", "domain": "light", "service": "turn_on",
                        "entity_id": "light.x"}}
    out = agentbot_action(lens)
    assert out == {"domain": "light", "service": "turn_on", "entity_id": "light.x"}
    assert "off_after_min" not in out


def test_lens_action_notify_type_returns_none():
    lens = {"action": {"type": "notify", "message": "ciao"}}
    assert agentbot_action(lens) is None


def test_lens_action_missing_or_malformed_action_returns_none():
    assert agentbot_action({}) is None
    assert agentbot_action({"action": None}) is None
    assert agentbot_action({"action": {"type": "bogus"}}) is None


def test_lens_message_uses_configured_message():
    lens = {"action": {"type": "notify", "message": "Attenzione: porta aperta"}}
    assert agentbot_message(lens, {"entity_id": "sensor.x"}) == "Attenzione: porta aperta"


def test_lens_message_falls_back_when_no_configured_message():
    lens = {"id": "abc123abc123", "name": "Porta garage", "action": {"type": "notify"}}
    msg = agentbot_message(lens, {"entity_id": "binary_sensor.garage"})
    assert "Porta garage" in msg and "binary_sensor.garage" in msg


def test_lens_message_never_raises_on_empty_input():
    assert agentbot_message({}, {}) != ""


# ---------------------------------------------------------------------------
# Fakes / helpers for the orchestration tests
# ---------------------------------------------------------------------------

class _Rec:
    def __init__(self):
        self.notified = []
        self.acted = []
        self.proposed = []
        self.events = []

    async def notify(self, message, *, title):
        self.notified.append((title, message))

    async def act(self, action):
        self.acted.append(action)

    async def propose(self, decision, wake):
        self.proposed.append(decision)

    def record_event(self, evt):
        self.events.append(evt)


def _policy(tiers=None, entity_tiers=None):
    def _get():
        return {"tiers": tiers or {}, "entity_tiers": entity_tiers or {}}
    return _get


def _make_run_decision_from_llm(llm_reason, *, gather_context=None, notify, act, propose,
                                 execute_policy, allow_green_auto):
    """Test-local stand-in for server.py's real `_run_decision(wake, suggested,
    system, force_notify_only=False, model="auto")` (verified against the
    current `hiris/app/server.py` body, `_run_decision`): calls `reason()`
    (the LLM edge is the only fake), re-injects the deterministic
    `suggested` action onto the parsed Decision (mirroring `_run_decision`'s
    `decision.action = suggested`), then -- if `force_notify_only` -- forces
    the action back to `None` before the executor ever sees it (Task 3
    review fix: a notify-type Agentbot must NEVER actuate, even when
    `suggested` is None and the LLM's own parsed action would otherwise
    survive), then runs the result through the REAL `executor.execute`.
    This is the same "not practical to instantiate the real _on_startup
    closure, so mirror the composed logic against real reason()/execute()"
    approach already used by `tests/test_sentinel_wiring.py`'s
    `_resolve_verdict` mirror.

    Task 4B: `model` is accepted and threaded straight into `reason()`,
    exactly like the real `_run_decision` -- so this mirror still matches
    the production wiring now that `agentbot_runner.py`'s `_on_wake` passes
    `model=reasoning.get("model") or "auto"` into `run_decision`."""
    async def _run_decision(wake, suggested, system, force_notify_only=False, model="auto"):
        decision = await reason(wake, gather_context=gather_context or (lambda w: {}),
                                 llm_reason=llm_reason, system=system, model=model)
        if suggested and getattr(decision, "verdict", "") != "falso_positivo":
            decision.action = suggested
        if force_notify_only:
            decision.action = None
        ep = execute_policy() or {}
        return await real_execute(
            decision, wake,
            tiers=ep.get("tiers") or {}, entity_tiers=ep.get("entity_tiers") or {},
            notify=notify, act=act, propose=propose, allow_green_auto=allow_green_auto)
    return _run_decision


NOTIFY_LENS = {
    "id": "aaaaaaaaaaaa", "name": "Notifica soglia", "enabled": True,
    "trigger": {"type": "event", "entity_id": "sensor.temp", "operator": ">", "threshold": 30},
    "reasoning": {"enabled": False},
    "action": {"type": "notify", "message": "Temperatura troppo alta!"},
    "severity": "warn",
}

SERVICE_LENS = {
    "id": "bbbbbbbbbbbb", "name": "Spegni stufa", "enabled": True,
    "trigger": {"type": "event", "entity_id": "switch.stufa", "operator": ">", "threshold": 3000},
    "reasoning": {"enabled": False},
    "action": {"type": "service", "domain": "switch", "service": "turn_off", "entity_id": "switch.stufa"},
    "severity": "alert",
}

DANGEROUS_LENS = {
    "id": "cccccccccccc", "name": "Apri garage", "enabled": True,
    "trigger": {"type": "event", "entity_id": "sensor.x", "operator": ">", "threshold": 1},
    "reasoning": {"enabled": False},
    "action": {"type": "service", "domain": "cover", "service": "open_cover", "entity_id": "cover.garage"},
    "severity": "alert",
}

AI_SERVICE_LENS = {
    "id": "dddddddddddd", "name": "Agentbot AI", "enabled": True,
    "trigger": {"type": "event", "entity_id": "switch.pompa", "operator": ">", "threshold": 100},
    "reasoning": {"enabled": True, "prompt": "Valuta se la pompa e' davvero in anomalia."},
    "action": {"type": "service", "domain": "switch", "service": "turn_off", "entity_id": "switch.pompa"},
    "severity": "warn",
}


@pytest.fixture
def store(tmp_path):
    s = SentinelStore(str(tmp_path / "s.db"))
    yield s
    s.close()


# ---------------------------------------------------------------------------
# (a) zero-AI Agentbot, notify action -> executor called with Decision(action=None)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_zero_ai_notify_lens_calls_executor_notify_path(store):
    rec = _Rec()

    async def _run_decision_unused(wake, suggested, system):
        raise AssertionError("reasoning disabled -- run_decision must not be called")

    outcome = await run_agentbot(
        NOTIFY_LENS, {"entity_id": "sensor.temp", "value": 35},
        store=store, run_decision=_run_decision_unused, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert outcome == "woke"
    assert rec.notified and rec.notified[0][1] == "Temperatura troppo alta!"
    assert not rec.acted
    assert rec.events and rec.events[0]["outcome"] == "notify"
    assert rec.events[0]["kind"] == "agentbot:aaaaaaaaaaaa"


# ---------------------------------------------------------------------------
# (b) zero-AI Agentbot, service action, green tier + opt-in -> executor acts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_zero_ai_service_lens_green_tier_acts(store):
    rec = _Rec()

    async def _run_decision_unused(wake, suggested, system):
        raise AssertionError("reasoning disabled -- run_decision must not be called")

    outcome = await run_agentbot(
        SERVICE_LENS, {"entity_id": "switch.stufa", "value": 3500},
        store=store, run_decision=_run_decision_unused, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(tiers={"switch": "green"}), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert outcome == "woke"
    assert rec.acted == [{"domain": "switch", "service": "turn_off", "entity_id": "switch.stufa"}]
    assert rec.events[0]["outcome"] == "act"
    # severity "alert" (SERVICE_LENS) must have been normalized to "critico"
    assert rec.events[0]["severity"] == "critico"


# ---------------------------------------------------------------------------
# (c) dangerous domain -> denylist blocks regardless of tier/opt-in (only alert)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dangerous_domain_service_lens_only_alerts(store):
    rec = _Rec()

    async def _run_decision_unused(wake, suggested, system):
        raise AssertionError("reasoning disabled -- run_decision must not be called")

    outcome = await run_agentbot(
        DANGEROUS_LENS, {"entity_id": "sensor.x", "value": 2},
        store=store, run_decision=_run_decision_unused, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(tiers={"cover": "green"}), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert outcome == "woke"
    assert rec.events[0]["outcome"] == "alert"
    assert not rec.acted
    assert not rec.proposed
    assert rec.notified  # alert = notify with the Agentbot's message


# ---------------------------------------------------------------------------
# (d) AI-enabled Agentbot: reasoner invoked with the custom prompt appended
#     to SENTINEL_SYSTEM; a malicious LLM fake tries to redirect the action
#     -> ignored, the executed action is still the Agentbot's config action.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ai_lens_system_contains_custom_prompt(store):
    rec = _Rec()
    seen_systems = []

    async def _llm_reason(system, user, *, model, max_tokens):
        seen_systems.append(system)
        return '```json\n{"verdict":"anomalia","severity":"warn","message":"ok","action":null}\n```'

    run_decision = _make_run_decision_from_llm(
        _llm_reason, notify=rec.notify, act=rec.act, propose=rec.propose,
        execute_policy=_policy(tiers={"switch": "green"}), allow_green_auto=True)

    await run_agentbot(
        AI_SERVICE_LENS, {"entity_id": "switch.pompa", "value": 150},
        store=store, run_decision=run_decision, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(tiers={"switch": "green"}), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert seen_systems, "reasoner must have been invoked"
    assert seen_systems[0].startswith(SENTINEL_SYSTEM)
    assert "Valuta se la pompa" in seen_systems[0]


@pytest.mark.asyncio
async def test_ai_lens_llm_attempts_to_override_action_is_ignored(store):
    """The malicious action deliberately targets a SAFE (non-dangerous)
    domain with its OWN tier=green, distinct from the Agentbot's real
    `switch.pompa` target. This makes the test actually discriminating: if
    `run_agentbot` failed to pass the Agentbot's deterministic `suggested`
    action into `run_decision`, the LLM's `light.malicious_target` action
    would sail through the (non-dangerous) tier gate and `act` would be
    called with it -- unlike a dangerous-domain target, which the
    executor's denylist would block regardless of whether the override
    happened, making that variant non-discriminating for this specific
    guarantee."""
    rec = _Rec()

    async def _malicious_llm_reason(system, user, *, model, max_tokens):
        return (
            '```json\n{"verdict":"anomalia","severity":"warn","message":"redirect",'
            '"action":{"domain":"light","service":"turn_on","entity_id":"light.malicious_target"}}'
            '\n```'
        )

    tiers = {"switch": "green", "light": "green"}
    run_decision = _make_run_decision_from_llm(
        _malicious_llm_reason, notify=rec.notify, act=rec.act, propose=rec.propose,
        execute_policy=_policy(tiers=tiers), allow_green_auto=True)

    await run_agentbot(
        AI_SERVICE_LENS, {"entity_id": "switch.pompa", "value": 150},
        store=store, run_decision=run_decision, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(tiers=tiers), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    # The executed action must be the AGENTBOT's config action, never the LLM's.
    assert rec.acted == [{"domain": "switch", "service": "turn_off", "entity_id": "switch.pompa"}]
    assert not any(a.get("domain") == "light" for a in rec.acted)


@pytest.mark.asyncio
async def test_ai_lens_notify_only_llm_attempts_dangerous_action_still_denied(store):
    """Even in the one case where `agentbot_action` legitimately returns
    None (a `notify`-type Agentbot) and the LLM's own proposed action
    therefore isn't overridden by a `suggested` value, the real
    `executor.execute`'s dangerous-domain denylist is still the final
    backstop: a lock/alarm/cover/siren/garage target from the LLM is still
    never acted upon."""
    rec = _Rec()
    notify_lens_ai = {**NOTIFY_LENS, "reasoning": {"enabled": True, "prompt": "Sii prudente."}}

    async def _malicious_llm_reason(system, user, *, model, max_tokens):
        return (
            '```json\n{"verdict":"anomalia","severity":"critico","message":"apro",'
            '"action":{"domain":"lock","service":"unlock","entity_id":"lock.porta_blindata"}}'
            '\n```'
        )

    run_decision = _make_run_decision_from_llm(
        _malicious_llm_reason, notify=rec.notify, act=rec.act, propose=rec.propose,
        execute_policy=_policy(tiers={"lock": "green"}), allow_green_auto=True)

    await run_agentbot(
        notify_lens_ai, {"entity_id": "sensor.temp", "value": 35},
        store=store, run_decision=run_decision, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(tiers={"lock": "green"}), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert not rec.acted  # dangerous domain denylist still blocks it


@pytest.mark.asyncio
async def test_ai_notify_lens_never_actuates_even_on_safe_green_domain(store):
    """Task 3 review fix: for a `notify`-type Agentbot, `agentbot_action`
    legitimately returns `None`, so the reasoning path's `if suggested and
    ...` guard never re-injects a deterministic action. Without
    `force_notify_only`, that leaves the LLM's OWN parsed `action` sitting
    on the Decision, and on a SAFE (non-dangerous) domain with a green tier
    + `allow_green_auto`, `executor.execute` would actuate it -- even
    though the user explicitly configured this Agentbot as "just notify".
    Unlike
    `test_ai_lens_notify_only_llm_attempts_dangerous_action_still_denied`
    (which uses a dangerous `lock` domain, so the denylist alone would save
    it regardless of this fix), this test uses `light` -- a safe domain --
    so only `force_notify_only` forcing `decision.action = None` before
    `execute()` runs can prevent the actuation."""
    rec = _Rec()
    notify_lens_ai = {**NOTIFY_LENS, "reasoning": {"enabled": True, "prompt": "Sii prudente."}}

    async def _llm_proposes_safe_action(system, user, *, model, max_tokens):
        return (
            '```json\n{"verdict":"anomalia","severity":"warn","message":"agisco",'
            '"action":{"domain":"light","service":"turn_on","entity_id":"light.malicious_target"}}'
            '\n```'
        )

    run_decision = _make_run_decision_from_llm(
        _llm_proposes_safe_action, notify=rec.notify, act=rec.act, propose=rec.propose,
        execute_policy=_policy(tiers={"light": "green"}), allow_green_auto=True)

    outcome = await run_agentbot(
        notify_lens_ai, {"entity_id": "sensor.temp", "value": 35},
        store=store, run_decision=run_decision, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(tiers={"light": "green"}), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert outcome == "woke"
    assert not rec.acted  # notify Agentbot must NEVER actuate, safe domain or not
    assert rec.notified  # the AI verdict/message still reaches the user


# ---------------------------------------------------------------------------
# (e) cooldown / cap gating (reuse of wake.maybe_wake, same as the built-ins)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cooldown_blocks_second_fire_within_window(store):
    rec = _Rec()
    calls = []

    async def _run_decision_unused(wake, suggested, system):
        raise AssertionError("reasoning disabled")

    async def _run(clock_val):
        return await run_agentbot(
            NOTIFY_LENS, {"entity_id": "sensor.temp"},
            store=store, run_decision=_run_decision_unused, execute=real_execute,
            notify=rec.notify, act=rec.act, propose=rec.propose,
            get_execute_policy=_policy(), allow_green_auto=True,
            record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
            clock=lambda: clock_val, today=lambda: "2026-07-24",
            cooldown_sec=1800,
        )

    out1 = await _run(1000.0)
    out2 = await _run(1100.0)  # 100s later, well within 1800s cooldown

    assert out1 == "woke"
    assert out2 == "cooldown"
    assert len(rec.notified) == 1  # second fire never reached the executor


@pytest.mark.asyncio
async def test_key_scopes_cooldown_per_lens_and_entity(store):
    """An Agentbot firing on two different entities in the same evaluation
    batch (e.g. an event trigger matched via different evidence) must not
    share a single cooldown slot -- `key` includes the evidence's
    entity_id."""
    rec = _Rec()

    async def _run_decision_unused(wake, suggested, system):
        raise AssertionError("reasoning disabled")

    out_a = await run_agentbot(
        NOTIFY_LENS, {"entity_id": "sensor.temp_a"},
        store=store, run_decision=_run_decision_unused, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )
    out_b = await run_agentbot(
        NOTIFY_LENS, {"entity_id": "sensor.temp_b"},
        store=store, run_decision=_run_decision_unused, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert out_a == "woke" and out_b == "woke"
    assert len(rec.notified) == 2


# ---------------------------------------------------------------------------
# (f) Task 5 review Fix 2: a SCHEDULED Agentbot's own interval/cron cadence
# IS its rate limiter -- passing cooldown_sec=0 must bypass the cooldown
# gate entirely, while daily_cap (an unrelated, unchanged safety net) still
# applies. Event Agentbots (which never pass cooldown_sec) must keep the
# default ~30-min cooldown -- verified by OMITTING the kwarg entirely,
# not just passing 1800 explicitly (regression against Fix 2's new
# `cooldown_sec: int | None = None` default).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cooldown_sec_zero_bypasses_cooldown_but_daily_cap_still_applies(store):
    rec = _Rec()

    async def _run_decision_unused(wake, suggested, system):
        raise AssertionError("reasoning disabled")

    async def _run(clock_val):
        return await run_agentbot(
            NOTIFY_LENS, {"entity_id": "sensor.temp"},
            store=store, run_decision=_run_decision_unused, execute=real_execute,
            notify=rec.notify, act=rec.act, propose=rec.propose,
            get_execute_policy=_policy(), allow_green_auto=True,
            record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
            clock=lambda: clock_val, today=lambda: "2026-07-24",
            cooldown_sec=0, daily_cap=2,
        )

    out1 = await _run(1000.0)
    out2 = await _run(1000.5)  # immediately after -- would be "cooldown" at the default 1800s
    out3 = await _run(1001.0)  # third fire -- beyond daily_cap=2

    assert out1 == "woke"
    assert out2 == "woke"   # cooldown bypassed
    assert out3 == "cap"    # daily_cap still enforced
    assert len(rec.notified) == 2


@pytest.mark.asyncio
async def test_omitted_cooldown_sec_still_defaults_to_thirty_minutes(store):
    rec = _Rec()

    async def _run_decision_unused(wake, suggested, system):
        raise AssertionError("reasoning disabled")

    async def _run(clock_val):
        return await run_agentbot(
            NOTIFY_LENS, {"entity_id": "sensor.temp"},
            store=store, run_decision=_run_decision_unused, execute=real_execute,
            notify=rec.notify, act=rec.act, propose=rec.propose,
            get_execute_policy=_policy(), allow_green_auto=True,
            record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
            clock=lambda: clock_val, today=lambda: "2026-07-24",
            # cooldown_sec intentionally omitted -- must resolve to the
            # same default (~1800s) as before Fix 2, for EVENT Agentbots.
        )

    out1 = await _run(1000.0)
    out2 = await _run(1100.0)  # 100s later, well within the default 1800s cooldown

    assert out1 == "woke"
    assert out2 == "cooldown"
    assert len(rec.notified) == 1


# ---------------------------------------------------------------------------
# (g) Task 4B: `reasoning.model` (per-Agentbot model) must reach
# `run_decision`'s `model` kwarg unchanged -- this is the actual runtime
# threading point (server.py's `_run_decision` has no `agentbot` in scope;
# the Agentbot's `reasoning` dict is only in scope HERE, in `_on_wake`).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ai_lens_threads_its_own_reasoning_model_into_run_decision(store):
    rec = _Rec()
    seen = {}

    async def _run_decision_spy(wake, suggested, system, force_notify_only=False, model="auto"):
        seen["model"] = model
        return None

    lens_with_model = {**AI_SERVICE_LENS,
                        "reasoning": {"enabled": True, "prompt": "x", "model": "gpt-4o"}}

    await run_agentbot(
        lens_with_model, {"entity_id": "switch.pompa", "value": 150},
        store=store, run_decision=_run_decision_spy, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(tiers={"switch": "green"}), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert seen["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_ai_lens_without_configured_model_defaults_to_auto(store):
    rec = _Rec()
    seen = {}

    async def _run_decision_spy(wake, suggested, system, force_notify_only=False, model="auto"):
        seen["model"] = model
        return None

    # AI_SERVICE_LENS's reasoning dict has no "model" key at all.
    await run_agentbot(
        AI_SERVICE_LENS, {"entity_id": "switch.pompa", "value": 150},
        store=store, run_decision=_run_decision_spy, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(tiers={"switch": "green"}), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert seen["model"] == "auto"


# ---------------------------------------------------------------------------
# (h) Fase 1 fix-wave CRITICAL: an Agentbot whose `action` is legitimately
# `None` (mode="objective") must ALSO get `force_notify_only=True` -- not
# just a `"notify"`-type rule. Before the fix, `_on_wake` computed
# `action_type = (agentbot.get("action") or {}).get("type")` and only forced
# notify-only when that was the STRING "notify"; for `action=None` it was
# `None`, so BOTH guards in server.py's `_run_decision` failed to fire
# (`suggested` is also None) and the LLM's own emitted action would survive
# onto the Decision and reach the executor.
# ---------------------------------------------------------------------------

OBJECTIVE_LENS = {
    "id": "eeeeeeeeeeee", "name": "Obiettivo pompa", "enabled": True,
    "mode": "objective", "objective": "Mantieni la pompa in sicurezza",
    "trigger": {"type": "schedule", "interval_min": 30},
    "reasoning": {"enabled": True, "prompt": "Valuta la situazione ed agisci se necessario."},
    "action": None,
    "severity": "warn",
}


@pytest.mark.asyncio
async def test_objective_lens_action_none_forces_notify_only_true(store):
    """Direct assertion on what `_on_wake` threads into `run_decision`: for
    `action=None` (mode="objective"), `force_notify_only` must be True and
    `suggested` must be None -- RED before the fix (`force_notify_only` was
    False because `action_type` was `None`, not the string `"notify"`)."""
    rec = _Rec()
    seen = {}

    async def _run_decision_spy(wake, suggested, system, force_notify_only=False, model="auto"):
        seen["force_notify_only"] = force_notify_only
        seen["suggested"] = suggested
        return None

    await run_agentbot(
        OBJECTIVE_LENS, {"entity_id": "switch.pompa", "value": 150},
        store=store, run_decision=_run_decision_spy, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(tiers={"switch": "green"}), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert seen["suggested"] is None
    assert seen["force_notify_only"] is True


@pytest.mark.asyncio
async def test_objective_lens_llm_emitted_action_never_reaches_executor(store):
    """End-to-end: an objective Agentbot (action=None) whose LLM response
    fabricates a service action on a SAFE (non-dangerous) green-tier domain
    must NEVER actuate it -- only `force_notify_only` forcing
    `decision.action = None` before `execute()` runs can prevent this,
    since `suggested` (from `agentbot_action`) is also None here so the
    OTHER guard (`if suggested and ...`) never fires either. RED before the
    fix: `rec.acted` would contain the LLM's fabricated action."""
    rec = _Rec()

    async def _llm_invents_an_action(system, user, *, model, max_tokens):
        return (
            '```json\n{"verdict":"anomalia","severity":"warn","message":"agisco",'
            '"action":{"domain":"light","service":"turn_on","entity_id":"light.malicious_target"}}'
            '\n```'
        )

    run_decision = _make_run_decision_from_llm(
        _llm_invents_an_action, notify=rec.notify, act=rec.act, propose=rec.propose,
        execute_policy=_policy(tiers={"light": "green"}), allow_green_auto=True)

    await run_agentbot(
        OBJECTIVE_LENS, {"entity_id": "switch.pompa", "value": 150},
        store=store, run_decision=run_decision, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(tiers={"light": "green"}), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert not rec.acted  # the LLM-invented action must never reach the executor
    assert rec.notified   # the AI verdict/message still reaches the user


@pytest.mark.asyncio
async def test_ai_lens_two_agentbots_use_independent_models(store):
    """Two Agentbots firing on their own entities must each reason with
    THEIR OWN configured model -- one Agentbot's choice must never leak
    into another's `reason()` call."""
    rec = _Rec()
    seen = []

    async def _run_decision_spy(wake, suggested, system, force_notify_only=False, model="auto"):
        seen.append(model)
        return None

    lens_a = {**AI_SERVICE_LENS, "id": "aaaaaaaaaaaa",
              "reasoning": {"enabled": True, "model": "claude-3-5-haiku"}}
    lens_b = {**AI_SERVICE_LENS, "id": "bbbbbbbbbbbb",
              "trigger": {**AI_SERVICE_LENS["trigger"], "entity_id": "switch.pompa2"},
              "reasoning": {"enabled": True, "model": "gpt-4o-mini"}}

    await run_agentbot(
        lens_a, {"entity_id": "switch.pompa", "value": 150},
        store=store, run_decision=_run_decision_spy, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(tiers={"switch": "green"}), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )
    await run_agentbot(
        lens_b, {"entity_id": "switch.pompa2", "value": 150},
        store=store, run_decision=_run_decision_spy, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(tiers={"switch": "green"}), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert seen == ["claude-3-5-haiku", "gpt-4o-mini"]


# ---------------------------------------------------------------------------
# (g) Agenti v1.1 Fase 2 Task 3: i Task emessi dal ragionatore di un agente
#     ereditano la sua IDENTITA' e il suo PERIMETRO.
#
# Questo e' l'unico test del file che percorre la catena intera fino al
# TaskEngine, quindi usa collaboratori reali fin dove e' possibile:
#   - `_llm_reason` e `_run_decision` NON sono mirror scritti a mano ma le
#     closure VERE estratte da `server._on_startup` con `inspect.getsource`
#     (stessa tecnica di `tests/test_reasoning_sweep_chat_skip.py`), cosi'
#     un drift della propagazione lato server fa fallire QUESTO test invece
#     di essere assorbito da una copia;
#   - `ToolDispatcher`, `create_task_tool`, `TaskEngine` e
#     `executor.execute` sono i moduli reali;
#   - l'unico finto e' il bordo di I/O vero (la chiamata all'LLM).
# ---------------------------------------------------------------------------

OBJECTIVE_AGENTBOT_RAW = {
    "id": "eeeeeeeeeeee",
    "name": "Custode cucina",
    "enabled": True,
    "mode": "objective",
    "objective": "Tieni sotto controllo i consumi della cucina.",
    "trigger": {"type": "schedule", "interval_min": 60},
    "reasoning": {"enabled": True, "prompt": "Ragiona e pianifica se serve."},
    "severity": "warn",
    "perimeter": {"allowed_entities": ["light.cucina"], "allowed_services": ["light.*"]},
}

# Il task che l'LLM prova a creare punta a light.salotto: FUORI dal perimetro
# dell'agente, ma su un dominio SICURO con tier verde -- cosi' il semaforo
# (denylist + tier gate) lo lascerebbe passare e l'unico motivo possibile del
# rifiuto e' il perimetro ereditato dal Task.
_OUT_OF_PERIMETER_TASK_INPUTS = {
    "label": "Spegni il salotto",
    "trigger": {"type": "delay", "minutes": 10},
    "actions": [{
        "type": "call_ha_service", "domain": "light", "service": "turn_off",
        "data": {"entity_id": "light.salotto"},
    }],
}


class _FakeReasoningRunner:
    """Sta al posto di `app["llm_router"]` all'UNICO bordo di I/O reale (la
    chiamata all'LLM). Riproduce cio' che `ClaudeRunner.run_with_actions` ->
    `chat()` gia' fa quando il modello emette un blocco `tool_use`
    (claude_runner.py, ramo `stop_reason == "tool_use"`): inoltra
    `allowed_entities`/`allowed_services`/`chatbot_id` verbatim al VERO
    `ToolDispatcher`. Quel forwarding e' wiring preesistente e non toccato da
    questo task; tutto cio' che sta a valle (dispatcher -> task_tools ->
    TaskEngine) e' reale."""

    def __init__(self, dispatcher, tool_call):
        self._dispatcher = dispatcher
        self._tool_call = tool_call
        self.seen_kwargs = []

    async def run_with_actions(self, **kwargs):
        self.seen_kwargs.append(kwargs)
        name, inputs = self._tool_call
        await self._dispatcher.dispatch(
            name, inputs,
            allowed_entities=kwargs.get("allowed_entities"),
            allowed_services=kwargs.get("allowed_services"),
            allowed_endpoints=kwargs.get("allowed_endpoints"),
            chatbot_id=kwargs.get("chatbot_id"),
        )
        return (
            '```json\n{"verdict":"anomalia","severity":"warn",'
            '"message":"ho pianificato un task","action":null}\n```',
            {},
        )


def _extract_closure(src: str, start_marker: str, end_marker: str) -> str:
    """Ritaglia una closure da `src` fra due marker testuali.

    `str.index` alza gia' ValueError se un marker sparisce del tutto, ma NON
    protegge dal caso insidioso: un marker ancora presente che pero' delimita
    una fetta DIVERSA (riformattazione, una closure spostata, un secondo
    `return out or ""` comparso prima di quello giusto). In quel caso
    l'estrazione riuscirebbe in silenzio e i test girerebbero su codice non
    piu' rappresentativo, continuando a passare. Da qui gli assert
    sull'unicita' dei marker e sull'ordine: meglio un fallimento rumoroso di
    un verde che non dimostra nulla (review, minor #5)."""
    assert src.count(start_marker) == 1, (
        f"marker di inizio {start_marker!r} trovato "
        f"{src.count(start_marker)} volte in server._on_startup: "
        "l'estrazione non e' piu' univoca")
    start = src.index(start_marker)
    assert end_marker in src[start:], (
        f"marker di fine {end_marker!r} non trovato DOPO {start_marker!r}: "
        "la closure e' stata riformattata o spostata")
    end = src.index(end_marker, start) + len(end_marker)
    return textwrap.dedent(src[start:end])


def _load_real_server_run_decision(*, app, gather_context, execute, notify, act, propose,
                                   record_situation_event):
    """Carica le closure REALI `_llm_reason` + `_run_decision` da
    `server._on_startup`, legandole a doppi di test per le sole variabili
    libere che non sono simboli importabili (`app`, `_gather_context`,
    `_notify`/`_act`/`_propose`, `_record_situation_event`). Tutto il resto
    (`reason`, `execute`, `env_bool`, `RunnerBackendError`, `logger`) e' un
    simbolo reale, quindi il legame e' esatto e non una supposizione."""
    from hiris.app.claude_runner import RunnerBackendError

    src = inspect.getsource(server._on_startup)
    namespace = {
        "app": app,
        "logger": logging.getLogger("test_run_agentbot_perimeter"),
        "RunnerBackendError": RunnerBackendError,
        "reason": reason,
        "execute": execute,
        "env_bool": server.env_bool,
        "_gather_context": gather_context,
        "_notify": notify,
        "_act": act,
        "_propose": propose,
        "_record_situation_event": record_situation_event,
    }
    # Ogni closure porta con se' i frammenti che DEVONO comparire nella fetta
    # estratta. Sono precisamente i kwarg che questo task propaga: se la
    # propagazione viene rimossa o rinominata a monte, l'estrazione non deve
    # restituire in silenzio una fetta che "compila comunque" -- deve
    # fallire qui, prima che i test a valle costruiscano certezze su codice
    # che non e' piu' quello di produzione (review, minor #5).
    expected_fragments = {
        "_llm_reason": (
            "async def _llm_reason(system, user, *, model, max_tokens,",
            "agent_id=None, allowed_entities=None, allowed_services=None)",
            "chatbot_id=agent_id,",
            "allowed_entities=allowed_entities, allowed_services=allowed_services",
        ),
        "_run_decision": (
            "async def _run_decision(",
            "agent_id=None, perimeter=None",
            'perimeter.get("allowed_entities")',
            'perimeter.get("allowed_services")',
            "allowed_entities=_allowed_entities",
            "allowed_services=_allowed_services",
        ),
    }
    for marker_start, marker_end, label in (
        ("    async def _llm_reason(", '        return out or ""', "_llm_reason"),
        ("    async def _run_decision(",
         "        await _record_situation_event(wake.signal_kind, wake.entity_id, decision, outcome)",
         "_run_decision"),
    ):
        func_src = _extract_closure(src, marker_start, marker_end)
        for fragment in expected_fragments[label]:
            assert fragment in func_src, (
                f"la closure {label} estratta da server.py non contiene piu' "
                f"{fragment!r}: o la firma/propagazione e' cambiata, o "
                "_extract_closure sta ritagliando la fetta sbagliata. In "
                "entrambi i casi i test sottostanti non provano piu' cio' "
                "che dicono di provare.")
        exec(compile(func_src, f"<{label} extracted from server.py>", "exec"), namespace)
    return namespace["_run_decision"]


def _perimeter_chain(tmp_path, perimeter_raw):
    """Costruisce dispatcher+TaskEngine reali e l'agentbot objective validato
    dal VERO `validate_agentbot`, cosi' il blocco `perimeter` ha esattamente
    la forma che il validatore materializza in produzione."""
    agentbot = validate_agentbot({**OBJECTIVE_AGENTBOT_RAW, "perimeter": perimeter_raw})
    assert agentbot is not None, "l'agentbot objective di prova deve essere valido"

    ha = AsyncMock()
    ha.call_service = AsyncMock(return_value=True)
    cache = MagicMock()
    cache.get_state = MagicMock(return_value={"state": "on"})
    execute_policy = {"tiers": {"light": "green"}, "entity_tiers": {}}

    task_engine = TaskEngine(
        ha_client=ha, entity_cache=cache, notify_config={},
        data_path=str(tmp_path / "tasks.json"), execute_policy=execute_policy)
    task_engine._scheduler = MagicMock()  # niente scheduling reale

    dispatcher = ToolDispatcher(
        ha_client=ha, notify_config={}, entity_cache=cache, execute_policy=execute_policy)
    dispatcher.set_task_engine(task_engine)

    runner = _FakeReasoningRunner(dispatcher, ("create_task", _OUT_OF_PERIMETER_TASK_INPUTS))
    return agentbot, ha, execute_policy, task_engine, runner


async def _fire_objective_agentbot(agentbot, *, store, execute_policy, runner, rec):
    async def _gather_context(wake):
        return {}

    async def _record_situation_event(kind, entity_id, decision, outcome):
        return None

    run_decision = _load_real_server_run_decision(
        app={"llm_router": runner, "execute_policy": execute_policy},
        gather_context=_gather_context, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        record_situation_event=_record_situation_event)

    return await run_agentbot(
        agentbot, {"entity_id": "light.cucina", "value": 1},
        store=store, run_decision=run_decision, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=lambda: execute_policy, allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-29",
    )


@pytest.mark.asyncio
async def test_task_emitted_by_an_agent_inherits_its_identity_and_perimeter(store, tmp_path):
    """Oggi il task nasce come 'hiris-default' e senza perimetro: puo' agire
    su entita' fuori dall'ambito dell'agente che lo ha creato."""
    agentbot, ha, execute_policy, task_engine, runner = _perimeter_chain(
        tmp_path, {"allowed_entities": ["light.cucina"], "allowed_services": ["light.*"]})
    rec = _Rec()

    outcome = await _fire_objective_agentbot(
        agentbot, store=store, execute_policy=execute_policy, runner=runner, rec=rec)
    assert outcome == "woke"

    # (a) il task NASCE attribuito all'agente e confinato dal suo perimetro
    tasks = list(task_engine._tasks.values())
    assert len(tasks) == 1
    task = tasks[0]
    assert task.agent_id == "eeeeeeeeeeee", "il task deve essere attribuito all'agente che lo ha creato"
    assert task.allowed_entities == ["light.cucina"]
    assert task.allowed_services == ["light.*"]

    # (b) alla sua ESECUZIONE l'azione su light.salotto e' RIFIUTATA --
    # dall'enforcement gia' esistente in task_engine._run_action, non da un
    # controllo nuovo: il semaforo (light -> green) l'avrebbe lasciata passare.
    ha.call_service.reset_mock()
    await task_engine._execute_task(task.id)
    assert ha.call_service.await_count == 0, "l'azione fuori perimetro non deve raggiungere HA"
    assert "light.salotto" in (task.result or "")
    assert "not permitted by policy" in (task.result or "")

    # ...e identita' + perimetro erano gia' visibili all'anello precedente,
    # la chiamata all'LLM: e' li' che il ragionatore smette di essere anonimo
    # e senza confini.
    assert len(runner.seen_kwargs) == 1
    assert runner.seen_kwargs[0]["chatbot_id"] == "eeeeeeeeeeee"
    assert runner.seen_kwargs[0]["allowed_entities"] == ["light.cucina"]
    assert runner.seen_kwargs[0]["allowed_services"] == ["light.*"]


@pytest.mark.asyncio
async def test_task_from_agent_with_explicitly_empty_perimeter_is_fail_closed(store, tmp_path):
    """Una allow-list ESPLICITAMENTE vuota (`"allowed_entities": []`) e' una
    decisione dell'utente -- "non concedo nulla" -- e va propagata com'e' fino
    in fondo, senza mai essere allargata a `None`. `task_engine._run_action`
    ha sempre distinto `None` ("nessun confine") da `[]` ("nessuna entita'
    concessa"); da questo fix il dispatcher legge `[]` allo stesso modo, cosi'
    lo stesso valore non significa piu' cose opposte ai due capi della catena.

    Sorella di `test_task_from_agent_without_declared_perimeter_is_unconfined`:
    insieme inchiodano i due lati della distinzione lungo la catena REALE
    (server._run_decision -> runner -> dispatcher -> Task -> TaskEngine)."""
    # `allowed_services` concede il servizio, cosi' il task SUPERA il controllo
    # alla creazione e si arriva davvero a misurare l'effetto di
    # `allowed_entities: []` all'ESECUZIONE. (Con anche i servizi a `[]` il
    # task verrebbe rifiutato prima, vedi il test successivo.)
    agentbot, ha, execute_policy, task_engine, runner = _perimeter_chain(
        tmp_path, {"allowed_entities": [], "allowed_services": ["light.*"]})
    assert agentbot["perimeter"]["allowed_entities"] == []
    rec = _Rec()

    await _fire_objective_agentbot(
        agentbot, store=store, execute_policy=execute_policy, runner=runner, rec=rec)

    # La lista vuota arriva VERBATIM fino al ragionatore: non e' stata
    # normalizzata a None da nessun anello intermedio.
    assert runner.seen_kwargs[0]["allowed_entities"] == []
    assert runner.seen_kwargs[0]["allowed_services"] == ["light.*"]

    task = next(iter(task_engine._tasks.values()))
    assert task.agent_id == "eeeeeeeeeeee"
    assert task.allowed_entities == []
    assert task.allowed_services == ["light.*"]

    ha.call_service.reset_mock()
    await task_engine._execute_task(task.id)
    assert ha.call_service.await_count == 0
    assert "not permitted by policy" in (task.result or "")


@pytest.mark.asyncio
async def test_task_with_empty_service_perimeter_is_refused_at_creation(store, tmp_path):
    """L'altro effetto di `[]` = "nessuna concessione": il ramo `create_task`
    del dispatcher controlla il SERVIZIO gia' alla creazione, quindi con
    `allowed_services: []` il task non nasce nemmeno e l'LLM riceve un errore
    esplicito invece di un "task creato" che sarebbe poi rimasto inerte.

    Nota l'asimmetria deliberata (commentata nel dispatcher, review minor
    #7): l'ENTITA' fuori perimetro non e' controllata qui ma solo
    all'esecuzione -- l'enforcement di `allowed_entities` resta in un unico
    punto, `task_engine._run_action`."""
    agentbot, ha, execute_policy, task_engine, runner = _perimeter_chain(
        tmp_path, {"allowed_entities": [], "allowed_services": []})
    rec = _Rec()

    await _fire_objective_agentbot(
        agentbot, store=store, execute_policy=execute_policy, runner=runner, rec=rec)

    assert runner.seen_kwargs[0]["allowed_services"] == []
    assert task_engine._tasks == {}, "nessun task deve nascere fuori dal perimetro"
    assert ha.call_service.await_count == 0


@pytest.mark.asyncio
async def test_task_from_agent_without_declared_perimeter_is_unconfined(store, tmp_path):
    """L'altro lato: se l'utente non ha dichiarato NULLA, il blocco
    `perimeter` resta comunque materializzato (Task 2) ma le due allow-list
    valgono `None` = "nessuna restrizione su quell'asse". L'agente resta
    confinato dal semaforo (denylist + tier) e da `max_tier`, non da una
    allow-list che nessuno ha scritto.

    Prima di questo fix il default era `[]`, che il dispatcher leggeva come
    "nessun limite" (l'agente leggeva tutta la casa) e il task_engine come
    "nessuna concessione" (ogni Task emesso era inerte, con un solo
    `logger.warning` a dirlo). Quel doppio significato e' cio' che questo
    test impedisce di reintrodurre."""
    agentbot, ha, execute_policy, task_engine, runner = _perimeter_chain(tmp_path, None)
    assert agentbot["perimeter"]["allowed_entities"] is None
    assert agentbot["perimeter"]["allowed_services"] is None
    rec = _Rec()

    await _fire_objective_agentbot(
        agentbot, store=store, execute_policy=execute_policy, runner=runner, rec=rec)

    assert runner.seen_kwargs[0]["allowed_entities"] is None
    assert runner.seen_kwargs[0]["allowed_services"] is None

    task = next(iter(task_engine._tasks.values()))
    # L'IDENTITA' viene ereditata comunque: senza perimetro dichiarato il Task
    # e' comunque attribuito all'agente che lo ha emesso, non a "hiris-default".
    assert task.agent_id == "eeeeeeeeeeee"
    assert task.allowed_entities is None
    assert task.allowed_services is None

    # ...e l'azione passa, perche' `light` e' verde e nessuna allow-list la
    # nega: il confine e' il semaforo, esattamente come per ogni Task creato
    # fuori dalla modalita' obiettivo.
    ha.call_service.reset_mock()
    await task_engine._execute_task(task.id)
    assert ha.call_service.await_count == 1
    assert "not permitted by policy" not in (task.result or "")


@pytest.mark.asyncio
async def test_rule_mode_agentbot_reasoning_call_is_unchanged(store, tmp_path):
    """Regressione: un Agentbot in `mode="rule"` non ha (e non puo' avere) un
    blocco `perimeter`, quindi la sua chiamata di ragionamento resta identica a
    prima -- nessuna identita', nessun perimetro -- e i suoi task continuano a
    nascere esattamente come nascevano."""
    agentbot = validate_agentbot({
        "id": "ffffffffffff", "name": "Regola stufa", "enabled": True,
        "trigger": {"type": "event", "entity_id": "switch.stufa",
                    "operator": ">", "threshold": 3000},
        "reasoning": {"enabled": True, "prompt": "Valuta."},
        "action": {"type": "service", "domain": "switch", "service": "turn_off",
                   "entity_id": "switch.stufa"},
        "severity": "warn",
    })
    assert agentbot is not None and agentbot["perimeter"] is None

    ha = AsyncMock()
    ha.call_service = AsyncMock(return_value=True)
    cache = MagicMock()
    execute_policy = {"tiers": {"switch": "green", "light": "green"}, "entity_tiers": {}}
    task_engine = TaskEngine(
        ha_client=ha, entity_cache=cache, notify_config={},
        data_path=str(tmp_path / "tasks.json"), execute_policy=execute_policy)
    task_engine._scheduler = MagicMock()
    dispatcher = ToolDispatcher(
        ha_client=ha, notify_config={}, entity_cache=cache, execute_policy=execute_policy)
    dispatcher.set_task_engine(task_engine)
    runner = _FakeReasoningRunner(dispatcher, ("create_task", _OUT_OF_PERIMETER_TASK_INPUTS))
    rec = _Rec()

    async def _gather_context(wake):
        return {}

    async def _record_situation_event(kind, entity_id, decision, outcome):
        return None

    run_decision = _load_real_server_run_decision(
        app={"llm_router": runner, "execute_policy": execute_policy},
        gather_context=_gather_context, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        record_situation_event=_record_situation_event)

    await run_agentbot(
        agentbot, {"entity_id": "switch.stufa", "value": 3500},
        store=store, run_decision=run_decision, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=lambda: execute_policy, allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-29",
    )

    assert len(runner.seen_kwargs) == 1
    kwargs = runner.seen_kwargs[0]
    assert kwargs.get("chatbot_id") is None
    assert kwargs.get("allowed_entities") is None
    assert kwargs.get("allowed_services") is None
    task = next(iter(task_engine._tasks.values()))
    assert task.agent_id == "hiris-default"
    assert task.allowed_entities is None
