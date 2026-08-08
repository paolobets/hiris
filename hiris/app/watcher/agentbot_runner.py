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
  parsed action would survive onto the Decision and reach `executor.execute()`
  unchecked by this module's determinism guarantee (it would still land on
  "propose", never "act" -- the Sentinel stopped acting in fetta E2 Task 6 --
  but the PROPOSAL would then carry the LLM's target instead of nothing).
  This module closes that gap by passing `force_notify_only=(action.type=="notify")` into
  `run_decision`, which (in server.py's `_run_decision`) forces
  `decision.action = None` right before `execute()` runs. A notify Agentbot
  can therefore NEVER actuate, reasoning-enabled or not — only its
  verdict/severity/message ever reach the user.
- Reasoning always runs through `run_decision`, which (in production) is
  server.py's `_run_decision` -> `reason()` -> `_llm_reason()`. `_llm_reason`
  calls the LLM with `allowed_tools=[]`, which is falsy and does NOT narrow
  the tool set (`claude_runner.py:894-896`): the reasoner receives every
  `EVALUATION_ONLY_TOOLS` entry (`claude_runner.py:210-222`), a set that
  excludes only the tools that ACT (`call_ha_service`, `send_notification`,
  `trigger_automation`, `toggle_automation`, `http_request`) -- it is not
  "zero tools". This module does not weaken or bypass that; it never talks
  to the LLM directly, and actuation only ever happens through
  `executor.execute()`, gated by the semaforo, as described above.
- Agenti v1.1 Fase 2 Task 3: since `create_task` IS one of those tools, an
  Agentbot with a `perimeter` (mode="objective") also passes its id and its
  allow-lists into `run_decision`, so a Task the reasoner emits is born
  attributed to that agent and confined to its perimeter. The refusal
  itself still happens where it always did -- `task_engine._run_action`'s
  `allowed_entities`/`allowed_services` check, at execution time. Nothing
  here enforces anything new; it only stops leaving those fields empty.
- The zero-AI path calls `execute` directly with the exact same adapters
  (`notify`/`propose`) and `tiers`/`entity_tiers` shape as `_run_decision`'s
  own tail call, so the dangerous-domain denylist and tier gate in
  `executor.execute()` apply unchanged.
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
    (matching the executor's expected Decision.action shape);
    `"notify"` (or any other/missing type) -> `None`, meaning
    "message-only": `executor.execute()` then just notifies, never proposes."""
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


# Agenti v1.1 Fase 2 Task 7. Fino a qui `objective` era un campo
# DECORATIVO: nessun runtime lo leggeva (compariva solo dentro commenti in
# `server.py`, qui e in `api/handlers_agentbots.py`), e il prompt di sistema
# del ragionamento era `sentinel_system + "\n\n" + reasoning.prompt` e basta
# -- cioe' un agente mode="objective" inseguiva il campo *Verdetto* invece
# dell'Obiettivo che l'utente aveva scritto.
#
# Questi due preamboli sono l'unica cosa che quel campo aggiunge al prompt.
# Sono etichette, non istruzioni di sicurezza: cio' che l'agente puo'
# leggere e toccare resta deciso altrove (EVALUATION_ONLY_TOOLS lato
# ragionatore, semaforo + perimetro lato attuazione) e NON e' negoziabile
# da nulla di scritto qui dentro.
OBJECTIVE_PREAMBLE = (
    "Questo agente lavora per un OBIETTIVO: e' il criterio con cui valuti la "
    "situazione e decidi. Obiettivo dell'agente:"
)
REFINEMENT_PREAMBLE = (
    "Indicazioni aggiuntive per il verdetto (affinano l'obiettivo, non lo "
    "sostituiscono):"
)


def agentbot_system(agentbot: dict, sentinel_system: str) -> str:
    """Prompt di sistema del ragionamento per QUESTO Agentbot.

    `sentinel_system` resta SEMPRE in testa, in entrambe le modalita': non e'
    decorazione, e' il contratto di uscita (il blocco ```json``` con
    verdict/severity/message/action che `reasoner.parse_decision` legge, piu'
    il divieto di proporre azioni su serrature/allarmi/tapparelle/sirene).
    Sostituirlo con un preambolo "da agente-obiettivo" avrebbe fatto sparire
    quel contratto e ogni Decision sarebbe degradata al ramo di fallback di
    `parse_decision` (testo grezzo come messaggio, severity dal solo hint).
    Da qui la forma scelta: si AGGIUNGE, non si rimpiazza.

    mode="rule" -> `sentinel_system + "\\n\\n" + reasoning.prompt`, byte per
    byte com'era prima di Fase 2 Task 7 (una regola non ha obiettivo:
    `validate_agentbot` lo VIETA in quella modalita').

    mode="objective" -> in mezzo entra l'obiettivo dell'utente, PRIMA del
    `reasoning.prompt`: l'obiettivo e' la sostanza, il *Verdetto* resta
    valido e usato ma come affinamento. L'ordine e' la parte che conta --
    l'ultima parola in un prompt di sistema pesa, e a pesare deve essere il
    criterio, non la rifinitura.

    Un `objective` vuoto/assente in objective mode non puo' arrivare qui
    (`validate_agentbot` rigetta il record), ma se ci arrivasse si torna alla
    forma della regola invece di emettere un'etichetta senza contenuto.

    Fix-wave IMPORTANT 1: se `reasoning.prompt` e' lo STESSO testo
    dell'obiettivo (a meno di spazi ai bordi) il blocco di affinamento viene
    OMESSO. Non e' un'ottimizzazione: e' il percorso di DEFAULT del wizard di
    creazione (`create-wizard.js` scrive `reasoning.prompt = missione` e
    `objective = obiettivo || missione`, e l'editor avanzato ripropone
    entrambi i campi precompilati dai valori salvati), quindi senza questo
    filtro l'utente medio otteneva la stessa frase due volte, la seconda
    sotto un'etichetta che annuncia indicazioni *aggiuntive* e poi ne
    consegna una copia verbatim. Un'etichetta che mente al modello e' peggio
    di un'etichetta assente. Il confronto e' su testo, non su identita' di
    oggetto: due campi distinti con lo stesso contenuto sono lo stesso
    contenuto.

    Nessuna sanitizzazione: `objective` e `reasoning.prompt` hanno la stessa
    provenienza (l'utente che configura o approva l'agente, non Home
    Assistant -- `objective` puo' essere scritto da un LLM via proposta del
    Brain, `handlers_proposals.py`, ma solo con approvazione esplicita) e lo
    stesso trattamento che `reasoning.prompt` ha sempre avuto -- e' il
    materiale che ARRIVA da HA a essere sanificato, in
    `reasoner.build_user_message`. La lunghezza e' gia' limitata a monte
    (2000 caratteri per entrambi, `watcher.agentbots`)."""
    agentbot = agentbot or {}
    prompt = (agentbot.get("reasoning") or {}).get("prompt") or ""
    objective = agentbot.get("objective")
    objective = objective.strip() if isinstance(objective, str) else ""
    if (agentbot.get("mode") or "rule") != "objective" or not objective:
        return sentinel_system + "\n\n" + prompt
    blocks = [sentinel_system, f"{OBJECTIVE_PREAMBLE}\n{objective}"]
    # `objective` e' gia' strippato qui sopra: il confronto e' strip-vs-strip.
    # Il test `isinstance` non e' ridondante -- tiene un `prompt` non-str
    # (che questa funzione tollerava prima) su esattamente il ramo che
    # prendeva prima, senza trasformare un dato sporco in AttributeError.
    same_text = isinstance(prompt, str) and prompt.strip() == objective
    if prompt and not same_text:
        blocks.append(f"{REFINEMENT_PREAMBLE}\n{prompt}")
    return "\n\n".join(blocks)


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
    propose: Callable[..., Awaitable],
    get_execute_policy: Callable[[], dict],
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
            # Task 7: in mode="objective" l'obiettivo dell'utente entra nel
            # prompt di sistema PRIMA del reasoning.prompt; in mode="rule"
            # (nessun obiettivo) la forma resta byte per byte
            # `sentinel_system + "\n\n" + reasoning.prompt`. Tutta la
            # composizione vive in `agentbot_system` (testabile in
            # isolamento).
            system = agentbot_system(agentbot, sentinel_system)
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
            #
            # Agenti v1.1 Fase 2 Task 3: identity + perimeter travel TOGETHER
            # and only exist together. `validate_agentbot` materializes
            # `perimeter` for every mode="objective" Agentbot (with explicit
            # defaults when the user declared none) and FORBIDS it for
            # mode="rule" -- so `perimeter is None` is exactly "this is a
            # rule", and a rule keeps the pre-Fase-2 call shape verbatim:
            # no identity, no scope, byte-for-byte the reasoning call it
            # always made. This matters beyond the Task it emits:
            # `chatbot_id` also scopes the reasoner's `recall_memory` tool
            # (`tools/dispatcher.py`), so handing a rule an identity it
            # never had would silently move it to an empty memory bucket.
            #
            # Downstream, `run_decision` (server.py's `_run_decision`) binds
            # both onto the `llm_reason` callable; the Task the reasoner
            # emits is then stamped with this agent's id and confined to
            # this perimeter, and `task_engine._run_action`'s ALREADY
            # EXISTING allow-list check refuses anything outside it at
            # execution time.
            perimeter = agentbot.get("perimeter")
            scope = {} if perimeter is None else {
                "agent_id": agentbot_id, "perimeter": perimeter}
            await run_decision(
                w, suggested=suggested, system=system,
                force_notify_only=(action_type != "service"), model=model,
                **scope)
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
            notify=notify, propose=propose,
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
