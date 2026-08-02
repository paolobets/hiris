from __future__ import annotations
import fnmatch
import logging
import re
from datetime import date
from typing import Any, Optional

# HA automation IDs are slug-style: lowercase alphanumeric + underscore.
# Reject anything else before composing entity_id, to avoid injection through
# automation.{id} in case HA's downstream parser is lenient.
_AUTOMATION_ID_RE = re.compile(r"^[a-z0-9_]+$")

# Action types the TaskEngine can actually execute (deny-by-default at create_task).
_ALLOWED_TASK_ACTIONS = frozenset({"call_ha_service", "send_notification", "create_task"})

from .ha_tools import (
    get_entity_states, get_area_entities, get_home_status,
    get_entities_on, get_entities_by_domain,
)
from .energy_tools import get_energy_history
from .weather_tools import get_weather_forecast
from .notify_tools import send_notification
from .automation_tools import get_ha_automations, get_automation_config, trigger_automation, toggle_automation
from .task_tools import create_task_tool, list_tasks_tool, cancel_task_tool
from .calendar_tools import (
    get_calendar_events, set_input_helper, create_calendar_event,
    resolve_input_helper_service,
)
from .http_tools import http_request
from .memory_tools import handle_recall_memory as _handle_recall_memory, handle_save_memory as _handle_save_memory
from .history_tools import get_history as _get_history
from .health_tools import get_ha_health
from .advisory_tools import get_advisories
from .diagnostics_tools import (
    get_logbook as _get_logbook,
    render_template as _render_template,
)
from .proposal_tools import create_automation_proposal
from .config_tools import normalize_config_inputs, apply_ha_config
from .dashboard_tools import propose_dashboard
from .knowledge_tools import (
    handle_save_knowledge, handle_recall_knowledge, handle_link_knowledge,
)
from ..brain.briefing import build_briefing_bundle, render_briefing_template
from ..security.semaphore import gate_action, normalize_target

logger = logging.getLogger(__name__)


# `None` vs `[]` -- ONE semantics for the whole chain (dispatcher -> Task ->
# `task_engine._run_action`), see `watcher/agentbots.py::_validate_str_list`:
#
#   allowed_* is None  -> NO RESTRICTION on that axis (the historical
#                         "unscoped caller" case: sentinel wakes, briefing,
#                         a chatbot with no allow-list configured).
#   allowed_* == []    -> DENY EVERYTHING on that axis. "Nothing granted" is
#                         not "no limits"; an empty allow-list is a decision,
#                         not an omission.
#
# Hence every check below tests `is None` / `is not None`, NEVER truthiness --
# truthiness would silently read `[]` as "unrestricted" here while
# `task_engine._run_action` (which has always used `is not None`) reads the
# very same `[]` as "deny", so the same value would mean opposite things at
# the two ends of one call.
def _filter_entities(entities: list[dict], allowed_entities: list[str] | None) -> list[dict]:
    """Return only entities whose ID matches any allowed_entities glob pattern.

    `None` -> unrestricted (every entity passes); `[]` -> nothing passes."""
    if allowed_entities is None:
        return entities
    return [
        e for e in entities
        if any(fnmatch.fnmatch(e.get("id", e.get("entity_id", "")), pat) for pat in allowed_entities)
    ]


def _filter_area_map(
    area_map: dict[str, list[str]], allowed_entities: list[str] | None
) -> dict[str, list[str]]:
    """Filter an area→[entity_id] map through the same _filter_entities allowlist
    used by get_home_status/get_entities_on/get_entities_by_domain (review B/#11):
    drop non-permitted entity_ids within each area, then drop areas left empty.

    `None` -> unrestricted (map returned as-is); `[]` -> every area drops out."""
    if allowed_entities is None:
        return area_map
    result: dict[str, list[str]] = {}
    for area, eids in area_map.items():
        kept = [e["id"] for e in _filter_entities([{"id": eid} for eid in eids], allowed_entities)]
        if kept:
            result[area] = kept
    return result


def _check_service_allowed(
    service_key: str, allowed_services: list[str] | None
) -> dict | None:
    """Return error dict if service blocked, None if allowed.

    `allowed_services is None` -> unrestricted; `[]` -> everything blocked."""
    if allowed_services is not None and not any(
        fnmatch.fnmatch(service_key, pat) for pat in allowed_services
    ):
        logger.warning("Service %s blocked by policy", service_key)
        return {"error": f"Service {service_key} not permitted by policy"}
    return None


def _check_entity_allowed(
    entity_id: str, allowed_entities: list[str] | None
) -> dict | None:
    """Return error dict if entity blocked, None if allowed.

    `allowed_entities is None` -> unrestricted; `[]` -> everything blocked."""
    if allowed_entities is not None and not any(
        fnmatch.fnmatch(entity_id, pat) for pat in allowed_entities
    ):
        logger.warning("Entity %s blocked by allowed_entities policy", entity_id)
        return {"error": f"Entity {entity_id!r} not permitted by policy"}
    return None


class ToolDispatcher:
    """Executes HIRIS tools. Shared across LLM runners so HA integration stays in one place."""

    def __init__(
        self,
        ha_client: Any,
        notify_config: dict,
        entity_cache: Any = None,
        semantic_map: Any = None,
        embedding_provider: Any = None,
        memory_retention_days: int | None = None,
        health_monitor: Any = None,
        advisory_store: Any = None,
        proposal_store: Any = None,
        knowledge_store: Any = None,
        embedder: Any = None,
        pseudonymizer: Any = None,
        history_store: Any = None,
        execute_policy: dict | None = None,
        request_confirmation: Any = None,
        confirm_executor: Any = None,
        data_dir: str | None = None,
    ) -> None:
        self._ha = ha_client
        self._notify_config = notify_config
        self._cache = entity_cache
        self._semantic_map = semantic_map
        self._embedder = embedding_provider
        self._memory_retention_days = memory_retention_days
        self._health_monitor = health_monitor
        self._advisory_store = advisory_store
        self._proposal_store = proposal_store
        self._knowledge_store = knowledge_store
        # Use dedicated embedder if provided, otherwise fall back to the memory embedder
        self._knowledge_embedder = embedder if embedder is not None else embedding_provider
        self._pseudonymizer = pseudonymizer
        self._history_store = history_store
        # Serviva a daily_briefing per caricare la soglia
        # detectors.battery.min_pct: ora le batterie arrivano dalle segnalazioni
        # del Brain e nessun tool lo legge piu'. Il parametro resta accettato
        # per non rompere il cablaggio esistente (server.py e i test lo passano).
        self._data_dir = data_dir
        # Riferimento VIVO al dict app["execute_policy"] (mutato in place da
        # apply_saved_policy): il semaforo si legge a ogni dispatch. {} = fail-closed.
        self._execute_policy = execute_policy if execute_policy is not None else {}
        self._request_confirmation = request_confirmation
        self._confirm_executor = confirm_executor
        self._task_engine: Any = None

    def set_task_engine(self, engine: Any) -> None:
        self._task_engine = engine

    async def _gate(
        self, *, name: str, inputs: dict, domain: str, service: str,
        entity_ids: list[str], user_id: str | None,
    ) -> dict | None:
        """Semaforo universale — gate condiviso da OGNI superficie che attua su HA
        (call_ha_service, trigger_automation, toggle_automation, set_input_helper;
        review A/#2, #9, #10). Chiamare SOLO quando l'azione non è già
        tier_confirmed (il chiamante decide se saltare il gate in quel caso, come
        fa call_ha_service per lo step-up out-of-band).

        Ritorna None se l'azione può procedere (allow). Altrimenti ritorna il
        dict ({"error": ...} o {"status": "confirmation_required", ...}) da
        restituire IMMEDIATAMENTE al chiamante SENZA attuare — mai chiamare
        ha.call_service (o l'equivalente tool) se il ritorno non è None.
        """
        verdict = gate_action(
            domain=domain, service=service, entity_ids=entity_ids,
            tiers=self._execute_policy.get("tiers") or {},
            entity_tiers=self._execute_policy.get("entity_tiers") or {},
        )
        if verdict.decision == "allow":
            return None
        logger.warning("%s gated: %s (%s.%s)", name, verdict.decision, domain, service)
        if verdict.decision == "confirm":
            if self._request_confirmation is not None:
                res = await self._request_confirmation(
                    tool=name, inputs=inputs, tier=verdict.tier, user=user_id,
                )
                # No-identity guard (Fix 5, mirrored from call_ha_service): fall
                # back to the generic error instead of minting a pending nobody
                # can ever confirm.
                if not isinstance(res, dict) or not res.get("id"):
                    return {"error": "Azione a rischio: richiede conferma."}
                return {"status": "confirmation_required",
                        "id": res.get("id"), "tier": verdict.tier,
                        "message": ("Ho bisogno della tua conferma: tocca "
                                    "'Conferma' nella notifica sul telefono, "
                                    "oppure dimmi il codice che ti ho inviato.")}
            return {"error": "Azione a rischio: richiede conferma."}
        return {"error": verdict.reason}

    @property
    def has_memory(self) -> bool:
        # save_memory/recall_memory route into the unified KnowledgeStore
        # (Slice 3) — gate tool exposure on that, not the legacy MemoryStore.
        return self._knowledge_store is not None and self._knowledge_embedder is not None

    async def dispatch(
        self,
        name: str,
        inputs: dict,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
        allowed_endpoints: Optional[list[dict]] = None,
        chatbot_id: Optional[str] = None,
        visible_entity_ids: Optional[frozenset] = None,
        knowledge_allow_sensitive: bool = False,
        knowledge_kinds: list[str] | str | None = None,
        cloud: bool = True,
        tier_confirmed: bool = False,
        user_id: str | None = None,
        pseudonym_map: dict[str, str] | None = None,
    ) -> Any:
        _REDACT_KEYS = frozenset({"api_key", "token", "password", "secret", "authorization", "code"})
        _log_inputs = {k: "***" if k.lower() in _REDACT_KEYS else v for k, v in inputs.items()}
        logger.info("Tool call: %s(%s)", name, _log_inputs)
        try:
            if name == "get_area_entities":
                result = await get_area_entities(self._ha, entity_cache=self._cache)
                return _filter_area_map(result, allowed_entities)
            if name == "get_entity_states":
                ids = inputs.get("ids", [])
                if visible_entity_ids:
                    ids = [eid for eid in ids if eid in visible_entity_ids]
                if allowed_entities is not None:
                    ids = [eid for eid in ids if any(fnmatch.fnmatch(eid, pat) for pat in allowed_entities)]
                return await get_entity_states(self._ha, ids, entity_cache=self._cache)
            if name == "get_history":
                entity_ids = inputs.get("entity_ids", [])
                if visible_entity_ids:
                    entity_ids = [eid for eid in entity_ids if eid in visible_entity_ids]
                if allowed_entities is not None:
                    entity_ids = [eid for eid in entity_ids
                                  if any(fnmatch.fnmatch(eid, pat) for pat in allowed_entities)]
                return await _get_history(
                    self._ha,
                    entity_ids,
                    days=int(inputs.get("days", 7)),
                    resolution=inputs.get("resolution", "auto"),
                    store=self._history_store,
                )
            if name == "get_logbook":
                # Un entity_id vuoto vale come assente: per il modello "" e
                # nessun valore significano la stessa cosa (tutta la casa).
                entity_id = inputs.get("entity_id") or None
                if entity_id is not None:
                    # ASIMMETRIA VOLUTA rispetto a get_entity_states/get_history:
                    # li' l'entita' fuori perimetro si SCARTA dalla lista, qui si
                    # RIFIUTA la chiamata. L'entita' e' una sola e facoltativa:
                    # scartarla equivarrebbe a chiedere il logbook dell'INTERA
                    # casa, cioe' ad allargare il perimetro invece di stringerlo.
                    if visible_entity_ids and entity_id not in visible_entity_ids:
                        logger.warning("get_logbook: %r fuori dal contesto visibile", entity_id)
                        return {"error": f"Entity {entity_id!r} non è fra quelle visibili in questo contesto"}
                    err = _check_entity_allowed(entity_id, allowed_entities)
                    if err is not None:
                        return err
                # I due rifiuti qui sopra si somigliano ma NON sono la stessa
                # cosa, e trattarli come equivalenti sarebbe un errore:
                #   - allowed_entities e' il perimetro di sicurezza e prosegue
                #     fino al tool, dove filtra anche le VOCI restituite. Deve:
                #     senza entity_id basterebbe ometterlo per leggere tutta la
                #     casa, e il rifiuto qui sopra non varrebbe nulla.
                #   - visible_entity_ids si ferma qui, e quindi il suo rifiuto e'
                #     aggirabile semplicemente non passando entity_id. E' voluto,
                #     perche' non e' un contenimento: e' l'insieme delle entita'
                #     rilevanti per la domanda corrente (SemanticContextMap),
                #     quasi sempre non vuoto e di natura semantica. Filtrarci le
                #     voci svuoterebbe proprio la domanda "cosa e' successo ieri
                #     sera?", che per definizione non conosce le entita' in
                #     anticipo. Non usarlo come se fosse una whitelist.
                # `hours` non si normalizza qui: assente o `null` valgono il
                # default DENTRO il tool, cosi' il contratto e' uno solo per
                # qualunque chiamante (vedi diagnostics_tools.get_logbook).
                return await _get_logbook(
                    self._ha,
                    entity_id=entity_id,
                    hours=inputs.get("hours"),
                    allowed_entities=allowed_entities,
                )
            if name == "render_template":
                # Nessun perimetro di entita' applicabile: un template le legge
                # tutte per costruzione. E' la ragione per cui questo tool resta
                # fuori da EVALUATION_ONLY_TOOLS (vedi claude_runner.py) ed e'
                # concedibile solo esplicitamente a un agente di chat.
                return await _render_template(self._ha, inputs.get("template"))
            if name == "get_home_status":
                result = get_home_status(self._cache, semantic_map=self._semantic_map) if self._cache else []
                return _filter_entities(result, allowed_entities)
            if name == "get_entities_on":
                result = get_entities_on(self._cache) if self._cache else []
                return _filter_entities(result, allowed_entities)
            if name == "get_entities_by_domain":
                result = get_entities_by_domain(inputs["domain"], self._cache) if self._cache else []
                return _filter_entities(result, allowed_entities)
            if name == "get_energy_history":
                return await get_energy_history(self._ha, inputs["days"], semantic_map=self._semantic_map)
            if name == "get_weather_forecast":
                return await get_weather_forecast(inputs["hours"])
            if name == "send_notification":
                return await send_notification(
                    self._ha, inputs.get("message", ""), inputs["channel"], self._notify_config,
                    title=inputs.get("title"), notification_id=inputs.get("notification_id"),
                )
            if name == "get_ha_automations":
                return await get_ha_automations(self._ha)
            if name == "get_automation_config":
                automation_id = inputs.get("automation_id", "")
                bare_id = (
                    automation_id[len("automation."):]
                    if automation_id.startswith("automation.") else automation_id
                )
                # Numeric unique ids bypass the entity_id path entirely (ha_client
                # fast path); anything else must match the same slug regex the
                # trigger/toggle branches enforce (review A/#4: SSRF/path-injection).
                if not (bare_id.isascii() and bare_id.isdigit()) and not _AUTOMATION_ID_RE.match(bare_id):
                    return {"error": f"invalid automation_id: {automation_id!r}"}
                return await get_automation_config(self._ha, automation_id)
            if name == "trigger_automation":
                automation_id = inputs["automation_id"]
                bare_id = (
                    automation_id[len("automation."):]
                    if automation_id.startswith("automation.") else automation_id
                )
                if not _AUTOMATION_ID_RE.match(bare_id):
                    return {"error": f"invalid automation_id: {automation_id!r}"}
                entity_id = f"automation.{bare_id}"
                err = _check_service_allowed("automation.trigger", allowed_services)
                if err is not None:
                    return err
                err = _check_entity_allowed(entity_id, allowed_entities)
                if err is not None:
                    return err
                if not tier_confirmed:
                    gate_result = await self._gate(
                        name=name, inputs=inputs, domain="automation", service="trigger",
                        entity_ids=[entity_id], user_id=user_id,
                    )
                    if gate_result is not None:
                        return gate_result
                return await trigger_automation(self._ha, automation_id)
            if name == "toggle_automation":
                automation_id = inputs["automation_id"]
                enabled = inputs["enabled"]
                bare_id = (
                    automation_id[len("automation."):]
                    if automation_id.startswith("automation.") else automation_id
                )
                if not _AUTOMATION_ID_RE.match(bare_id):
                    return {"error": f"invalid automation_id: {automation_id!r}"}
                entity_id = f"automation.{bare_id}"
                service_key = "automation.turn_on" if enabled else "automation.turn_off"
                err = _check_service_allowed(service_key, allowed_services)
                if err is not None:
                    return err
                err = _check_entity_allowed(entity_id, allowed_entities)
                if err is not None:
                    return err
                if not tier_confirmed:
                    gate_result = await self._gate(
                        name=name, inputs=inputs, domain="automation", service=service_key.split(".")[1],
                        entity_ids=[entity_id], user_id=user_id,
                    )
                    if gate_result is not None:
                        return gate_result
                return await toggle_automation(self._ha, automation_id, enabled)
            if name == "call_ha_service":
                domain = inputs["domain"]
                service = inputs["service"]
                data = inputs.get("data", {})
                target = inputs.get("target", {}) or {}
                # review A/#5: merge target into data ONCE, so the entity_ids gated
                # below are exactly the entity_ids forwarded to ha.call_service at
                # the bottom -- a target-scoped call must never be executed as a
                # domain-wide broadcast because `target` got silently dropped.
                normalized = normalize_target(data, target)
                # Semaforo universale (denylist + tier). Saltato se l'azione è già
                # stata confermata out-of-band da un umano (approvazione gateway /
                # step-up chat): in quel caso la conferma umana autorizza esattamente
                # questo comando, denylist inclusa (killer feature step-up).
                if not tier_confirmed:
                    # Fix #2/#8: un target per area/dispositivo/label non è risolvibile ai
                    # tier per-entità → fail-closed, INDIPENDENTEMENTE da entità esplicite
                    # accompagnatorie (HA attua l'intero gruppo lato server, bypassando
                    # gli override per-entità: un target misto entity_id+area_id fa sì
                    # che HA esegua su TUTTE le entità dell'area, non solo su quella verde).
                    if normalized.has_group_target:
                        logger.warning("call_ha_service gated: area/device/label target present (%s.%s)", domain, service)
                        return {"error": "Azione su area/dispositivo/label non consentita dal semaforo: specifica le entità target."}
                    gate_result = await self._gate(
                        name=name, inputs=inputs, domain=domain, service=service,
                        entity_ids=normalized.entity_ids, user_id=user_id,
                    )
                    if gate_result is not None:
                        return gate_result
                if allowed_services is not None:
                    service_key = f"{domain}.{service}"
                    if not any(fnmatch.fnmatch(service_key, pat) for pat in allowed_services):
                        logger.warning("Service %s.%s blocked by policy", domain, service)
                        return {"error": f"Service {domain}.{service} not permitted by policy"}
                if allowed_entities is not None:
                    eids = normalized.entity_ids
                    if not eids:
                        logger.warning("call_ha_service blocked: no target entity under an active entity whitelist")
                        return {"error": "call_ha_service richiede un entity_id target quando è attiva una whitelist"}
                    for eid in eids:
                        if not any(fnmatch.fnmatch(eid, pat) for pat in allowed_entities):
                            logger.warning("Entity %s blocked by allowed_entities policy", eid)
                            return {"error": f"Entity {eid!r} not permitted by policy"}
                return await self._ha.call_service(domain, service, normalized.data)
            if name == "create_task":
                if self._task_engine is None:
                    return {"error": "TaskEngine not available"}
                for action in inputs.get("actions", []):
                    atype = action.get("type")
                    if atype not in _ALLOWED_TASK_ACTIONS:
                        logger.warning("create_task blocked: action type %r not permitted", atype)
                        return {"error": f"Action type {atype!r} not permitted in tasks"}
                    # ASYMMETRY, deliberate (Task 3 review, minor #7): the
                    # SERVICE of a task action is checked here at CREATION
                    # time, but its ENTITY is not -- an action targeting an
                    # out-of-perimeter entity is accepted here and only
                    # refused later, by `task_engine._run_action`, when the
                    # task actually fires. So the LLM can be told "task
                    # created" for a task that will do nothing.
                    #
                    # It is left this way on purpose: `allowed_entities` is
                    # enforced in exactly ONE place (the executor), and
                    # adding a second enforcement point here would duplicate
                    # the boundary and let the two drift apart -- the very
                    # failure mode this phase exists to avoid. The trade-off
                    # is a worse error message, not a weaker boundary: the
                    # action is still refused before it reaches HA. The
                    # service check below predates this task and is kept
                    # only because removing it would WIDEN what create_task
                    # accepts.
                    if atype == "call_ha_service" and allowed_services is not None:
                        svc_key = f"{action.get('domain', '')}.{action.get('service', '')}"
                        if not any(fnmatch.fnmatch(svc_key, pat) for pat in allowed_services):
                            logger.warning("create_task blocked: action %s not permitted", svc_key)
                            return {"error": f"Action {svc_key} not permitted by policy"}
                return create_task_tool(
                    task_engine=self._task_engine,
                    label=inputs["label"],
                    trigger=inputs["trigger"],
                    actions=inputs["actions"],
                    condition=inputs.get("condition"),
                    one_shot=inputs.get("one_shot", True),
                    agent_id=chatbot_id or "hiris-default",
                    allowed_entities=allowed_entities,
                    allowed_services=allowed_services,
                )
            if name == "list_tasks":
                if self._task_engine is None:
                    return {"error": "TaskEngine not available"}
                return list_tasks_tool(
                    task_engine=self._task_engine,
                    # Shim 3: an external MCP client that learned the old key
                    # ("chatbot_id") must not silently receive an unfiltered list.
                    agent_id=inputs.get("agent_id") or inputs.get("chatbot_id"),
                    status=inputs.get("status"),
                )
            if name == "cancel_task":
                if self._task_engine is None:
                    return {"error": "TaskEngine not available"}
                return cancel_task_tool(
                    task_engine=self._task_engine,
                    task_id=inputs["task_id"],
                )
            if name == "get_calendar_events":
                return await get_calendar_events(
                    self._ha,
                    hours=inputs.get("hours", 24),
                    calendar_entity=inputs.get("calendar_entity"),
                )
            if name == "set_input_helper":
                eid = inputs.get("entity_id", "")
                if "value" not in inputs:
                    return {"error": "Missing required parameter: value"}
                ih_domain = eid.split(".")[0] if "." in eid else ""
                # Same `is not None` semantics as every other check in this
                # file (see the module comment above `_filter_entities`): a
                # perimeter of `[]` must deny set_input_helper too, otherwise
                # this one actuating tool would stay fail-OPEN while
                # call_ha_service/trigger_automation/toggle_automation and
                # the Task executor all read `[]` as "deny".
                if allowed_services is not None and ih_domain:
                    if not any(
                        fnmatch.fnmatch(f"{ih_domain}.turn_on", pat)
                        or fnmatch.fnmatch(f"{ih_domain}.set_value", pat)
                        or fnmatch.fnmatch(f"{ih_domain}.select_option", pat)
                        for pat in allowed_services
                    ):
                        logger.warning("set_input_helper on %r blocked by allowed_services policy", ih_domain)
                        return {"error": f"Domain {ih_domain!r} not permitted by allowed_services policy"}
                if allowed_entities is not None and eid:
                    if not any(fnmatch.fnmatch(eid, pat) for pat in allowed_entities):
                        logger.warning("set_input_helper on %r blocked by allowed_entities policy", eid)
                        return {"error": f"Entity {eid!r} not permitted by policy"}
                if not tier_confirmed:
                    # Fail closed LOCALLY: any non-confirmed actuation must pass
                    # the semaforo. A malformed target or an unresolvable service
                    # returns its error here and NEVER falls through to actuation
                    # -- don't rely on the downstream actuator re-validating (a
                    # future loosening there would silently reopen the bypass).
                    if not ih_domain or not eid:
                        return {"error": f"Invalid entity_id for set_input_helper: {eid!r}"}
                    resolved = resolve_input_helper_service(ih_domain, inputs.get("value"))
                    if not isinstance(resolved, tuple):
                        return resolved if isinstance(resolved, dict) else {
                            "error": f"Cannot resolve input helper service for {ih_domain!r}"}
                    ih_service, _ = resolved
                    gate_result = await self._gate(
                        name=name, inputs=inputs, domain=ih_domain, service=ih_service,
                        entity_ids=[eid], user_id=user_id,
                    )
                    if gate_result is not None:
                        return gate_result
                return await set_input_helper(self._ha, entity_id=eid, value=inputs.get("value"))
            if name == "create_calendar_event":
                return await create_calendar_event(
                    self._ha,
                    calendar_entity=inputs["calendar_entity"],
                    summary=inputs["summary"],
                    event_type=inputs["event_type"],
                    start_date_time=inputs.get("start_date_time"),
                    end_date_time=inputs.get("end_date_time"),
                    start_date=inputs.get("start_date"),
                    end_date=inputs.get("end_date"),
                    description=inputs.get("description"),
                    location=inputs.get("location"),
                )
            if name == "http_request":
                return await http_request(
                    url=inputs["url"],
                    method=inputs.get("method", "GET"),
                    headers=inputs.get("headers"),
                    body=inputs.get("body"),
                    allowed_endpoints=allowed_endpoints,
                )
            if name == "recall_memory":
                if self._knowledge_store is None or self._knowledge_embedder is None:
                    return {"error": "Memory store not configured"}
                return await _handle_recall_memory(
                    self._knowledge_store, self._knowledge_embedder, inputs,
                    owner=user_id or "home",
                    chatbot_id=chatbot_id or "hiris-default",
                )
            if name == "save_memory":
                if self._knowledge_store is None or self._knowledge_embedder is None:
                    return {"error": "Memory store not configured"}
                return await _handle_save_memory(
                    self._knowledge_store, self._knowledge_embedder, inputs,
                    owner=user_id or "home",
                    chatbot_id=chatbot_id or "hiris-default",
                    retention_days=self._memory_retention_days,
                )
            if name == "get_ha_health":
                return get_ha_health(self._health_monitor, inputs.get("sections") or ["all"])
            if name == "get_advisories":
                # `or None`: una severity vuota vale "nessun filtro", non un
                # valore fuori enum da respingere.
                # Il perimetro va passato: l'evidenza delle segnalazioni nomina
                # entita' di tutta la casa, e un bot ristretto alle luci (o un
                # agente reattivo, che ha questo tool fra i suoi) le leggerebbe
                # tutte. Filtrato dentro get_advisories, come per get_logbook.
                return get_advisories(self._advisory_store,
                                      inputs.get("severity") or None,
                                      allowed_entities=allowed_entities)
            if name == "create_automation_proposal":
                # Explicit up-front validation: the LLM's tool call does not
                # hard-guarantee every "required" input_schema key is actually
                # populated (prompt/context compression, model hiccups). Bare
                # inputs[...] access below would raise KeyError and be masked
                # by the blanket except at the bottom of dispatch() as a
                # generic "non riuscito" message the model can't act on.
                # Check up front and return a specific, retriable error instead.
                _required = ("type", "name", "description", "config", "routing_reason")
                _missing = [k for k in _required if k not in inputs]
                if _missing:
                    return {"error": f"Campi obbligatori mancanti: {', '.join(_missing)}"}
                return await create_automation_proposal(
                    self._proposal_store,
                    proposal_type=inputs["type"],
                    name=inputs["name"],
                    description=inputs["description"],
                    config=inputs["config"],
                    routing_reason=inputs["routing_reason"],
                    automation_id=inputs.get("automation_id"),
                )
            if name == "create_ha_config":
                # Le plance non si creano piu' direttamente da qui: devono
                # passare da propose_dashboard e dall'approvazione dell'utente.
                # Il kind 'dashboard' e' sparito dall'input_schema, ma lo schema
                # non e' una garanzia forte (il modello puo' comunque emettere
                # un valore fuori enum): senza questo guard la rimozione
                # sarebbe solo cosmetica e la scrittura diretta resterebbe
                # raggiungibile. normalize_config_inputs/apply_ha_config
                # continuano ad accettare 'dashboard' perche' servono all'apply
                # della proposta (chat e MCP), che e' gia' dietro il gate umano.
                if inputs.get("kind") == "dashboard":
                    return {"error": ("Le plance non si creano con create_ha_config: "
                                      "usa propose_dashboard, che passa "
                                      "dall'approvazione dell'utente.")}
                try:
                    normalized = normalize_config_inputs(inputs)
                except ValueError as exc:
                    return {"error": str(exc)}
                return await apply_ha_config(self._ha, normalized)
            if name == "list_dashboards":
                return await self._ha.list_dashboards()
            if name == "get_dashboard_config":
                return await self._ha.get_lovelace_config(inputs.get("url_path", ""))
            if name == "propose_dashboard":
                return await propose_dashboard(
                    self._proposal_store,
                    inputs.get("mode", ""),
                    inputs.get("url_path", ""),
                    inputs.get("config", {}),
                    inputs.get("reason", ""),
                    title=inputs.get("title"),
                )
            if name == "save_knowledge":
                # Stessa condizione di save_memory/recall_memory: senza store
                # o senza embedder l'elemento non potrebbe MAI essere
                # richiamato (knowledge_store.search filtra su
                # `embedding IS NOT NULL`), quindi salvarlo sarebbe un
                # successo apparente. Qui bastava lo store, e su
                # un'installazione senza provider di embedding il modello
                # rispondeva "salvato" su un ricordo perduto in partenza.
                if self._knowledge_store is None or self._knowledge_embedder is None:
                    return {"error": ("La memoria non è disponibile: non posso "
                                      "salvare questo ricordo perché non "
                                      "potrei più ritrovarlo.")}
                return await handle_save_knowledge(
                    self._knowledge_store, self._knowledge_embedder, inputs,
                    owner=user_id or "home",
                )
            if name == "recall_knowledge" and self._knowledge_store:
                return await handle_recall_knowledge(
                    self._knowledge_store, self._knowledge_embedder, inputs,
                    owner=user_id or "home",
                    chatbot_id=chatbot_id or "hiris-default",
                    allow_sensitive=knowledge_allow_sensitive,
                    kinds=knowledge_kinds,
                    pseudonymizer=self._pseudonymizer,
                    cloud=cloud,
                    pseudonym_map=pseudonym_map,
                )
            if name == "link_knowledge" and self._knowledge_store:
                return await handle_link_knowledge(self._knowledge_store, inputs)
            if name == "daily_briefing":
                # On-demand chat butler summary (Slice 7 Task 5). READ-ONLY: no HA
                # service call, no semaforo — it only reads knowledge_store/entity_cache.
                #
                # allow_sensitive mirrors recall_knowledge's model: the agent config
                # (knowledge_allow_sensitive) AND the current chat backend's locality
                # (cloud) both gate it. Sensitive deadlines are included only when the
                # agent is allowed to see them AND the chat backend is local — fail-closed
                # whenever either signal is missing/False (config disallows OR backend is
                # cloud), same as recall_knowledge. Hidden items are still counted in
                # bundle["counts"]["hidden_sensitive"] regardless.
                #
                # Le batterie scariche arrivano dalle segnalazioni gia' prodotte dai
                # controlli di salute del Brain (advisory_store), non da un calcolo
                # fatto qui: unica fonte di verita', unica soglia. Senza store la
                # sezione resta vuota. Di conseguenza la policy dei rilevatori non
                # viene piu' letta in questo punto.
                #
                # Returns the DETERMINISTIC render_briefing_template(bundle) string,
                # not compose_briefing (which needs an llm_reason this dispatcher
                # lacks) — the chat model, already mid-reply, narrates it itself.
                if self._knowledge_store is None:
                    return "Il maggiordomo non ha accesso alla memoria in questo momento: riprova più tardi."
                try:
                    allow_sensitive = bool(knowledge_allow_sensitive) and not bool(cloud)
                    # On-demand tool: scope to the caller so they see their OWN
                    # private obligations + home ones (review C/#2 follow-up),
                    # unlike the scheduled home-wide broadcast (owner="home").
                    bundle = build_briefing_bundle(
                        self._knowledge_store, self._cache,
                        today=date.today(), allow_sensitive=allow_sensitive,
                        owner=user_id or "home",
                        advisory_store=self._advisory_store,
                    )
                    return render_briefing_template(bundle)
                except Exception as exc:
                    logger.error("daily_briefing failed: %s", exc)
                    return "Non sono riuscito a preparare il resoconto di oggi: riprova più tardi."
            if name == "confirm_pending":
                if self._confirm_executor is None:
                    return {"error": "Conferma non disponibile"}
                code = str(inputs.get("code", "")).strip()
                if not code:
                    return {"error": "Codice mancante."}
                return await self._confirm_executor(code=code, user=user_id)
            logger.warning("Unknown tool: %s", name)
            return {
                "error": (
                    f"Tool '{name}' non esiste. "
                    "Usa ESCLUSIVAMENTE i tool elencati nel system prompt. "
                    "Non inventare nomi di tool."
                )
            }
        except KeyError as exc:
            # Several tool branches build kwargs from bare inputs["..."]
            # access. When the LLM's tool call omits a required key, that
            # raises a KeyError which -- without this arm -- would fall into
            # the blanket except below and come back as the generic "non
            # riuscito" message: no indication of which field was missing,
            # so the model (and therefore the user) can't retry meaningfully.
            # Catch it specifically, name the missing field, and log for
            # diagnosability. Must NOT leak anything beyond the field name.
            missing_field = exc.args[0] if exc.args else str(exc)
            logger.warning("Tool %s missing required field: %s", name, missing_field, exc_info=True)
            return {"error": f"Campo obbligatorio mancante per '{name}': {missing_field}"}
        except Exception:
            # Review L/2: never echo str(exc) back to the caller -- it can
            # leak internal detail (paths, hostnames, connection strings).
            # Log the full detail server-side (with traceback) and return a
            # generic, non-identifying message instead.
            logger.exception("Tool %s failed", name)
            return {"error": f"Strumento '{name}' non riuscito. Riprova più tardi."}
