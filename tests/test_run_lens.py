"""Tests for the shared `_run_lens` flow (Slice 5b, Task 3):
`hiris.app.watcher.lens_runner.run_lens` + its pure helpers
(`lens_action`, `lens_message`, `normalize_lens_severity`).

`run_lens` is the function `server.py`'s `_on_startup` binds onto
`app["run_lens"]` (a thin closure over the real sentinel_store/execute/
_run_decision/notify/act/propose adapters) -- it lives in its own module
precisely so it can be exercised here with real collaborators
(`watcher.reasoner.reason`, `watcher.executor.execute`, a real
`SentinelStore`) plus fakes only at the true I/O edges (the LLM call,
notify/act/propose), instead of needing to boot the whole aiohttp app
(`_on_startup` connects to HA, writes ingress config, etc. -- not
practical in a unit test, same reasoning as the existing
`test_sentinel_evaluator.py`/`test_sentinel_executor.py` suites).

SECURITY FOCUS: the executed action must always be the lens's own
deterministic config (`lens_action(lens)`), never derived from the LLM's
output, even when a malicious/broken LLM fake tries to propose a
different target. See `test_ai_lens_llm_attempts_to_override_action_*`.
"""
import pytest

from hiris.app.watcher.executor import execute as real_execute
from hiris.app.watcher.lens_runner import (
    lens_action,
    lens_message,
    normalize_lens_severity,
    run_lens,
)
from hiris.app.watcher.reasoner import SENTINEL_SYSTEM, reason
from hiris.app.watcher.sentinel_store import SentinelStore


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_normalize_lens_severity_maps_alert_to_critico():
    assert normalize_lens_severity("alert") == "critico"


def test_normalize_lens_severity_passes_through_info_and_warn():
    assert normalize_lens_severity("info") == "info"
    assert normalize_lens_severity("warn") == "warn"


def test_normalize_lens_severity_unknown_defaults_to_info():
    assert normalize_lens_severity("bogus") == "info"
    assert normalize_lens_severity(None) == "info"
    assert normalize_lens_severity(123) == "info"


def test_lens_action_service_type_returns_deterministic_shape():
    lens = {"action": {"type": "service", "domain": "switch", "service": "turn_off",
                        "entity_id": "switch.stufa", "off_after_min": 5, "message": "x"}}
    assert lens_action(lens) == {"domain": "switch", "service": "turn_off",
                                  "entity_id": "switch.stufa", "off_after_min": 5}


def test_lens_action_service_type_without_off_after_min_omits_key():
    lens = {"action": {"type": "service", "domain": "light", "service": "turn_on",
                        "entity_id": "light.x"}}
    out = lens_action(lens)
    assert out == {"domain": "light", "service": "turn_on", "entity_id": "light.x"}
    assert "off_after_min" not in out


def test_lens_action_notify_type_returns_none():
    lens = {"action": {"type": "notify", "message": "ciao"}}
    assert lens_action(lens) is None


def test_lens_action_missing_or_malformed_action_returns_none():
    assert lens_action({}) is None
    assert lens_action({"action": None}) is None
    assert lens_action({"action": {"type": "bogus"}}) is None


def test_lens_message_uses_configured_message():
    lens = {"action": {"type": "notify", "message": "Attenzione: porta aperta"}}
    assert lens_message(lens, {"entity_id": "sensor.x"}) == "Attenzione: porta aperta"


def test_lens_message_falls_back_when_no_configured_message():
    lens = {"id": "abc123abc123", "name": "Porta garage", "action": {"type": "notify"}}
    msg = lens_message(lens, {"entity_id": "binary_sensor.garage"})
    assert "Porta garage" in msg and "binary_sensor.garage" in msg


def test_lens_message_never_raises_on_empty_input():
    assert lens_message({}, {}) != ""


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
    review fix: a notify-type lens must NEVER actuate, even when `suggested`
    is None and the LLM's own parsed action would otherwise survive), then
    runs the result through the REAL `executor.execute`. This is the same
    "not practical to instantiate the real _on_startup closure, so mirror
    the composed logic against real reason()/execute()" approach already
    used by `tests/test_sentinel_wiring.py`'s `_resolve_verdict` mirror.

    Task 4B: `model` is accepted and threaded straight into `reason()`,
    exactly like the real `_run_decision` -- so this mirror still matches
    the production wiring now that `lens_runner.py`'s `_on_wake` passes
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
    "id": "dddddddddddd", "name": "Lente AI", "enabled": True,
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
# (a) zero-AI lens, notify action -> executor called with Decision(action=None)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_zero_ai_notify_lens_calls_executor_notify_path(store):
    rec = _Rec()

    async def _run_decision_unused(wake, suggested, system):
        raise AssertionError("reasoning disabled -- run_decision must not be called")

    outcome = await run_lens(
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
    assert rec.events[0]["kind"] == "lens:aaaaaaaaaaaa"


# ---------------------------------------------------------------------------
# (b) zero-AI lens, service action, green tier + opt-in -> executor acts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_zero_ai_service_lens_green_tier_acts(store):
    rec = _Rec()

    async def _run_decision_unused(wake, suggested, system):
        raise AssertionError("reasoning disabled -- run_decision must not be called")

    outcome = await run_lens(
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

    outcome = await run_lens(
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
    assert rec.notified  # alert = notify with the lens's message


# ---------------------------------------------------------------------------
# (d) AI-enabled lens: reasoner invoked with the custom prompt appended to
#     SENTINEL_SYSTEM; a malicious LLM fake tries to redirect the action ->
#     ignored, the executed action is still the lens's config action.
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

    await run_lens(
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
    domain with its OWN tier=green, distinct from the lens's real
    `switch.pompa` target. This makes the test actually discriminating: if
    `run_lens` failed to pass the lens's deterministic `suggested` action
    into `run_decision`, the LLM's `light.malicious_target` action would
    sail through the (non-dangerous) tier gate and `act` would be called
    with it -- unlike a dangerous-domain target, which the executor's
    denylist would block regardless of whether the override happened,
    making that variant non-discriminating for this specific guarantee."""
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

    await run_lens(
        AI_SERVICE_LENS, {"entity_id": "switch.pompa", "value": 150},
        store=store, run_decision=run_decision, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(tiers=tiers), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    # The executed action must be the LENS's config action, never the LLM's.
    assert rec.acted == [{"domain": "switch", "service": "turn_off", "entity_id": "switch.pompa"}]
    assert not any(a.get("domain") == "light" for a in rec.acted)


@pytest.mark.asyncio
async def test_ai_lens_notify_only_llm_attempts_dangerous_action_still_denied(store):
    """Even in the one case where `lens_action` legitimately returns None
    (a `notify`-type lens) and the LLM's own proposed action therefore
    isn't overridden by a `suggested` value, the real `executor.execute`'s
    dangerous-domain denylist is still the final backstop: a lock/alarm/
    cover/siren/garage target from the LLM is still never acted upon."""
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

    await run_lens(
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
    """Task 3 review fix: for a `notify`-type lens, `lens_action` legitimately
    returns `None`, so the reasoning path's `if suggested and ...` guard
    never re-injects a deterministic action. Without `force_notify_only`,
    that leaves the LLM's OWN parsed `action` sitting on the Decision, and
    on a SAFE (non-dangerous) domain with a green tier + `allow_green_auto`,
    `executor.execute` would actuate it -- even though the user explicitly
    configured this lens as "just notify". Unlike
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

    outcome = await run_lens(
        notify_lens_ai, {"entity_id": "sensor.temp", "value": 35},
        store=store, run_decision=run_decision, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(tiers={"light": "green"}), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert outcome == "woke"
    assert not rec.acted  # notify lens must NEVER actuate, safe domain or not
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
        return await run_lens(
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
    """A lens firing on two different entities in the same evaluation batch
    (e.g. an event trigger matched via different evidence) must not share a
    single cooldown slot -- `key` includes the evidence's entity_id."""
    rec = _Rec()

    async def _run_decision_unused(wake, suggested, system):
        raise AssertionError("reasoning disabled")

    out_a = await run_lens(
        NOTIFY_LENS, {"entity_id": "sensor.temp_a"},
        store=store, run_decision=_run_decision_unused, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )
    out_b = await run_lens(
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
# (f) Task 5 review Fix 2: a SCHEDULED lens's own interval/cron cadence IS
# its rate limiter -- passing cooldown_sec=0 must bypass the cooldown gate
# entirely, while daily_cap (an unrelated, unchanged safety net) still
# applies. Event lenses (which never pass cooldown_sec) must keep the
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
        return await run_lens(
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
        return await run_lens(
            NOTIFY_LENS, {"entity_id": "sensor.temp"},
            store=store, run_decision=_run_decision_unused, execute=real_execute,
            notify=rec.notify, act=rec.act, propose=rec.propose,
            get_execute_policy=_policy(), allow_green_auto=True,
            record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
            clock=lambda: clock_val, today=lambda: "2026-07-24",
            # cooldown_sec intentionally omitted -- must resolve to the
            # same default (~1800s) as before Fix 2, for EVENT lenses.
        )

    out1 = await _run(1000.0)
    out2 = await _run(1100.0)  # 100s later, well within the default 1800s cooldown

    assert out1 == "woke"
    assert out2 == "cooldown"
    assert len(rec.notified) == 1


# ---------------------------------------------------------------------------
# (g) Task 4B: `reasoning.model` (per-Agentbot model) must reach
# `run_decision`'s `model` kwarg unchanged -- this is the actual runtime
# threading point (server.py's `_run_decision` has no `lens` in scope; the
# lens's `reasoning` dict is only in scope HERE, in `_on_wake`).
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

    await run_lens(
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
    await run_lens(
        AI_SERVICE_LENS, {"entity_id": "switch.pompa", "value": 150},
        store=store, run_decision=_run_decision_spy, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(tiers={"switch": "green"}), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert seen["model"] == "auto"


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

    await run_lens(
        lens_a, {"entity_id": "switch.pompa", "value": 150},
        store=store, run_decision=_run_decision_spy, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(tiers={"switch": "green"}), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )
    await run_lens(
        lens_b, {"entity_id": "switch.pompa2", "value": 150},
        store=store, run_decision=_run_decision_spy, execute=real_execute,
        notify=rec.notify, act=rec.act, propose=rec.propose,
        get_execute_policy=_policy(tiers={"switch": "green"}), allow_green_auto=True,
        record_event=rec.record_event, sentinel_system=SENTINEL_SYSTEM,
        clock=lambda: 1.0, today=lambda: "2026-07-24",
    )

    assert seen == ["claude-3-5-haiku", "gpt-4o-mini"]
