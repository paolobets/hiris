"""Gateway access policy — UI-managed, per-category.

Lets the user pick, from the HIRIS web UI, which categories of devices the MCP
gateway (Claude) may control, instead of editing CSV globs in the add-on
options. v1 supports two levels per category: ``green`` (allowed) and ``off``
(not allowed). ``yellow``/``red`` are accepted and persisted but, in v1, treated
as not-allowed for execution (their notification/confirmation flows arrive in
v2). The derived policy feeds the same ``execute_policy`` the execute-API
already enforces.
"""
from __future__ import annotations

import json
import logging
import os
import re

from aiohttp import web

logger = logging.getLogger(__name__)

# Read tools are always available to the gateway (non-destructive).
READ_TOOLS = ["get_home_status", "get_area_entities", "get_entity_states",
              "get_history", "recall_memory", "get_automation_config",
              "get_advisories", "get_logbook"]
# render_template resta FUORI da questa lista. Questa lista non e' un menu:
# derive_execute_policy la concede SEMPRE e per intero, senza opt-in per singolo
# tool, e le letture partono con allowed_entities=None (handlers_execute: "reads
# see the whole home"). Il perimetro delle letture remote lo fornisce ora la
# denylist di lettura (api/read_denylist.py), che rifiuta le richieste che nominano
# un'entita' coperta e POTA le risposte -- quindi copre anche il caso del
# parametro omesso. E' per questo che get_logbook e' rientrato: la sua
# enumerazione in blocco della cronologia non e' piu' illimitata.
# render_template no: un template non offre alcun entity_id da filtrare, quindi
# la denylist non avrebbe presa e nessun perimetro potrebbe contenerlo.
# Contenimento della superficie remota, non limite tecnico: gira gia' nel
# dispatcher, riabilitarlo sarebbe una riga qui (e una in mcp/tiers.py). In chat
# e agli agenti locali e' pienamente disponibile — vedi claude_runner.py.

# Propose / schedule tools the gateway may always reach (non-destructive).
# create_task is intentionally excluded: when confirm_actions=false the gateway
# does NOT hold it, so exposing it without green domains would leave its
# call_ha_service actions unconstrained. It is added in derive_execute_policy
# only when at least one green domain exists (allowed_services is then set).
PROPOSE_TOOLS = ["create_automation_proposal", "save_memory", "list_tasks",
                 "cancel_task", "create_ha_config"]

# Canonical categories shown in the UI, with friendly Italian labels and the HA
# domain they map to. Order is the display order.
GATEWAY_CATEGORIES = [
    {"id": "light", "label": "Luci", "domain": "light"},
    {"id": "scene", "label": "Scene", "domain": "scene"},
    {"id": "script", "label": "Script", "domain": "script"},
    {"id": "climate", "label": "Climatizzazione", "domain": "climate"},
    {"id": "cover", "label": "Tapparelle / Tende", "domain": "cover"},
    {"id": "media_player", "label": "Media / TV", "domain": "media_player"},
    {"id": "switch", "label": "Interruttori / Prese", "domain": "switch"},
    {"id": "fan", "label": "Ventilazione", "domain": "fan"},
    {"id": "vacuum", "label": "Aspirapolvere", "domain": "vacuum"},
    {"id": "humidifier", "label": "Umidificatori", "domain": "humidifier"},
    {"id": "water_heater", "label": "Scaldabagno", "domain": "water_heater"},
    {"id": "valve", "label": "Valvole", "domain": "valve"},
    {"id": "siren", "label": "Sirene", "domain": "siren"},
    {"id": "lawn_mower", "label": "Tagliaerba", "domain": "lawn_mower"},
    {"id": "select", "label": "Selettori", "domain": "select"},
    {"id": "number", "label": "Valori numerici", "domain": "number"},
    {"id": "button", "label": "Pulsanti", "domain": "button"},
    {"id": "input_boolean", "label": "Interruttori virtuali", "domain": "input_boolean"},
    {"id": "automation", "label": "Automazioni HA", "domain": "automation"},
    {"id": "remote", "label": "Telecomandi", "domain": "remote"},
    {"id": "lock", "label": "Serrature", "domain": "lock"},
    {"id": "alarm_control_panel", "label": "Allarme", "domain": "alarm_control_panel"},
]

_VALID_LEVELS = frozenset({"green", "yellow", "red", "off"})
_BY_ID = {c["id"]: c for c in GATEWAY_CATEGORIES}
DEFAULT_NOTIFY_SERVICE = "notify.persistent_notification"
_SERVICE_RE = re.compile(r"^notify\.[A-Za-z0-9_]{1,64}$")
_ENTITY_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")


def _policy_path(data_dir: str) -> str:
    return os.path.join(data_dir, "gateway_policy.json")


def _read_full(data_dir: str) -> dict:
    try:
        with open(_policy_path(data_dir), encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.warning("gateway_policy.json unreadable (%s) — treating as empty", exc)
        return {}


def _write_full(data_dir: str, data: dict) -> None:
    path = _policy_path(data_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def load_categories(data_dir: str) -> dict:
    """Load the saved {category_id: level} map (empty/default = all off)."""
    cats = _read_full(data_dir).get("categories", {})
    return {k: v for k, v in cats.items() if k in _BY_ID and v in _VALID_LEVELS}


def load_entities(data_dir: str) -> dict:
    """Load {entity_id: level} per-entity overrides (validated)."""
    ents = _read_full(data_dir).get("entities", {})
    if not isinstance(ents, dict):
        return {}
    return {k: v for k, v in ents.items()
            if isinstance(k, str) and _ENTITY_RE.match(k) and v in _VALID_LEVELS}


def load_settings(data_dir: str) -> dict:
    s = _read_full(data_dir).get("settings", {})
    svc = s.get("notify_service")
    if not (isinstance(svc, str) and _SERVICE_RE.match(svc)):
        svc = DEFAULT_NOTIFY_SERVICE
    users = s.get("notify_users")
    if not isinstance(users, dict):
        users = {}
    users = {k: v for k, v in users.items()
             if isinstance(k, str) and isinstance(v, str) and _SERVICE_RE.match(v)}
    return {"notify_service": svc, "notify_users": users}


def save_categories(data_dir: str, categories: dict, settings: dict | None = None,
                    entities: dict | None = None) -> dict:
    """Validate and persist the category map (+ optional per-entity overrides, settings)."""
    clean = {k: v for k, v in categories.items() if k in _BY_ID and v in _VALID_LEVELS}
    full = _read_full(data_dir)
    full["version"] = 2
    full["categories"] = clean
    if entities is not None:
        full["entities"] = {k: v for k, v in entities.items()
                            if isinstance(k, str) and _ENTITY_RE.match(k) and v in _VALID_LEVELS}
    if settings is not None:
        svc = settings.get("notify_service")
        full.setdefault("settings", {})
        if isinstance(svc, str) and _SERVICE_RE.match(svc):
            full["settings"]["notify_service"] = svc
        users = settings.get("notify_users")
        if isinstance(users, dict):
            full["settings"]["notify_users"] = {
                k: v for k, v in users.items()
                if isinstance(k, str) and isinstance(v, str) and _SERVICE_RE.match(v)
            }
    _write_full(data_dir, full)
    return clean


def effective_tier(entity_id: str, tiers: dict, entity_tiers: dict) -> str:
    """Effective tier of a target entity: a per-entity override beats the domain
    level; unconfigured domains default to 'off' (fail-closed)."""
    if entity_id in entity_tiers:
        return entity_tiers[entity_id]
    dom = entity_id.split(".", 1)[0] if "." in entity_id else ""
    return tiers.get(dom, "off")


def derive_execute_policy(categories: dict, entities: dict | None = None) -> dict:
    """Translate the category map (+ optional per-entity overrides) into the execute-API policy.

    - green: the domain is directly executable (its glob is whitelisted).
    - yellow/red: the domain is *requestable* but held for approval (carried in
      ``tiers`` so the execute-API can route it), not in the green whitelist.
    - off/missing: not reachable at all.
    Per-entity overrides in ``entities`` ({entity_id: level}) beat the domain level.
    """
    entities = entities or {}
    tiers: dict = {}
    entity_tiers: dict = {}
    green_domains: list[str] = []
    green_entities: list[str] = []
    actionable = False
    for cid, level in categories.items():
        if cid not in _BY_ID or level not in ("green", "yellow", "red"):
            continue
        dom = _BY_ID[cid]["domain"]
        tiers[dom] = level
        actionable = True
        if level == "green":
            green_domains.append(dom)
    for eid, level in entities.items():
        if not (isinstance(eid, str) and _ENTITY_RE.match(eid)) or level not in _VALID_LEVELS:
            continue
        entity_tiers[eid] = level
        if level in ("green", "yellow", "red"):
            actionable = True
        if level == "green":
            green_entities.append(eid)
    tools = list(READ_TOOLS) + list(PROPOSE_TOOLS)
    if actionable:
        tools.append("call_ha_service")  # requestable; the handler routes by tier
        tools.append("create_task")      # only when green domains/entities constrain its actions
    # allowed_services: green domains' services + the domain-services of green entities.
    services = [d + ".*" for d in green_domains] + [e.split(".", 1)[0] + ".*" for e in green_entities]
    # allowed_entities: green domains' glob + the specific green entity ids.
    allowed_entities = [d + ".*" for d in green_domains] + list(green_entities)
    return {
        "tools": tools,
        "allowed_services": services or None,
        "allowed_entities": allowed_entities or None,
        "tiers": tiers,
        "entity_tiers": entity_tiers,
    }


def notify_service_for_user(app, user: str | None) -> str:
    """Resolve the notify service for a given HA user_id: the per-user mapping
    (``gateway_settings.notify_users``) if present and valid, else the global
    ``notify_service``, else the hard default."""
    gs = app.get("gateway_settings") or {}
    users = gs.get("notify_users") or {}
    svc = users.get(user) if user else None
    if isinstance(svc, str) and _SERVICE_RE.match(svc):
        return svc
    glob = gs.get("notify_service")
    return glob if isinstance(glob, str) and _SERVICE_RE.match(glob) else DEFAULT_NOTIFY_SERVICE


def apply_saved_policy(app: web.Application) -> None:
    """If a UI-managed policy file exists, derive and set the execute policy
    (overriding the env CSV). Called at startup and after each save. Mutates the
    existing dict in place so it works at request time too — aiohttp forbids
    reassigning app[key] after the app has started."""
    data_dir = app.get("data_dir") or "/data"
    # Notify service for the approval flow (always applied). Mutate a dict holder
    # in place so it works at request time (aiohttp forbids app[key]= after start).
    holder = app.get("gateway_settings")
    if not isinstance(holder, dict):
        app["gateway_settings"] = holder = {}
    settings = load_settings(data_dir)
    holder["notify_service"] = settings["notify_service"]
    holder["notify_users"] = settings["notify_users"]
    cats = load_categories(data_dir)
    ents = load_entities(data_dir)
    if not cats and not ents:
        return
    derived = derive_execute_policy(cats, ents)
    existing = app.get("execute_policy")
    if isinstance(existing, dict):
        existing.clear()
        existing.update(derived)
    else:
        app["execute_policy"] = derived
    logger.info("Gateway execute-policy loaded from UI policy (%d categories)", len(cats))


async def handle_get_gateway_policy(request: web.Request) -> web.Response:
    data_dir = request.app.get("data_dir") or "/data"
    cats = load_categories(data_dir)
    # Per-category entity count from the live cache, so the UI can show how many
    # devices each category has (and grey out the empty ones).
    counts: dict = {}
    cache = request.app.get("entity_cache")
    if cache is not None:
        try:
            counts = cache.domain_counts()
        except Exception:
            counts = {}
    # Lazy import: security.semaphore imports effective_tier FROM this module
    # at load time (see handle_autonomy_summary above) -- importing at module
    # scope here would create an import cycle.
    #
    # "dangerous" e' calcolato qui, non ricopiato lato frontend (era duplicato
    # a mano in gateway-route.js, con "garage_door" che non e' nemmeno una
    # categoria valida -- vedi GATEWAY_CATEGORIES sopra): un'unica fonte,
    # cosi' un domani DANGEROUS_DOMAINS cambia senza che l'avviso a schermo
    # possa disallinearsi (stesso principio di summarize_autonomy).
    from ..security.semaphore import DANGEROUS_DOMAINS
    categories = [
        dict(c, count=int(counts.get(c["domain"], 0)),
             dangerous=c["domain"] in DANGEROUS_DOMAINS)
        for c in GATEWAY_CATEGORIES
    ]
    return web.json_response({
        "categories": categories,
        "levels": cats,                       # {category_id: level} (missing = off)
        "valid_levels": sorted(_VALID_LEVELS),
        "settings": load_settings(data_dir),  # {"notify_service": ...}
        "entities": load_entities(data_dir),  # {entity_id: level} overrides
    })


async def handle_autonomy_summary(request: web.Request) -> web.Response:
    """Read-only: per-entity/pattern tier counts for the Chatbot editor's
    Autonomia summary (config/chatbot-editor.js::renderAutonomiaSummary).

    Backend is the single authority here on purpose (review finding, SP-4
    Fase B Task 4): the summary used to recompute the tier client-side,
    mirroring ``effective_tier`` but WITHOUT the ``DANGEROUS_DOMAINS``
    denylist ``security.semaphore.gate_action`` always applies on top (lock/
    alarm_control_panel/cover/siren/garage_door — "difesa in profondità").
    That let the UI show a domain like ``cover`` as green while
    ``gate_action`` would always ``deny_dangerous`` it — display-only (no
    security hole, enforcement itself was untouched) but actively
    misinformed the user about the Chatbot's real autonomy in exactly the
    highest-stakes domains. Computing the summary here, with the exact same
    ``summarize_autonomy`` (which itself reuses ``effective_tier`` and
    ``DANGEROUS_DOMAINS``) that real enforcement is built from, makes that
    class of drift structurally impossible: one implementation, not two kept
    in sync by hand.
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON body"}, status=400)
    entities = body.get("entities")
    if not isinstance(entities, list):
        return web.json_response({"error": "entities must be a list"}, status=400)
    entities = [e for e in entities if isinstance(e, str)][:2000]
    data_dir = request.app.get("data_dir") or "/data"
    cats = load_categories(data_dir)
    tiers = {_BY_ID[cid]["domain"]: level for cid, level in cats.items() if cid in _BY_ID}
    entity_tiers = load_entities(data_dir)
    # Lazy import: security.semaphore imports effective_tier FROM this module
    # at module load time, so importing summarize_autonomy at module scope
    # here would create an import cycle.
    from ..security.semaphore import summarize_autonomy
    counts = summarize_autonomy(entities, tiers, entity_tiers)
    return web.json_response({"counts": counts, "total": len(entities)})


async def handle_save_gateway_policy(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON body"}, status=400)
    cats = body.get("levels") or body.get("categories") or {}
    if not isinstance(cats, dict):
        return web.json_response({"error": "levels must be an object"}, status=400)
    settings = body.get("settings") if isinstance(body.get("settings"), dict) else None
    ents = body.get("entities") if isinstance(body.get("entities"), dict) else None
    data_dir = request.app.get("data_dir") or "/data"
    clean = save_categories(data_dir, cats, settings, entities=ents)
    apply_saved_policy(request.app)
    return web.json_response({"ok": True, "levels": clean,
                             "settings": load_settings(data_dir),
                             "execute_policy": request.app.get("execute_policy")})
