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

from aiohttp import web

logger = logging.getLogger(__name__)

# Read tools are always available to the gateway (non-destructive).
READ_TOOLS = ["get_home_status", "get_area_entities", "get_entity_states", "recall_knowledge"]

# Canonical categories shown in the UI, with friendly Italian labels and the HA
# domain they map to. Order is the display order.
GATEWAY_CATEGORIES = [
    {"id": "light", "label": "Luci", "domain": "light"},
    {"id": "scene", "label": "Scene", "domain": "scene"},
    {"id": "climate", "label": "Climatizzazione", "domain": "climate"},
    {"id": "cover", "label": "Tapparelle / Tende", "domain": "cover"},
    {"id": "media_player", "label": "Media / TV", "domain": "media_player"},
    {"id": "switch", "label": "Interruttori / Prese", "domain": "switch"},
    {"id": "fan", "label": "Ventilazione", "domain": "fan"},
    {"id": "vacuum", "label": "Aspirapolvere", "domain": "vacuum"},
    {"id": "lock", "label": "Serrature", "domain": "lock"},
    {"id": "alarm_control_panel", "label": "Allarme", "domain": "alarm_control_panel"},
    {"id": "script", "label": "Script", "domain": "script"},
]

_VALID_LEVELS = frozenset({"green", "yellow", "red", "off"})
_BY_ID = {c["id"]: c for c in GATEWAY_CATEGORIES}


def _policy_path(data_dir: str) -> str:
    return os.path.join(data_dir, "gateway_policy.json")


def load_categories(data_dir: str) -> dict:
    """Load the saved {category_id: level} map (empty/default = all off)."""
    path = _policy_path(data_dir)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        cats = data.get("categories", {})
        return {k: v for k, v in cats.items() if k in _BY_ID and v in _VALID_LEVELS}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.warning("gateway_policy.json unreadable (%s) — treating as empty", exc)
        return {}


def save_categories(data_dir: str, categories: dict) -> dict:
    """Validate and persist the category map; returns the cleaned map."""
    clean = {k: v for k, v in categories.items() if k in _BY_ID and v in _VALID_LEVELS}
    path = _policy_path(data_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "categories": clean}, fh)
    os.replace(tmp, path)
    return clean


def derive_execute_policy(categories: dict) -> dict:
    """Translate the category map into the execute-API policy. v1: only 'green'
    categories are executable; their domain becomes a service/entity glob."""
    green_domains = [
        _BY_ID[cid]["domain"]
        for cid, level in categories.items()
        if level == "green" and cid in _BY_ID
    ]
    tools = list(READ_TOOLS)
    services: list[str] = []
    entities: list[str] = []
    if green_domains:
        tools.append("call_ha_service")
        for dom in green_domains:
            services.append(dom + ".*")
            entities.append(dom + ".*")
    return {
        "tools": tools,
        "allowed_services": services or None,
        "allowed_entities": entities or None,
    }


def apply_saved_policy(app: web.Application) -> None:
    """If a UI-managed policy file exists, derive and set the execute policy
    (overriding the env CSV). Called at startup and after each save. Mutates the
    existing dict in place so it works at request time too — aiohttp forbids
    reassigning app[key] after the app has started."""
    data_dir = app.get("data_dir") or "/data"
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
    return web.json_response({
        "categories": GATEWAY_CATEGORIES,
        "levels": cats,                       # {category_id: level} (missing = off)
        "valid_levels": sorted(_VALID_LEVELS),
    })


async def handle_save_gateway_policy(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON body"}, status=400)
    cats = body.get("levels") or body.get("categories") or {}
    if not isinstance(cats, dict):
        return web.json_response({"error": "levels must be an object"}, status=400)
    data_dir = request.app.get("data_dir") or "/data"
    clean = save_categories(data_dir, cats)
    apply_saved_policy(request.app)
    return web.json_response({"ok": True, "levels": clean,
                             "execute_policy": request.app.get("execute_policy")})
