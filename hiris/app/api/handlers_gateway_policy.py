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
              "get_history", "recall_knowledge", "get_automation_config"]

# Propose / schedule tools the gateway may always reach (non-destructive).
# create_task is intentionally excluded: when confirm_actions=false the gateway
# does NOT hold it, so exposing it without green domains would leave its
# call_ha_service actions unconstrained. It is added in derive_execute_policy
# only when at least one green domain exists (allowed_services is then set).
PROPOSE_TOOLS = ["create_automation_proposal", "save_knowledge", "list_tasks",
                 "cancel_task"]

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
DEFAULT_NOTIFY_SERVICE = "notify.iphone_bet"
_SERVICE_RE = re.compile(r"^notify\.[A-Za-z0-9_]{1,64}$")


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


def load_settings(data_dir: str) -> dict:
    s = _read_full(data_dir).get("settings", {})
    svc = s.get("notify_service")
    if not (isinstance(svc, str) and _SERVICE_RE.match(svc)):
        svc = DEFAULT_NOTIFY_SERVICE
    return {"notify_service": svc}


def save_categories(data_dir: str, categories: dict, settings: dict | None = None) -> dict:
    """Validate and persist the category map (preserving/updating settings)."""
    clean = {k: v for k, v in categories.items() if k in _BY_ID and v in _VALID_LEVELS}
    full = _read_full(data_dir)
    full["version"] = 1
    full["categories"] = clean
    if settings is not None:
        svc = settings.get("notify_service")
        full.setdefault("settings", {})
        if isinstance(svc, str) and _SERVICE_RE.match(svc):
            full["settings"]["notify_service"] = svc
    _write_full(data_dir, full)
    return clean


def derive_execute_policy(categories: dict) -> dict:
    """Translate the category map into the execute-API policy.

    - green: the domain is directly executable (its glob is whitelisted).
    - yellow/red: the domain is *requestable* but held for approval (carried in
      ``tiers`` so the execute-API can route it), not in the green whitelist.
    - off/missing: not reachable at all.
    """
    tiers: dict = {}
    green_domains: list[str] = []
    actionable = False
    for cid, level in categories.items():
        if cid not in _BY_ID or level not in ("green", "yellow", "red"):
            continue
        dom = _BY_ID[cid]["domain"]
        tiers[dom] = level
        actionable = True
        if level == "green":
            green_domains.append(dom)
    tools = list(READ_TOOLS) + list(PROPOSE_TOOLS)
    if actionable:
        tools.append("call_ha_service")  # requestable; the handler routes by tier
        tools.append("create_task")      # only when green domains constrain its actions
    services = [d + ".*" for d in green_domains]
    entities = [d + ".*" for d in green_domains]
    return {
        "tools": tools,
        "allowed_services": services or None,
        "allowed_entities": entities or None,
        "tiers": tiers,
    }


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
    holder["notify_service"] = load_settings(data_dir)["notify_service"]
    cats = load_categories(data_dir)
    if not cats:
        return
    derived = derive_execute_policy(cats)
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
    categories = [
        dict(c, count=int(counts.get(c["domain"], 0))) for c in GATEWAY_CATEGORIES
    ]
    return web.json_response({
        "categories": categories,
        "levels": cats,                       # {category_id: level} (missing = off)
        "valid_levels": sorted(_VALID_LEVELS),
        "settings": load_settings(data_dir),  # {"notify_service": ...}
    })


async def handle_save_gateway_policy(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON body"}, status=400)
    cats = body.get("levels") or body.get("categories") or {}
    if not isinstance(cats, dict):
        return web.json_response({"error": "levels must be an object"}, status=400)
    settings = body.get("settings") if isinstance(body.get("settings"), dict) else None
    data_dir = request.app.get("data_dir") or "/data"
    clean = save_categories(data_dir, cats, settings)
    apply_saved_policy(request.app)
    return web.json_response({"ok": True, "levels": clean,
                             "settings": load_settings(data_dir),
                             "execute_policy": request.app.get("execute_policy")})
