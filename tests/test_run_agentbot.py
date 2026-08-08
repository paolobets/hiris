"""Tests for the shared `_run_agentbot` flow (Slice 5b, Task 3; renamed lens
-> Agentbot in SP-4 Fase A Task 3; the module file itself was renamed to
`agentbot_runner.py` in SP-4 Fase B Task 5):
`hiris.app.watcher.agentbot_runner.run_agentbot` + its pure helpers
(`agentbot_action`, `agentbot_message`, `normalize_agentbot_severity`).

`run_agentbot` is the function `server.py`'s `_on_startup` binds onto
`app["run_agentbot"]` (a thin closure over the real sentinel_store/execute/
_run_decision/notify/propose adapters) -- it lives in its own module
precisely so it can be exercised here with real collaborators
(`watcher.reasoner.reason`, `watcher.executor.execute`, a real
`SentinelStore`) plus fakes only at the true I/O edges (the LLM call,
notify/propose), instead of needing to boot the whole aiohttp app
(`_on_startup` connects to HA, writes ingress config, etc. -- not
practical in a unit test, same reasoning as the existing
`test_sentinel_evaluator.py`/`test_sentinel_executor.py` suites).

SECURITY FOCUS: the executed action must always be the Agentbot's own
deterministic config (`agentbot_action(agentbot)`), never derived from the
LLM's output, even when a malicious/broken LLM fake tries to propose a
different target. See `test_ai_lens_llm_attempts_to_override_action_*`.
"""
import asyncio
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
    OBJECTIVE_PREAMBLE,
    REFINEMENT_PREAMBLE,
    agentbot_action,
    agentbot_message,
    agentbot_system,
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
        self.proposed = []
        self.events = []

    async def notify(self, message, *, title):
        self.notified.append((title, message))

    async def propose(self, decision, wake):
        self.proposed.append(decision)

    def record_event(self, evt):
        self.events.append(evt)


def _policy(tiers=None, entity_tiers=None):
    def _get():
        return {"tiers": tiers or {}, "entity_tiers": entity_tiers or {}}
    return _get


def _make_run_decision_from_llm(llm_reason, *, gather_context=None, notify, propose,
                                 execute_policy):
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
            notify=notify, propose=propose)
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
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=_policy(),
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert outcome == "woke"
    assert rec.notified and rec.notified[0][1] == "Temperatura troppo alta!"
    assert not rec.proposed
    assert rec.events and rec.events[0]["outcome"] == "notify"
    assert rec.events[0]["kind"] == "agentbot:aaaaaaaaaaaa"


# ---------------------------------------------------------------------------
# (b) zero-AI Agentbot, service action, green tier -> executor proposes.
#
# Fetta E2 Task 6 ("la Sentinella smette di usare il dispatcher"): il tier
# "green" non ha piu' un ramo di attuazione automatica (era dietro l'opt-in
# `allow_green_auto`, ora rimosso insieme ad `act`) -- propone sempre, come
# "yellow". Il nome del test e l'esito atteso sono cambiati di conseguenza;
# il resto del comportamento (l'azione eseguita/proposta e' quella della
# CONFIG dell'agentbot, mai dell'LLM) resta identico e continua a essere
# verificato piu' sotto, sui percorsi con reasoning abilitato.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_zero_ai_service_lens_green_tier_proposes(store):
    rec = _Rec()

    async def _run_decision_unused(wake, suggested, system):
        raise AssertionError("reasoning disabled -- run_decision must not be called")

    outcome = await run_agentbot(
        SERVICE_LENS, {"entity_id": "switch.stufa", "value": 3500},
        store=store, run_decision=_run_decision_unused, execute=real_execute,
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=_policy(tiers={"switch": "green"}),
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert outcome == "woke"
    assert len(rec.proposed) == 1
    assert rec.proposed[0].action == {
        "domain": "switch", "service": "turn_off", "entity_id": "switch.stufa"}
    assert rec.events[0]["outcome"] == "propose"
    # severity "alert" (SERVICE_LENS) must have been normalized to "critico"
    assert rec.events[0]["severity"] == "critico"


# ---------------------------------------------------------------------------
# (c) dangerous domain -> denylist blocks regardless of tier (only alert)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dangerous_domain_service_lens_only_alerts(store):
    rec = _Rec()

    async def _run_decision_unused(wake, suggested, system):
        raise AssertionError("reasoning disabled -- run_decision must not be called")

    outcome = await run_agentbot(
        DANGEROUS_LENS, {"entity_id": "sensor.x", "value": 2},
        store=store, run_decision=_run_decision_unused, execute=real_execute,
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=_policy(tiers={"cover": "green"}),
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert outcome == "woke"
    assert rec.events[0]["outcome"] == "alert"
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
        _llm_reason, notify=rec.notify, propose=rec.propose,
        execute_policy=_policy(tiers={"switch": "green"}))

    await run_agentbot(
        AI_SERVICE_LENS, {"entity_id": "switch.pompa", "value": 150},
        store=store, run_decision=run_decision, execute=real_execute,
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=_policy(tiers={"switch": "green"}),
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
    would sail through the (non-dangerous) tier gate and `propose` would be
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
        _malicious_llm_reason, notify=rec.notify, propose=rec.propose,
        execute_policy=_policy(tiers=tiers))

    await run_agentbot(
        AI_SERVICE_LENS, {"entity_id": "switch.pompa", "value": 150},
        store=store, run_decision=run_decision, execute=real_execute,
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=_policy(tiers=tiers),
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    # The proposed action must be the AGENTBOT's config action, never the LLM's.
    assert len(rec.proposed) == 1
    assert rec.proposed[0].action == {
        "domain": "switch", "service": "turn_off", "entity_id": "switch.pompa"}
    assert not any(
        d.action and d.action.get("domain") == "light" for d in rec.proposed)


@pytest.mark.asyncio
async def test_ai_lens_notify_only_llm_attempts_dangerous_action_still_denied(store):
    """Even in the one case where `agentbot_action` legitimately returns
    None (a `notify`-type Agentbot) and the LLM's own proposed action
    therefore isn't overridden by a `suggested` value, the real
    `executor.execute`'s dangerous-domain denylist is still the final
    backstop: a lock/alarm/cover/siren/garage target from the LLM is still
    never acted upon, nor even proposed."""
    rec = _Rec()
    notify_lens_ai = {**NOTIFY_LENS, "reasoning": {"enabled": True, "prompt": "Sii prudente."}}

    async def _malicious_llm_reason(system, user, *, model, max_tokens):
        return (
            '```json\n{"verdict":"anomalia","severity":"critico","message":"apro",'
            '"action":{"domain":"lock","service":"unlock","entity_id":"lock.porta_blindata"}}'
            '\n```'
        )

    run_decision = _make_run_decision_from_llm(
        _malicious_llm_reason, notify=rec.notify, propose=rec.propose,
        execute_policy=_policy(tiers={"lock": "green"}))

    await run_agentbot(
        notify_lens_ai, {"entity_id": "sensor.temp", "value": 35},
        store=store, run_decision=run_decision, execute=real_execute,
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=_policy(tiers={"lock": "green"}),
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert not rec.proposed  # dangerous domain denylist still blocks it


@pytest.mark.asyncio
async def test_ai_notify_lens_never_actuates_even_on_safe_green_domain(store):
    """Task 3 review fix: for a `notify`-type Agentbot, `agentbot_action`
    legitimately returns `None`, so the reasoning path's `if suggested and
    ...` guard never re-injects a deterministic action. Without
    `force_notify_only`, that leaves the LLM's OWN parsed `action` sitting
    on the Decision, and on a SAFE (non-dangerous) domain with a green tier
    `executor.execute` would propose it -- even though the user explicitly
    configured this Agentbot as "just notify". Unlike
    `test_ai_lens_notify_only_llm_attempts_dangerous_action_still_denied`
    (which uses a dangerous `lock` domain, so the denylist alone would save
    it regardless of this fix), this test uses `light` -- a safe domain --
    so only `force_notify_only` forcing `decision.action = None` before
    `execute()` runs can prevent the proposal."""
    rec = _Rec()
    notify_lens_ai = {**NOTIFY_LENS, "reasoning": {"enabled": True, "prompt": "Sii prudente."}}

    async def _llm_proposes_safe_action(system, user, *, model, max_tokens):
        return (
            '```json\n{"verdict":"anomalia","severity":"warn","message":"agisco",'
            '"action":{"domain":"light","service":"turn_on","entity_id":"light.malicious_target"}}'
            '\n```'
        )

    run_decision = _make_run_decision_from_llm(
        _llm_proposes_safe_action, notify=rec.notify, propose=rec.propose,
        execute_policy=_policy(tiers={"light": "green"}))

    outcome = await run_agentbot(
        notify_lens_ai, {"entity_id": "sensor.temp", "value": 35},
        store=store, run_decision=run_decision, execute=real_execute,
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=_policy(tiers={"light": "green"}),
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert outcome == "woke"
    assert not rec.proposed  # notify Agentbot must NEVER get anything proposed, safe domain or not
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
            notify=rec.notify, propose=rec.propose,
            get_execute_policy=_policy(),
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
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=_policy(),
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )
    out_b = await run_agentbot(
        NOTIFY_LENS, {"entity_id": "sensor.temp_b"},
        store=store, run_decision=_run_decision_unused, execute=real_execute,
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=_policy(),
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
            notify=rec.notify, propose=rec.propose,
            get_execute_policy=_policy(),
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
            notify=rec.notify, propose=rec.propose,
            get_execute_policy=_policy(),
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
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=_policy(tiers={"switch": "green"}),
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
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=_policy(tiers={"switch": "green"}),
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
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=_policy(tiers={"switch": "green"}),
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
    fix: `rec.proposed` would contain the LLM's fabricated action."""
    rec = _Rec()

    async def _llm_invents_an_action(system, user, *, model, max_tokens):
        return (
            '```json\n{"verdict":"anomalia","severity":"warn","message":"agisco",'
            '"action":{"domain":"light","service":"turn_on","entity_id":"light.malicious_target"}}'
            '\n```'
        )

    run_decision = _make_run_decision_from_llm(
        _llm_invents_an_action, notify=rec.notify, propose=rec.propose,
        execute_policy=_policy(tiers={"light": "green"}))

    await run_agentbot(
        OBJECTIVE_LENS, {"entity_id": "switch.pompa", "value": 150},
        store=store, run_decision=run_decision, execute=real_execute,
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=_policy(tiers={"light": "green"}),
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert not rec.proposed  # the LLM-invented action must never reach the executor
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
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=_policy(tiers={"switch": "green"}),
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )
    await run_agentbot(
        lens_b, {"entity_id": "switch.pompa2", "value": 150},
        store=store, run_decision=_run_decision_spy, execute=real_execute,
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=_policy(tiers={"switch": "green"}),
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


def _load_real_server_run_decision(*, app, gather_context, execute, notify, propose,
                                   record_situation_event, extra_globals=None):
    """Carica le closure REALI `_llm_reason` + `_run_decision` da
    `server._on_startup`, legandole a doppi di test per le sole variabili
    libere che non sono simboli importabili (`app`, `_gather_context`,
    `_notify`/`_propose`, `_record_situation_event`). Tutto il resto
    (`reason`, `execute`, `env_bool`, `RunnerBackendError`, `logger`) e' un
    simbolo reale, quindi il legame e' esatto e non una supposizione.

    La base del namespace sono i GLOBALI VERI di `server` (`vars(server)`):
    le closure estratte chiamano anche collaboratori a livello di modulo
    (`asyncio`, e da Fase 2 Task 5 gli helper del bound per esecuzione), e
    partire dai globali reali li lega alla loro implementazione VERA invece
    di far esplodere l'estrazione con un NameError a ogni nuovo helper -- o,
    peggio, di lasciarli stubbare in silenzio. Le voci qui sotto restano
    override espliciti perche' sono variabili LOCALI di `_on_startup`
    (import locali, adapter) e in `vars(server)` non ci sono.
    `extra_globals` e' l'unico modo per sostituire di proposito uno di quei
    globali in un singolo test (usato per accorciare la scadenza sotto il
    minuto senza far attendere la suite)."""
    from hiris.app.claude_runner import RunnerBackendError

    src = inspect.getsource(server._on_startup)
    namespace = {
        **vars(server),
        "app": app,
        "logger": logging.getLogger("test_run_agentbot_perimeter"),
        "RunnerBackendError": RunnerBackendError,
        "reason": reason,
        "execute": execute,
        "env_bool": server.env_bool,
        "_gather_context": gather_context,
        "_notify": notify,
        "_propose": propose,
        "_record_situation_event": record_situation_event,
    }
    namespace.update(extra_globals or {})
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
        notify=rec.notify, propose=rec.propose,
        record_situation_event=_record_situation_event)

    return await run_agentbot(
        agentbot, {"entity_id": "light.cucina", "value": 1},
        store=store, run_decision=run_decision, execute=real_execute,
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=lambda: execute_policy,
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
    confinato dal solo semaforo (denylist + tier), non da una allow-list
    che nessuno ha scritto.

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
        notify=rec.notify, propose=rec.propose,
        record_situation_event=_record_situation_event)

    await run_agentbot(
        agentbot, {"entity_id": "switch.stufa", "value": 3500},
        store=store, run_decision=run_decision, execute=real_execute,
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=lambda: execute_policy,
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


# ---------------------------------------------------------------------------
# (h) Agenti v1.1 Fase 2 Task 5: bound PER ESECUZIONE (budget + scadenza).
#
# `perimeter.budget_tokens` / `perimeter.deadline_min` esistevano gia'
# (validati e materializzati da `_validate_perimeter`) ma non li consumava
# nessuno: una singola esecuzione di ragionamento di un agente-obiettivo --
# che dal Task 4 gira da sola, su pianificazione, senza nessuno a guardarla --
# non aveva alcun limite. I contatori cumulativi giornalieri (daily cap della
# sentinella, usage.json) sono un'altra cosa e restano invariati.
#
# Questi test girano sul VERO `_run_decision` estratto da `server._on_startup`
# (stessa tecnica della sezione (g)): il bound e' proprio li' dentro, quindi
# un mirror scritto a mano non proverebbe nulla. Cio' che viene verificato e'
# COMPORTAMENTO: che il lavoro successivo (esecuzione della Decision:
# notify/propose) NON avvenga, e che l'esito finisca leggibile dove il
# sistema gia' registra gli esiti di queste esecuzioni
# (`_record_situation_event` -> `sentinel_store.record_event` -> `/api/
# sentinel/timeline` -> lista eventi dell'editor agentbot).
# ---------------------------------------------------------------------------

_DECISION_TEXT = (
    '```json\n{"verdict":"anomalia","severity":"warn",'
    '"message":"ho valutato la cucina","action":null}\n```'
)


class _MeteredReasoningRunner:
    """Sta al posto di `app["llm_router"]` ed espone le DUE sole cose che il
    percorso di ragionamento gli chiede: `run_with_actions` (il bordo di I/O
    verso l'LLM) e `get_chatbot_usage(agent_id)` (i contatori per-agente che
    il vero `ClaudeRunner.chat` incrementa a ogni risposta dell'API e che
    `LLMRouter` aggrega -- vedi claude_runner.py:718-724 e
    llm_router.py:346-362).

    `tokens_in`/`tokens_out` sono contabilizzati DENTRO la chiamata, come fa
    il runner vero: se la chiamata viene annullata a meta' non si contano.
    `requests` invece avanza all'INGRESSO della chiamata, prima di sapere cosa
    rispondera' il modello -- esattamente dove lo incrementano i runner veri
    (`claude_runner.py:609`, `openai_compat_runner.py:474` e `:756`), ed e'
    cio' che dice al bound se una chiamata e' stata davvero attribuita a
    questo agente. `track_usage=False` riproduce un runner che NON tiene
    contabilita' per-agente (contatori sempre a zero): il consumo non e'
    misurabile e il bound sul budget deve fallire aperto, dicendolo.
    `delay` serve a far scadere la scadenza; `usage_reads` conta le letture
    dei contatori, cosi' un test puo' dimostrare che per un Agentbot senza
    perimetro non viene nemmeno misurato nulla."""

    def __init__(self, *, tokens_in=0, tokens_out=0, delay=0.0, text=_DECISION_TEXT,
                 track_usage=True):
        self._tokens_in = tokens_in
        self._tokens_out = tokens_out
        self._delay = delay
        self._text = text
        self._track_usage = track_usage
        self._usage = {}
        self.calls = 0
        self.completed = 0
        self.usage_reads = 0
        self.seen_kwargs = []

    async def run_with_actions(self, **kwargs):
        self.calls += 1
        self.seen_kwargs.append(kwargs)
        cid = kwargs.get("chatbot_id")
        if cid and self._track_usage:
            u = self._usage.setdefault(
                cid, {"input_tokens": 0, "output_tokens": 0, "requests": 0})
            u["requests"] += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        if cid and self._track_usage:
            u["input_tokens"] += self._tokens_in
            u["output_tokens"] += self._tokens_out
        self.completed += 1
        return self._text, {}

    def get_chatbot_usage(self, chatbot_id):
        self.usage_reads += 1
        u = self._usage.get(chatbot_id) or {}
        return {
            "input_tokens": u.get("input_tokens", 0),
            "output_tokens": u.get("output_tokens", 0),
            "requests": u.get("requests", 0),
            "cost_usd": 0.0, "last_run": None,
            "tokens_today": 0, "tokens_today_date": "",
        }


async def _fire_bounded_agentbot(agentbot, *, store, runner, rec, events,
                                 extra_globals=None):
    """Fa scattare l'agentbot attraverso il flusso reale
    (`run_agentbot` -> `_run_decision` vero -> `reason` vero -> `execute`
    vero), raccogliendo in `events` cio' che il percorso registra come esito
    (l'argomento di `_record_situation_event`)."""
    execute_policy = {"tiers": {"light": "green"}, "entity_tiers": {}}

    async def _gather_context(wake):
        return {}

    async def _record_situation_event(kind, entity_id, decision, outcome):
        events.append({
            "kind": kind, "entity_id": entity_id, "outcome": outcome,
            "verdict": getattr(decision, "verdict", None),
            "severity": getattr(decision, "severity", None),
            "message": getattr(decision, "message", ""),
        })

    run_decision = _load_real_server_run_decision(
        app={"llm_router": runner, "execute_policy": execute_policy},
        gather_context=_gather_context, execute=real_execute,
        notify=rec.notify, propose=rec.propose,
        record_situation_event=_record_situation_event,
        extra_globals=extra_globals)

    return await run_agentbot(
        agentbot, {"entity_id": "light.cucina", "value": 1},
        store=store, run_decision=run_decision, execute=real_execute,
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=lambda: execute_policy,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-29",
    )


@pytest.mark.asyncio
async def test_run_over_token_budget_stops_and_records_why(store):
    """Sforare `budget_tokens` ferma l'esecuzione: la Decision del
    ragionatore non viene eseguita (niente notify/propose) e al suo posto
    resta un esito che dice perche'."""
    agentbot = validate_agentbot({**OBJECTIVE_AGENTBOT_RAW,
                                  "perimeter": {"budget_tokens": 100}})
    assert agentbot["perimeter"]["budget_tokens"] == 100
    # 120 + 30 = 150 token consumati da questa singola esecuzione: oltre i 100
    # concessi.
    runner = _MeteredReasoningRunner(tokens_in=120, tokens_out=30)
    rec, events = _Rec(), []

    outcome = await _fire_bounded_agentbot(
        agentbot, store=store, runner=runner, rec=rec, events=events)

    assert outcome == "woke"
    assert runner.calls == 1, "il ragionamento parte comunque: il budget e' per esecuzione"
    # (a) il lavoro successivo NON e' avvenuto
    assert rec.notified == [], "la Decision non doveva essere eseguita"
    assert rec.proposed == []
    # (b) ...e l'esito e' leggibile da dove il sistema espone gli esiti
    assert len(events) == 1
    ev = events[0]
    assert ev["outcome"] == "interrotto:budget"
    assert "budget" in ev["message"].lower()
    assert "100" in ev["message"] and "150" in ev["message"], (
        "il motivo deve dire il tetto e quanto e' stato consumato: "
        f"{ev['message']!r}")


@pytest.mark.asyncio
async def test_run_over_deadline_stops_and_records_why(store):
    """Sforare `deadline_min` ferma l'esecuzione allo stesso modo: il
    ragionamento viene annullato a meta' (non e' un'eccezione che risale, non
    e' un silenzio) e lascia il suo esito.

    L'unico doppio e' `agent_run_bound`, che qui restituisce una scadenza di
    50 ms invece dei 60 s minimi che lo schema ammette (`deadline_min` e'
    un intero di MINUTI >= 1): far attendere un minuto alla suite non
    proverebbe nulla di piu'. La conversione minuti->secondi che quel doppio
    sostituisce e' coperta, sul perimetro VERO, da
    `test_execution_bound_is_read_from_the_validated_perimeter`; tutto il
    resto qui (asyncio.timeout, annullamento, registrazione dell'esito) e'
    codice di produzione."""
    agentbot = validate_agentbot({**OBJECTIVE_AGENTBOT_RAW, "perimeter": None})
    assert agentbot["perimeter"]["deadline_min"] == 5
    runner = _MeteredReasoningRunner(delay=5.0)
    rec, events = _Rec(), []

    outcome = await _fire_bounded_agentbot(
        agentbot, store=store, runner=runner, rec=rec, events=events,
        extra_globals={"agent_run_bound": lambda perimeter: (None, 0.05)})

    assert outcome == "woke"
    assert runner.calls == 1 and runner.completed == 0, (
        "il ragionamento dev'essere stato annullato a meta', non atteso fino in fondo")
    assert rec.notified == [] and rec.proposed == []
    assert len(events) == 1
    ev = events[0]
    assert ev["outcome"] == "interrotto:scadenza"
    # Il messaggio nella sua forma REALE, non un "scadenza" case-insensitive:
    # il numero e' quello del bound (qui i 50 ms del doppio, resi in minuti
    # dal formato di produzione), non una costante scritta a mano. La resa del
    # caso vero (300 s -> "5 min") e' asserita in
    # `test_execution_bound_is_read_from_the_validated_perimeter`.
    assert ev["message"] == (
        "Esecuzione interrotta: superata la scadenza di 0.000833333 min "
        "per questa esecuzione"), ev["message"]


@pytest.mark.asyncio
async def test_run_within_bounds_behaves_exactly_as_before(store):
    """Contro-prova: un'esecuzione che sta nei limiti (default 4096 token,
    5 minuti) fa esattamente cio' che faceva prima -- la Decision viene
    eseguita e l'esito e' quello dell'executor."""
    agentbot = validate_agentbot({**OBJECTIVE_AGENTBOT_RAW, "perimeter": None})
    assert agentbot["perimeter"]["budget_tokens"] == 4096
    runner = _MeteredReasoningRunner(tokens_in=40, tokens_out=10)
    rec, events = _Rec(), []

    outcome = await _fire_bounded_agentbot(
        agentbot, store=store, runner=runner, rec=rec, events=events)

    assert outcome == "woke"
    assert len(rec.notified) == 1
    assert rec.notified[0][1] == "ho valutato la cucina"
    assert len(events) == 1 and events[0]["outcome"] == "notify"


@pytest.mark.asyncio
async def test_rule_mode_agentbot_is_not_bounded_per_run(store):
    """Regressione: una regola non ha (e non puo' avere) un `perimeter`,
    quindi non ha ne' budget ne' scadenza per esecuzione -- e non viene
    nemmeno misurata: nessuna lettura dei contatori per-agente, nessun
    cambiamento di comportamento."""
    agentbot = validate_agentbot({
        "id": "ffffffffffff", "name": "Regola cucina", "enabled": True,
        "trigger": {"type": "event", "entity_id": "light.cucina",
                    "operator": ">", "threshold": 0},
        "reasoning": {"enabled": True, "prompt": "Valuta."},
        "action": {"type": "notify", "message": "occhio"},
        "severity": "warn",
    })
    assert agentbot is not None and agentbot["perimeter"] is None
    runner = _MeteredReasoningRunner(tokens_in=99999, tokens_out=99999)
    rec, events = _Rec(), []

    outcome = await _fire_bounded_agentbot(
        agentbot, store=store, runner=runner, rec=rec, events=events)

    assert outcome == "woke"
    assert runner.usage_reads == 0, (
        "una regola non ha perimetro: non c'e' nulla da misurare")
    assert len(rec.notified) == 1
    assert len(events) == 1 and events[0]["outcome"] == "notify"


def test_execution_bound_is_read_from_the_validated_perimeter():
    """Il bound arriva dal perimetro VERO materializzato dal validatore
    (default 4096 token / 5 minuti), i minuti diventano secondi una volta sola
    qui, e quei secondi tornano minuti leggibili nel messaggio d'esito."""
    agentbot = validate_agentbot({**OBJECTIVE_AGENTBOT_RAW, "perimeter": None})
    budget_tokens, deadline_sec = server.agent_run_bound(agentbot["perimeter"])
    assert (budget_tokens, deadline_sec) == (4096, 300.0)
    # Review Task 5, minor #5: la scadenza VERA e' >= 1 minuto, ma il test che
    # la fa scattare deve accorciarla a 50 ms per non far attendere la suite --
    # e cosi' nessuno asseriva mai la resa che l'utente legge davvero. Il
    # formato e' quello di produzione (`_run_decision`, ramo TimeoutError):
    # con `:g` i 300 s del perimetro reale diventano "5 min", non "5.0" ne'
    # "0.08333 h".
    stopped = server.agent_run_stopped(
        f"superata la scadenza di {deadline_sec / 60:g} min per questa esecuzione",
        "warn")
    assert stopped.message == (
        "Esecuzione interrotta: superata la scadenza di 5 min per questa esecuzione")
    assert stopped.verdict == "interrotto" and stopped.action is None
    # Nessun perimetro (= ogni Agentbot mode="rule", e ogni chiamante
    # built-in del percorso di ragionamento) -> nessun bound.
    assert server.agent_run_bound(None) == (None, None)


@pytest.mark.asyncio
async def test_run_exactly_at_budget_is_not_over_it(store):
    """Il limite e' un TETTO, non una soglia: spendere ESATTAMENTE
    `budget_tokens` non sfora (`server.py` confronta con `>`), quindi
    l'esecuzione prosegue e la Decision viene eseguita. Comportamento scelto,
    non incidentale: senza questo test un refactoring potrebbe trasformare
    `>` in `>=` senza che nulla protesti."""
    agentbot = validate_agentbot({**OBJECTIVE_AGENTBOT_RAW,
                                  "perimeter": {"budget_tokens": 150}})
    assert agentbot["perimeter"]["budget_tokens"] == 150
    # 120 + 30 = 150: esattamente il tetto, nemmeno un token oltre.
    runner = _MeteredReasoningRunner(tokens_in=120, tokens_out=30)
    rec, events = _Rec(), []

    outcome = await _fire_bounded_agentbot(
        agentbot, store=store, runner=runner, rec=rec, events=events)

    assert outcome == "woke"
    assert len(rec.notified) == 1, "esattamente al tetto non e' oltre il tetto"
    assert len(events) == 1 and events[0]["outcome"] == "notify"


@pytest.mark.asyncio
async def test_unmeasurable_run_fails_open_and_says_so(store, caplog):
    """Review Task 5, finding #1: se il consumo per-agente non e' misurabile
    (nessuna chiamata risulta attribuita all'agente: contatore richieste fermo
    attraverso l'esecuzione), il bound sul budget FALLISCE APERTO -- l'agente
    non viene fermato -- ma la cosa dev'essere DETTA, non invisibile.

    Il fail-open e' deliberato: un tetto che non sa contare non deve fermare un
    agente. Prima di questo fix era anche silenzioso, e un tetto mai applicato
    era indistinguibile da un tetto rispettato."""
    agentbot = validate_agentbot({**OBJECTIVE_AGENTBOT_RAW,
                                  "perimeter": {"budget_tokens": 10}})
    # Consumo enorme, ben oltre i 10 token concessi -- ma il runner non tiene
    # contabilita' per-agente, quindi non risulta da nessuna parte.
    runner = _MeteredReasoningRunner(tokens_in=99999, tokens_out=99999,
                                     track_usage=False)
    rec, events = _Rec(), []
    server._AGENT_UNMEASURED_WARNED.discard(agentbot["id"])

    with caplog.at_level(logging.WARNING, logger="hiris.app.server"):
        outcome = await _fire_bounded_agentbot(
            agentbot, store=store, runner=runner, rec=rec, events=events)

    # (a) fail-open: l'esecuzione NON viene interrotta
    assert outcome == "woke"
    assert len(rec.notified) == 1
    assert len(events) == 1 and events[0]["outcome"] == "notify"
    # (b) ...ma il tetto mancante e' visibile
    warnings = [r for r in caplog.records
                if r.levelno >= logging.WARNING and r.name == "hiris.app.server"]
    assert len(warnings) == 1, [r.getMessage() for r in warnings]
    assert agentbot["id"] in warnings[0].getMessage()
    assert "senza tetto sui token" in warnings[0].getMessage()


def test_measured_cheap_run_is_not_mistaken_for_an_unmeasurable_one(caplog):
    """Contro-prova del fix: zero token MISURATI (richieste avanzate) sono un
    legittimo giro economico -- valgono 0, non "non misurabile", e non fanno
    rumore. E l'avviso di misura assente esce UNA volta per agente, non a ogni
    esecuzione: questo percorso gira su pianificazione, e un warning per giro
    sarebbe rumore che nessuno legge piu'."""
    with caplog.at_level(logging.WARNING, logger="hiris.app.server"):
        # (a) misurato: 1 richiesta in piu', 0 token in piu' -> 0, niente warning
        assert server.agent_run_tokens_spent((500, 3), (500, 4), "aaaaaaaaaaaa") == 0
        assert server.agent_run_tokens_spent((500, 3), (700, 4), "aaaaaaaaaaaa") == 200
        assert [r for r in caplog.records if r.name == "hiris.app.server"] == []

        # (b) non misurato: richieste ferme -> None (nessun bound) + avviso
        server._AGENT_UNMEASURED_WARNED.discard("bbbbbbbbbbbb")
        assert server.agent_run_tokens_spent((0, 0), (0, 0), "bbbbbbbbbbbb") is None
        assert server.agent_run_tokens_spent((0, 0), (0, 0), "bbbbbbbbbbbb") is None
        assert server.agent_run_tokens_spent((0, 0), (0, 0), "bbbbbbbbbbbb") is None
        warnings = [r for r in caplog.records if r.name == "hiris.app.server"]
        assert len(warnings) == 1, [r.getMessage() for r in warnings]

    # (c) niente da confrontare (runner assente, o backend senza
    # `get_chatbot_usage`) -> nessuna misura, nessun bound. Da questo fix in
    # poi anche questo caso avvisa (stesso meccanismo, motivo "non
    # leggibili") -- vedi i due test di pipeline sotto per la versione che
    # attraversa `_run_decision` invece di chiamare la funzione da sola.
    server._AGENT_UNMEASURED_WARNED.discard("aaaaaaaaaaaa")
    assert server.agent_run_tokens_spent(None, (10, 1), "aaaaaaaaaaaa") is None
    assert server.agent_run_tokens_spent((10, 1), None, "aaaaaaaaaaaa") is None


@pytest.mark.asyncio
async def test_unreadable_first_read_fails_open_and_says_so(store, caplog):
    """Review Task 5, fix wave 2, finding minor B (ramo 1): se la PRIMA
    lettura di `agent_run_usage` (`_usage_before`, presa PRIMA del
    ragionamento) restituisce `None`, prima di questo fix il blocco
    `if _usage_before is not None:` a `server.py:1868` saltava l'intero
    controllo -- `agent_run_tokens_spent` non veniva nemmeno invocata, nessun
    warning, solo il `logger.debug` dentro `agent_run_usage`.

    Il fix sposta il cancello su `_budget_tokens is not None` (un bound e'
    stato davvero richiesto -- l'unica cosa che deve distinguere "nessun
    warning mai" da "warning se la misura fallisce"): la lettura fallita
    arriva ora ad `agent_run_tokens_spent`, che la tratta con lo STESSO
    meccanismo una-tantum del ramo "richieste ferme", ma un motivo diverso e
    leggibile."""
    agentbot = validate_agentbot({**OBJECTIVE_AGENTBOT_RAW,
                                  "perimeter": {"budget_tokens": 10}})
    # Consumo enorme rispetto al tetto: se il bound si applicasse per errore
    # (non e' quello che vogliamo: fail-open resta fail-open) l'esecuzione
    # verrebbe fermata e il test lo scoprirebbe.
    runner = _MeteredReasoningRunner(tokens_in=99999, tokens_out=99999)
    rec, events = _Rec(), []
    server._AGENT_UNMEASURED_WARNED.discard(agentbot["id"])

    calls = {"n": 0}

    def _flaky_first_read(_runner, _agent_id):
        calls["n"] += 1
        # 1a chiamata (`_usage_before`, prima del ragionamento): fallita.
        # 2a chiamata (dopo il ragionamento): leggibile -- ma ormai
        # irrilevante, perche' senza un "prima" non c'e' differenza da fare.
        return None if calls["n"] == 1 else (150, 1)

    with caplog.at_level(logging.WARNING, logger="hiris.app.server"):
        outcome = await _fire_bounded_agentbot(
            agentbot, store=store, runner=runner, rec=rec, events=events,
            extra_globals={"agent_run_usage": _flaky_first_read})

    # (a) fail-open: la prima lettura fallita non deve MAI fermare
    # un'esecuzione che senza questo fix proseguiva.
    assert outcome == "woke"
    assert len(rec.notified) == 1
    assert len(events) == 1 and events[0]["outcome"] == "notify"
    # (b) ...ma e' visibile, col motivo giusto: "non leggibili", non
    # "nessuna chiamata attribuita" (quello e' il ramo del fix precedente).
    warnings = [r for r in caplog.records
                if r.levelno >= logging.WARNING and r.name == "hiris.app.server"]
    assert len(warnings) == 1, [r.getMessage() for r in warnings]
    msg = warnings[0].getMessage()
    assert agentbot["id"] in msg
    assert "senza tetto sui token" in msg
    assert "non sono leggibili" in msg
    assert "nessuna chiamata" not in msg


@pytest.mark.asyncio
async def test_unreadable_second_read_fails_open_and_says_so(store, caplog):
    """Review Task 5, fix wave 2, finding minor B (ramo 2): se la SECONDA
    lettura di `agent_run_usage` (a ragionamento concluso) restituisce
    `None`, prima di questo fix `agent_run_tokens_spent` usciva subito
    (`before is None or after is None: return None`, `server.py:780-781`
    pre-fix) senza mai arrivare al controllo su `requests` -- nessun warning.

    E' lo STESSO ramo "contatori non leggibili" del test sopra (ramo 1), non
    un secondo meccanismo: qui e' la seconda lettura a fallire invece della
    prima, ma l'esito -- fail-open, un warning col motivo "non leggibili" --
    dev'essere identico."""
    agentbot = validate_agentbot({**OBJECTIVE_AGENTBOT_RAW,
                                  "perimeter": {"budget_tokens": 10}})
    runner = _MeteredReasoningRunner(tokens_in=99999, tokens_out=99999)
    rec, events = _Rec(), []
    server._AGENT_UNMEASURED_WARNED.discard(agentbot["id"])

    calls = {"n": 0}

    def _flaky_second_read(_runner, _agent_id):
        calls["n"] += 1
        # 1a chiamata (`_usage_before`): leggibile. 2a chiamata (dopo il
        # ragionamento): fallita -- il caso che il ramo 1 non copriva.
        return (0, 0) if calls["n"] == 1 else None

    with caplog.at_level(logging.WARNING, logger="hiris.app.server"):
        outcome = await _fire_bounded_agentbot(
            agentbot, store=store, runner=runner, rec=rec, events=events,
            extra_globals={"agent_run_usage": _flaky_second_read})

    assert outcome == "woke"
    assert len(rec.notified) == 1
    assert len(events) == 1 and events[0]["outcome"] == "notify"
    warnings = [r for r in caplog.records
                if r.levelno >= logging.WARNING and r.name == "hiris.app.server"]
    assert len(warnings) == 1, [r.getMessage() for r in warnings]
    msg = warnings[0].getMessage()
    assert agentbot["id"] in msg
    assert "senza tetto sui token" in msg
    assert "non sono leggibili" in msg
    assert "nessuna chiamata" not in msg


# ---------------------------------------------------------------------------
# (i) Agenti v1.1 Fase 2 Task 7: l'OBIETTIVO guida davvero il ragionamento.
#
# Fino a qui `objective` era decorativo: `_on_wake` componeva il prompt di
# sistema come `sentinel_system + "\n\n" + reasoning.prompt` e basta, quindi
# un agente mode="objective" inseguiva il campo *Verdetto* e non l'Obiettivo
# che l'utente aveva scritto. Questi test guardano cosa arriva DAVVERO al
# modello -- il `system_prompt` che `run_with_actions` riceve -- non che una
# variabile sia stata assegnata.
# ---------------------------------------------------------------------------

async def _system_prompt_seen_by_the_model(store, tmp_path, agentbot_raw):
    """Fa scattare un agente-obiettivo lungo la catena VERA (le closure
    `_llm_reason`/`_run_decision` estratte da `server._on_startup`, il
    dispatcher e il TaskEngine reali) e restituisce il `system_prompt` che il
    runner -- l'unico bordo finto, la chiamata all'LLM -- si e' visto
    arrivare. E' letteralmente la stringa che il modello leggerebbe."""
    agentbot = validate_agentbot(agentbot_raw)
    assert agentbot is not None, "l'agentbot di prova deve essere valido"
    _, _, execute_policy, _, runner = _perimeter_chain(tmp_path, None)
    rec = _Rec()
    outcome = await _fire_objective_agentbot(
        agentbot, store=store, execute_policy=execute_policy, runner=runner, rec=rec)
    assert outcome == "woke"
    assert runner.seen_kwargs, "il ragionatore deve essere stato invocato"
    return runner.seen_kwargs[0]["system_prompt"]


@pytest.mark.asyncio
async def test_objective_reaches_the_model(store, tmp_path):
    """(a) L'obiettivo scritto dall'utente deve comparire nel prompt di
    sistema che il modello riceve. RED prima del fix: il prompt conteneva
    solo SENTINEL_SYSTEM + reasoning.prompt."""
    system = await _system_prompt_seen_by_the_model(store, tmp_path, OBJECTIVE_AGENTBOT_RAW)
    assert "Tieni sotto controllo i consumi della cucina." in system


@pytest.mark.asyncio
async def test_objective_precedes_the_reasoning_prompt_which_still_counts(store, tmp_path):
    """(b) Il `reasoning.prompt` (il *Verdetto*) resta valido e usato: e'
    l'affinamento, non la sostanza. Quindi deve continuare ad arrivare al
    modello, DOPO l'obiettivo -- e il contratto di uscita di SENTINEL_SYSTEM
    (il blocco ```json``` che `parse_decision` legge) deve restare in testa,
    o la Decision non sarebbe piu' parsabile."""
    system = await _system_prompt_seen_by_the_model(store, tmp_path, OBJECTIVE_AGENTBOT_RAW)
    assert system.startswith(SENTINEL_SYSTEM)
    assert "Ragiona e pianifica se serve." in system
    assert system.index("Tieni sotto controllo i consumi della cucina.") < \
        system.index("Ragiona e pianifica se serve."), \
        "l'obiettivo e' la sostanza: deve precedere l'affinamento del verdetto"


@pytest.mark.asyncio
async def test_objective_agentbot_without_reasoning_prompt_still_carries_its_objective(store, tmp_path):
    """Un agente-obiettivo senza *Verdetto* non e' un agente senza scopo:
    l'obiettivo da solo deve bastare ad arrivare al modello."""
    system = await _system_prompt_seen_by_the_model(
        store, tmp_path,
        {**OBJECTIVE_AGENTBOT_RAW, "reasoning": {"enabled": True}})
    assert system.startswith(SENTINEL_SYSTEM)
    assert "Tieni sotto controllo i consumi della cucina." in system


@pytest.mark.asyncio
async def test_rule_agentbot_system_prompt_is_byte_for_byte_unchanged(store):
    """(d) NON-REGRESSIONE, la piu' importante: una REGOLA non ha obiettivo e
    deve comporre il prompt di sistema esattamente come prima --
    `sentinel_system + "\n\n" + reasoning.prompt`, nemmeno una virgola in
    piu'. Verde prima e dopo il fix: e' il lucchetto."""
    rec = _Rec()
    seen = []

    async def _run_decision_spy(wake, suggested, system, force_notify_only=False, model="auto"):
        seen.append(system)
        return None

    await run_agentbot(
        AI_SERVICE_LENS, {"entity_id": "switch.pompa", "value": 150},
        store=store, run_decision=_run_decision_spy, execute=real_execute,
        notify=rec.notify, propose=rec.propose,
        get_execute_policy=_policy(tiers={"switch": "green"}),
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert seen == [
        SENTINEL_SYSTEM + "\n\n" + AI_SERVICE_LENS["reasoning"]["prompt"]]


# ---------------------------------------------------------------------------
# (i-bis) Fix-wave della review sul Task 7.
#
# IMPORTANT 1: il wizard di creazione scrive `reasoning.prompt = missione` e
# `objective = obiettivo || missione`, quindi nel percorso di DEFAULT (utente
# che non compila un obiettivo separato) i due campi portano lo STESSO testo e
# il prompt composto ripeteva la frase due volte -- la seconda sotto
# un'etichetta che annuncia indicazioni *aggiuntive*.
#
# MINOR 4: la composizione in objective non aveva un lucchetto su stringa
# esatta (solo startswith + substring + ordine), quindi cancellare uno dei due
# preamboli sarebbe passato inosservato. Ora ce l'ha, come per rule.
#
# MINOR 5: `agentbot_system` e' una funzione pura mai chiamata direttamente
# dai test; i suoi bordi (objective vuoto/di soli spazi, reasoning assente,
# prompt vuoto vs assente) restavano coperti solo di riflesso.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_objective_is_not_repeated_as_if_it_were_a_refinement(store, tmp_path):
    """IMPORTANT 1, il test che conta: quando `reasoning.prompt` e l'obiettivo
    sono lo stesso testo -- il caso che il wizard produce da solo -- il testo
    deve comparire nel prompt di sistema ESATTAMENTE UNA VOLTA, e il preambolo
    di affinamento non deve esserci affatto (annuncerebbe un'aggiunta e
    consegnerebbe una copia)."""
    mission = OBJECTIVE_AGENTBOT_RAW["objective"]
    system = await _system_prompt_seen_by_the_model(
        store, tmp_path,
        {**OBJECTIVE_AGENTBOT_RAW,
         "reasoning": {"enabled": True, "prompt": mission}})
    assert system.count(mission) == 1, \
        "l'obiettivo non va ripetuto: e' una copia, non un affinamento"
    assert REFINEMENT_PREAMBLE not in system
    # e l'obiettivo continua ad arrivare, sotto il SUO preambolo
    assert system == SENTINEL_SYSTEM + "\n\n" + OBJECTIVE_PREAMBLE + "\n" + mission


def test_agentbot_system_dedupes_only_on_identical_text():
    """Il filtro e' su testo (a meno di spazi ai bordi), non su identita' di
    oggetto: spazi/newline attorno allo stesso contenuto contano come stesso
    contenuto, un prompt DIVERSO resta un affinamento legittimo."""
    def _sys(prompt):
        return agentbot_system(
            {"mode": "objective", "objective": "Obiettivo X",
             "reasoning": {"enabled": True, "prompt": prompt}}, "SYS")

    assert REFINEMENT_PREAMBLE not in _sys("Obiettivo X")
    assert REFINEMENT_PREAMBLE not in _sys("  Obiettivo X\n\n")
    assert REFINEMENT_PREAMBLE in _sys("Obiettivo X, ma solo di notte")
    assert REFINEMENT_PREAMBLE in _sys("obiettivo x")  # case-sensitive: testo diverso


def test_agentbot_system_objective_form_is_locked_to_an_exact_string():
    """MINOR 4: lucchetto su stringa esatta per la forma a TRE blocchi, gemello
    di quello che gia' esiste per rule. Cancellare `OBJECTIVE_PREAMBLE` o
    `REFINEMENT_PREAMBLE`, invertire l'ordine dei blocchi o cambiare il
    separatore fa fallire QUESTO test, non solo una substring."""
    system = agentbot_system(
        {"mode": "objective", "objective": "Obiettivo X",
         "reasoning": {"enabled": True, "prompt": "Verdetto Y"}}, "SYS")
    assert system == (
        "SYS"
        + "\n\n" + OBJECTIVE_PREAMBLE + "\n" + "Obiettivo X"
        + "\n\n" + REFINEMENT_PREAMBLE + "\n" + "Verdetto Y")
    # il contratto d'uscita resta in testa, byte zero
    assert system.startswith("SYS\n\n")


@pytest.mark.parametrize("agentbot", [
    pytest.param({"mode": "objective", "objective": "",
                  "reasoning": {"prompt": "P"}}, id="objective-vuoto"),
    pytest.param({"mode": "objective", "objective": "   \n\t ",
                  "reasoning": {"prompt": "P"}}, id="objective-soli-spazi"),
    pytest.param({"mode": "objective", "objective": None,
                  "reasoning": {"prompt": "P"}}, id="objective-null"),
    pytest.param({"mode": "objective", "objective": 42,
                  "reasoning": {"prompt": "P"}}, id="objective-non-str"),
    pytest.param({"mode": "rule", "objective": "ignorato",
                  "reasoning": {"prompt": "P"}}, id="rule-ignora-objective"),
    pytest.param({"reasoning": {"prompt": "P"}}, id="mode-assente-default-rule"),
])
def test_agentbot_system_falls_back_to_the_rule_form(agentbot):
    """MINOR 5: il fallback documentato. `validate_agentbot` non lascia
    arrivare qui un objective vuoto/non-str, ma se ci arrivasse la funzione
    deve tornare alla forma della REGOLA -- non emettere un'etichetta
    "Obiettivo dell'agente:" seguita dal nulla."""
    assert agentbot_system(agentbot, "SYS") == "SYS\n\nP"
    assert OBJECTIVE_PREAMBLE not in agentbot_system(agentbot, "SYS")


@pytest.mark.parametrize("reasoning, expected", [
    pytest.param(None, "SYS\n\n", id="reasoning-null"),
    pytest.param({}, "SYS\n\n", id="reasoning-vuoto"),
    pytest.param({"enabled": True}, "SYS\n\n", id="prompt-assente"),
    pytest.param({"enabled": True, "prompt": ""}, "SYS\n\n", id="prompt-vuoto"),
    pytest.param({"enabled": True, "prompt": None}, "SYS\n\n", id="prompt-null"),
])
def test_agentbot_system_rule_form_survives_a_missing_reasoning(reasoning, expected):
    """MINOR 5: in rule, `reasoning` assente/vuoto/senza prompt non deve
    rompere nulla ne' cambiare la forma storica (`SYS + "\\n\\n" + prompt`,
    con prompt vuoto)."""
    assert agentbot_system({"mode": "rule", "reasoning": reasoning}, "SYS") == expected
    assert agentbot_system({"reasoning": reasoning}, "SYS") == expected


@pytest.mark.parametrize("reasoning", [
    None, {}, {"enabled": True}, {"enabled": True, "prompt": ""},
    {"enabled": True, "prompt": None}, {"enabled": True, "prompt": "   "},
])
def test_agentbot_system_objective_alone_when_there_is_no_refinement(reasoning):
    """MINOR 5, lato objective: senza *Verdetto* (assente, vuoto, null o di
    soli spazi) resta la forma a DUE blocchi, senza etichetta di affinamento
    appesa al vuoto. Nota: `"   "` e' truthy, quindi passa dal ramo del
    confronto, non da `if prompt`."""
    system = agentbot_system(
        {"mode": "objective", "objective": "Obiettivo X", "reasoning": reasoning},
        "SYS")
    if reasoning == {"enabled": True, "prompt": "   "}:
        # spazi puri: != obiettivo, quindi il blocco c'e' -- documentato,
        # non desiderabile, ma `_validate_reasoning` non lo produce mai
        assert system.startswith("SYS\n\n" + OBJECTIVE_PREAMBLE + "\nObiettivo X")
    else:
        assert system == "SYS\n\n" + OBJECTIVE_PREAMBLE + "\nObiettivo X"
        assert REFINEMENT_PREAMBLE not in system


def test_agentbot_system_tolerates_garbage_without_raising():
    """MINOR 5: la funzione non deve mai alzare -- e' invocata dentro
    `_on_wake`, dove un'eccezione trasformerebbe un prompt malformato in un
    Agentbot morto. `None`, dict vuoto e prompt non-str inclusi."""
    assert agentbot_system(None, "SYS") == "SYS\n\n"
    assert agentbot_system({}, "SYS") == "SYS\n\n"
    # prompt non-str in objective: ramo tollerato (nessun AttributeError)
    out = agentbot_system(
        {"mode": "objective", "objective": "Obiettivo X",
         "reasoning": {"prompt": ["non", "una", "stringa"]}}, "SYS")
    assert OBJECTIVE_PREAMBLE in out and REFINEMENT_PREAMBLE in out
