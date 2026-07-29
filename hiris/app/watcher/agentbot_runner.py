"""Shared `_run_agentbot` flow (Slice 5b, Task 3; renamed lens -> Agentbot in
SP-4 Fase A Task 3): turns a fired user Agentbot into a `Decision` and runs
it through the SAME `executor.execute()` (semaforo: dangerous-domain
denylist + tier gate + step-up) used by the built-in sentinel paths
(guardian on_wake / situations `_run_decision`), gated through the SAME
`wake.maybe_wake` cooldown/daily-cap as those built-ins.

SECURITY (non-negotiable, see plan Global Constraints):
- The executed action is ALWAYS `agentbot_action(agentbot)` — the
  Agentbot's own deterministic config (`action.type=="service"` -> concrete
  HA service call shape; `"notify"` -> None). NEVER derived from the LLM's
  output. When reasoning is enabled, the optional AI path (`run_decision`,
  i.e. server.py's `_run_decision`) only ever gets to pick verdict/severity/
  message: it re-injects `suggested` (== `agentbot_action(agentbot)`) onto
  the parsed Decision after `reason()` returns, exactly like the built-in
  situations flow does (`server.py` `_run_decision`, mirroring
  `server.py:955-956`'s `decision.action = suggested`).
- For a `notify`-type Agentbot, `agentbot_action(agentbot)` is `None`, so
  the guard above never re-injects anything — left alone, the LLM's OWN
  parsed action would survive onto the Decision, and on a safe/green domain
  with `allow_green_auto` the executor would actuate it. This module closes
  that gap by passing `force_notify_only=(action.type=="notify")` into
  `run_decision`, which (in server.py's `_run_decision`) forces
  `decision.action = None` right before `execute()` runs. A notify Agentbot
  can therefore NEVER actuate, reasoning-enabled or not — only its
  verdict/severity/message ever reach the user.
- Reasoning always runs through `run_decision`, which (in production) is
  server.py's `_run_decision` -> `reason()` -> `_llm_reason()`, and
  `_llm_reason` calls the LLM with `allowed_tools=[]` -- this module does
  not weaken or bypass that; it never talks to the LLM directly.
- The zero-AI path calls `execute` directly with the exact same adapters
  (`notify`/`act`/`propose`) and `tiers`/`entity_tiers`/`allow_green_auto`
  shape as `_run_decision`'s own tail call, so the dangerous-domain
  denylist and tier gate in `executor.execute()` apply unchanged.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from .signals import Decision, WakeEvent
from .wake import maybe_wake

# Agentbot severity vocabulary (watcher.agentbots.ALLOWED_SEVERITIES =
# {"info","warn","alert"}) does not match the Signal/Decision/WakeEvent
# vocabulary (watcher.signals.SEVERITIES = ("info","warn","critico")) --
# this is the single place an Agentbot's user-authored severity crosses into
# the sentinel pipeline, so it's the single place that normalizes it.
_SEVERITY_MAP = {"info": "info", "warn": "warn", "alert": "critico"}


def normalize_agentbot_severity(severity: Any) -> str:
    """Map an Agentbot's severity (`{info,warn,alert}`) into the Signal/
    Decision/WakeEvent vocabulary (`{info,warn,critico}`). Unknown/malformed
    input (missing key, wrong type, unrecognized string) safely falls back
    to `"info"` -- never raises, never silently escalates an unrecognized
    value to `"critico"`."""
    return _SEVERITY_MAP.get(severity, "info")


def agentbot_action(agentbot: dict) -> Optional[dict]:
    """Deterministic action derived from the Agentbot's OWN config -- never
    from an LLM. `action.type == "service"` -> a concrete
    `{domain, service, entity_id, off_after_min?}` HA service-call shape
    (matching the executor's/`_act`'s expected Decision.action shape);
    `"notify"` (or any other/missing type) -> `None`, meaning
    "message-only": `executor.execute()` then just notifies, never acts."""
    action = (agentbot or {}).get("action") or {}
    if action.get("type") != "service":
        return None
    out = {
        "domain": action.get("domain"),
        "service": action.get("service"),
        "entity_id": action.get("entity_id"),
    }
    off_after_min = action.get("off_after_min")
    if off_after_min is not None:
        out["off_after_min"] = off_after_min
    return out


def agentbot_message(agentbot: dict, evidence: dict) -> str:
    """Zero-AI Decision message: the Agentbot's own configured
    `action.message` if the user set one, else a generic fallback naming
    the Agentbot and the triggering entity (never empty, never raises)."""
    agentbot = agentbot or {}
    evidence = evidence or {}
    action = agentbot.get("action") or {}
    msg = action.get("message")
    if isinstance(msg, str) and msg.strip():
        return msg
    name = agentbot.get("name") or agentbot.get("id") or "agentbot"
    entity_id = evidence.get("entity_id", "-")
    return f"Agentbot '{name}': condizione soddisfatta su {entity_id}"


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


async def run_agentbot(
    agentbot: dict,
    evidence: dict,
    *,
    store,
    run_decision: Callable[..., Awaitable],
    execute: Callable[..., Awaitable],
    notify: Callable[..., Awaitable],
    act: Callable[..., Awaitable],
    propose: Callable[..., Awaitable],
    get_execute_policy: Callable[[], dict],
    allow_green_auto: bool,
    record_event: Callable[[dict], Any],
    sentinel_system: str,
    clock: Callable[[], float] = time.time,
    today: Callable[[], str] = _today,
    cooldown_sec: int | None = None,
    daily_cap: int = 20,
) -> str:
    """Fire (or gate) a single user-Agentbot evaluation.

    `store` is the sentinel store (cooldown/cap bookkeeping, same schema
    used by the guardian/situations paths). `run_decision` is server.py's
    real `_run_decision(wake, suggested, system, force_notify_only=False,
    model="auto")` (the optional-reasoning path: reason() judges
    verdict/severity/message using THIS Agentbot's own `reasoning.model`,
    then re-injects `suggested` as the action, then -- if
    `force_notify_only` -- forces it back to None -- see module docstring).
    `execute` is the real `watcher.executor.execute` (the zero-AI path
    calls it directly, exactly like `_run_decision`'s own tail call).

    `cooldown_sec`: `None` (the default) keeps the ORIGINAL behavior -- a
    ~30-min cooldown, same as the built-in guardian/situations paths --
    which is what an EVENT-triggered Agentbot still gets (it has no cadence
    of its own to honor). Task 5 review Fix 2: a SCHEDULE-triggered
    Agentbot's own interval/cron cadence IS its rate limiter, so
    `server.py`'s scheduled callback passes `cooldown_sec=0` here to bypass
    the cooldown gate entirely for that fire -- `daily_cap` (an unrelated,
    unchanged safety net) still applies regardless.

    Returns the `maybe_wake` gate outcome: `"woke"` | `"cooldown"` | `"cap"`.

    NOTE (SP-4 Fase A Task 3 rename): `cap_scope` below changed from
    `f"lens:{...}"` to `f"agentbot:{...}"`. This is the SAME string used as
    the `wake_counts`/`cooldowns` partition key in `sentinel_store` (see
    that module), so on the day this ships, any Agentbot that already had a
    daily-cap count or an active cooldown under the OLD `lens:*` scope
    starts fresh under the new `agentbot:*` scope. This is a deliberate,
    documented one-time reset of soft rate-limiter bookkeeping only -- it
    does not touch the semaforo (dangerous-domain denylist / tier gate /
    step-up), which is unconditional and unaffected by this rename. See
    Task 3 report for the full rationale.

    Sibling reset: `watcher.guardian.Guardian._dispatch_user_agentbots`
    changed its OWN per-Agentbot duration-timer key the same way
    (`lens:{id}:{eid}` -> `agentbot:{id}:{eid}`) for the `needs_duration`
    gating on EVENT-triggered Agentbots -- any in-progress duration timer
    under the old key becomes an unreachable orphan row and restarts from
    zero under the new key on the same boot. Same deliberate one-time
    reset, not a bug.
    """
    _cooldown_sec = 1800 if cooldown_sec is None else cooldown_sec
    agentbot = agentbot or {}
    evidence = dict(evidence or {})
    agentbot_id = agentbot.get("id", "-")
    entity_id = evidence.get("entity_id", "-")
    cap_scope = f"agentbot:{agentbot_id}"
    key = f"{cap_scope}:{entity_id}"

    wake = WakeEvent(
        signal_kind=cap_scope,
        entity_id=entity_id,
        severity_hint=normalize_agentbot_severity(agentbot.get("severity")),
        evidence=evidence,
        ts=clock(),
    )

    async def _on_wake(w: WakeEvent) -> None:
        reasoning = agentbot.get("reasoning") or {}
        suggested = agentbot_action(agentbot)  # deterministic, from config -- never from the LLM
        if reasoning.get("enabled"):
            system = sentinel_system + "\n\n" + (reasoning.get("prompt") or "")
            action_type = (agentbot.get("action") or {}).get("type")
            # Task 4B: this Agentbot's OWN model (validated by
            # `watcher.agentbots._validate_reasoning`, default "auto") --
            # threaded into `run_decision` (server.py's `_run_decision`)
            # so each Agentbot reasons with its configured model instead of
            # always falling back to "auto".
            model = reasoning.get("model") or "auto"
            # Fase 1 fix-wave CRITICAL: fail closed on SHAPE, not on the
            # string "notify". This used to be `action_type == "notify"`,
            # which was exhaustive ONLY because v1.0 guaranteed `action` is
            # always a validated dict (`_validate_action` rejects `None`),
            # so `action_type` was always either "service" (-> `suggested`
            # non-None -> the OTHER guard in `_run_decision` re-injects it)
            # or "notify" (-> this guard fires). Fase 1's mode="objective"
            # broke that guarantee: `action` is `None` by design there, so
            # `action_type` is `None` too -- neither guard used to fire, and
            # the LLM's OWN parsed action would survive onto the Decision
            # and reach `executor.execute()` unchecked by either of this
            # module's two safety nets (only the denylist/tier gate inside
            # `execute()` still applied). `!= "service"` instead makes ANY
            # mode without a validated, deterministic service action --
            # current or future -- force notify-only by construction,
            # instead of requiring every new mode to remember to add itself
            # to an allowlist of "safe" action_type strings here.
            #
            # LATENT DEPENDENCY (see also `run_agentbot`'s module
            # docstring): this guard and `_run_decision`'s `if suggested`
            # guard are only jointly exhaustive because of that invariant.
            # Any FUTURE mode must either supply a validated service action
            # (`agentbot_action` returns non-None) or be forced through this
            # `force_notify_only` path -- there is no third option. A new
            # mode that tries to thread its own action through some OTHER
            # channel would reopen exactly this gap.
            await run_decision(
                w, suggested=suggested, system=system,
                force_notify_only=(action_type != "service"), model=model)
            return
        decision = Decision(
            verdict="anomalia",
            severity=normalize_agentbot_severity(agentbot.get("severity")),
            message=agentbot_message(agentbot, evidence),
            action=suggested,
        )
        ep = get_execute_policy() or {}
        outcome = await execute(
            decision, w,
            tiers=ep.get("tiers") or {}, entity_tiers=ep.get("entity_tiers") or {},
            notify=notify, act=act, propose=propose,
            allow_green_auto=allow_green_auto,
        )
        record_event({
            "ts": clock(), "kind": cap_scope, "entity_id": entity_id,
            "verdict": decision.verdict, "severity": decision.severity,
            "outcome": outcome, "message": decision.message,
        })

    return await maybe_wake(
        store, key, wake, on_wake=_on_wake,
        clock=clock, today=today,
        cooldown_sec=_cooldown_sec, daily_cap=daily_cap, cap_scope=cap_scope,
    )
