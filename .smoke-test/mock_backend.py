"""
HIRIS mock backend per smoke test Playwright.
Serve static files da hiris/app/static/ + endpoint mock con fixture JSON.
Bind 127.0.0.1:8765.
"""
import json
import os
from pathlib import Path
from aiohttp import web

ROOT = Path(__file__).resolve().parent.parent / "hiris" / "app" / "static"

# ── Fixture data (rappresentativa dei dati reali) ─────────────────────────────

AGENTS = [
    {
        "id": "f020edde-8550-4f97-9523-157ecac980e6",
        "name": "IRRIGAZIONE",
        "type": "agent",
        "enabled": True,
        "is_default": False,
        "model": "openrouter:gemma2:e4b",
        "max_tokens": 4096,
        "thinking_budget": 0,
        "response_mode": "auto",
        "restrict_to_home": False,
        "require_confirmation": False,
        "max_chat_turns": 0,
        "system_prompt": "Valuta se e quanto irrigare oggi. Controlla precipitazioni recenti…",
        "strategic_context": "ZONE: prato nord (valve.irrigazione_nord), aiuole (valve.aiuole)…",
        "triggers": [{"type": "cron", "cron": "0 5 * * *"}],
        "states": ["SKIP", "LEGGERA", "PIENA"],
        "action_mode": "configured",
        "rules": [{"states": ["LEGGERA", "PIENA"], "actions": []}],
        "allowed_tools": ["get_entity_states", "get_weather_forecast", "create_task"],
        "allowed_entities": ["valve.*", "switch.irrigazione_*"],
        "allowed_services": ["valve.*", "switch.*"],
        "execution_log": [
            {
                "timestamp": "2026-05-07T14:23:00Z",
                "success": True,
                "eval_status": "SKIP",
                "result_summary": "Pioggia recente 12mm — irrigazione non necessaria oggi.",
                "tool_calls": ["get_weather_forecast", "get_entity_states"],
                "input_tokens": 1234,
                "output_tokens": 567,
                "cost_eur": 0.0042,
            },
            {
                "timestamp": "2026-05-06T05:00:00Z",
                "success": True,
                "eval_status": "PIENA",
                "result_summary": "Nessuna pioggia 72h, suolo asciutto. Programmate 25min/zona.",
                "tool_calls": ["get_weather_forecast"],
                "action_taken": "create_task valve.open + delay 25min + valve.close",
                "input_tokens": 1800,
                "output_tokens": 420,
                "cost_eur": 0.0061,
            },
        ],
        "usage": {"requests": 47, "input_tokens": 84230, "output_tokens": 18920, "cost_eur": 0.31},
        "budget_eur_limit": 5.00,
    },
    {
        "id": "hiris-default",
        "name": "HIRIS",
        "type": "chat",
        "enabled": True,
        "is_default": True,
        "model": "auto",
        "max_tokens": 4096,
        "thinking_budget": 4096,
        "response_mode": "compact",
        "restrict_to_home": True,
        "require_confirmation": False,
        "max_chat_turns": 50,
        "system_prompt": "Sei l'assistente smart home della famiglia. Rispondi conciso.",
        "strategic_context": "Casa: 2 adulti…",
        "triggers": [],
        "states": ["OK", "ATTENZIONE", "ANOMALIA"],
        "action_mode": "automatic",
        "rules": [],
        "allowed_tools": ["get_entity_states", "get_home_status", "search_entities"],
        "allowed_entities": [],
        "allowed_services": [],
        "execution_log": [],
        "usage": {"requests": 247, "input_tokens": 412300, "output_tokens": 89200, "cost_eur": 0.84},
    },
    {
        "id": "monitor-energia-001",
        "name": "Monitor energia",
        "type": "agent",
        "enabled": True,
        "is_default": False,
        "model": "claude-sonnet-4-7",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "execution_log": [
            {"timestamp": "2026-05-07T14:00:00Z", "success": True, "eval_status": "OK",
             "result_summary": "Consumo 2.3 kWh, sotto soglia.", "input_tokens": 1100, "output_tokens": 220},
        ],
    },
    {
        "id": "chat-openrouter-002",
        "name": "Chat open router",
        "type": "chat",
        "enabled": False,
        "is_default": False,
        "model": "openrouter:google/gemma-4-31b-it:free",
        "triggers": [],
        "execution_log": [],
    },
]

PROPOSALS = [
    {"id": "prop-001", "name": "Spegnimento riscaldamento notte", "type": "ha_automation",
     "description": "Suggerito alle 23:00 quando temperature soggiorno >19°C",
     "routing_reason": "pattern detected da Monitor energia",
     "created_at": "2026-05-06T22:14:00Z", "status": "pending"},
    {"id": "prop-002", "name": "Notifica vento >30 km/h", "type": "ha_automation",
     "description": "Soglia di sicurezza per esposizione sud",
     "routing_reason": "pattern detected da Vento e tapparelle",
     "created_at": "2026-05-05T15:42:00Z", "status": "pending"},
]

TASKS = [
    {"id": "task-001", "label": "Open valve nord", "agent_id": "f020edde-8550-4f97-9523-157ecac980e6",
     "created_at": "2026-05-07T05:00:00Z", "trigger": {"type": "delay", "minutes": 0},
     "actions": [{"type": "call_service", "domain": "valve", "service": "open_valve"}],
     "status": "executed", "executed_at": "2026-05-07T05:00:02Z", "one_shot": True},
    {"id": "task-002", "label": "Close valve nord", "agent_id": "f020edde-8550-4f97-9523-157ecac980e6",
     "created_at": "2026-05-07T05:00:00Z", "trigger": {"type": "delay", "minutes": 25},
     "actions": [{"type": "call_service", "domain": "valve", "service": "close_valve"}],
     "status": "pending", "one_shot": True},
    {"id": "task-003", "label": "Failed example", "agent_id": "monitor-energia-001",
     "created_at": "2026-05-06T22:14:00Z", "trigger": {"type": "absolute_time", "iso": "2026-05-07T05:00:00Z"},
     "actions": [], "status": "failed", "error": "Service call failed: timeout", "one_shot": True},
]

ENTITIES = [
    {"id": "binary_sensor.porta_ingresso", "name": "Porta ingresso"},
    {"id": "binary_sensor.porta_garage", "name": "Porta garage"},
    {"id": "binary_sensor.finestra_camera", "name": "Finestra camera"},
    {"id": "light.salotto", "name": "Luce salotto"},
    {"id": "light.cucina", "name": "Luce cucina"},
    {"id": "light.camera_letto", "name": "Luce camera letto"},
    {"id": "switch.irrigazione_nord", "name": "Irrigazione nord"},
    {"id": "switch.irrigazione_sud", "name": "Irrigazione sud"},
    {"id": "valve.irrigazione_nord", "name": "Valvola nord"},
    {"id": "sensor.temperatura_soggiorno", "name": "Temperatura soggiorno"},
    {"id": "sensor.consumo_totale_w", "name": "Consumo totale W"},
    {"id": "climate.soggiorno", "name": "Termostato soggiorno"},
    {"id": "person.paolo", "name": "Paolo"},
]

MODELS = {
    "providers": [
        {"label": "Anthropic", "models": [
            {"id": "claude-sonnet-4-7", "label": "Claude Sonnet 4.7"},
            {"id": "claude-haiku-4-5", "label": "Claude Haiku 4.5"},
            {"id": "claude-opus-4-7", "label": "Claude Opus 4.7"},
        ]},
        {"label": "OpenAI", "models": [
            {"id": "gpt-4o-mini", "label": "GPT-4o mini"},
        ]},
        {"label": "OpenRouter", "models": [
            {"id": "openrouter:google/gemma-4-31b-it:free", "label": "Gemma 4 31B (free)"},
            {"id": "openrouter:gemma2:e4b", "label": "Gemma 2 E4B"},
        ]},
        {"label": "Ollama (locale)", "models": [
            {"id": "gemma2:e4b", "label": "gemma2:e4b"},
        ]},
    ]
}

USAGE = {"total_requests": 294, "total_input_tokens": 496530, "total_output_tokens": 108120,
         "total_cost_eur": 1.15, "executions_24h": 23, "tokens_today": 12400, "cost_eur_month": 1.15}


# ── Endpoints ─────────────────────────────────────────────────────────────────

async def list_agents(req):
    return web.json_response(AGENTS)

async def get_agent(req):
    aid = req.match_info["id"]
    a = next((x for x in AGENTS if x["id"] == aid), None)
    if not a:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response(a)

async def update_agent(req):
    aid = req.match_info["id"]
    a = next((x for x in AGENTS if x["id"] == aid), None)
    if not a:
        return web.json_response({"error": "Not found"}, status=404)
    body = await req.json()
    a.update(body)
    return web.json_response(a)

async def list_proposals(req):
    status = req.rel_url.query.get("status")
    items = [p for p in PROPOSALS if not status or p["status"] == status]
    return web.json_response({"proposals": items})

async def list_tasks(req):
    status = req.rel_url.query.get("status")
    items = [t for t in TASKS if not status or status == "all" or t["status"] == status]
    return web.json_response(items)

async def get_usage(req):
    return web.json_response(USAGE)

async def get_models(req):
    return web.json_response(MODELS)

async def get_entities(req):
    q = (req.rel_url.query.get("q") or "").lower()
    items = [e for e in ENTITIES if q in e["id"].lower() or q in e["name"].lower()]
    return web.json_response(items)

async def run_agent(req):
    aid = req.match_info["id"]
    return web.json_response({
        "result": f"[Mock run for {aid}]\n✓ Simulazione test run completata\nValutazione: OK\nTokens: 1234↓ / 567↑",
        "eval_status": "OK",
    })

async def get_agent_usage(req):
    aid = req.match_info["id"]
    a = next((x for x in AGENTS if x["id"] == aid), None)
    return web.json_response(a.get("usage", {}) if a else {})


def build_app():
    app = web.Application()
    app.router.add_get("/api/agents", list_agents)
    app.router.add_get("/api/agents/{id}", get_agent)
    app.router.add_put("/api/agents/{id}", update_agent)
    app.router.add_post("/api/agents", update_agent)  # create same shape
    app.router.add_post("/api/agents/{id}/run", run_agent)
    app.router.add_delete("/api/agents/{id}", lambda r: web.Response(status=204))
    app.router.add_get("/api/agents/{id}/usage", get_agent_usage)
    app.router.add_get("/api/proposals", list_proposals)
    app.router.add_post("/api/proposals/{id}/apply", lambda r: web.Response(status=204))
    app.router.add_post("/api/proposals/{id}/reject", lambda r: web.Response(status=204))
    app.router.add_get("/api/tasks", list_tasks)
    app.router.add_delete("/api/tasks/{id}", lambda r: web.Response(status=204))
    app.router.add_get("/api/usage", get_usage)
    app.router.add_get("/api/models", get_models)
    app.router.add_get("/api/entities", get_entities)
    # Static — config.html cerca asset sotto "static/..." quindi mountiamo
    # ROOT su /static e duplichiamo i file top-level (config.html, index.html)
    # come route esplicite.
    async def serve_html(name):
        async def handler(r):
            return web.FileResponse(str(ROOT / name))
        return handler
    app.router.add_get("/", lambda r: web.HTTPFound("/config.html"))
    app.router.add_get("/config", lambda r: web.HTTPFound("/config.html"))
    app.router.add_get("/config.html", lambda r: web.FileResponse(str(ROOT / "config.html")))
    app.router.add_get("/index.html", lambda r: web.FileResponse(str(ROOT / "index.html")))
    app.router.add_static("/static", str(ROOT), show_index=False)
    return app


if __name__ == "__main__":
    web.run_app(build_app(), host="127.0.0.1", port=8765, print=lambda *a, **kw: None)
