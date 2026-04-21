# hiris/app/server.py
import asyncio
import logging
import os
from aiohttp import web
from .api.handlers_chat import handle_chat
from .api.handlers_agents import handle_list_agents, handle_create_agent, handle_get_agent, handle_update_agent, handle_delete_agent, handle_run_agent, handle_list_entities
from .api.handlers_status import handle_status
from .api.handlers_config import handle_config
from .api.handlers_usage import handle_usage, handle_reset_usage
from .agent_engine import AgentEngine
from .proxy.ha_client import HAClient
from .proxy.entity_cache import EntityCache
from .proxy.embedding_index import EmbeddingIndex

logger = logging.getLogger(__name__)


async def _on_startup(app: web.Application) -> None:
    from .claude_runner import ClaudeRunner

    ha_client = HAClient(
        base_url=os.environ.get("HA_BASE_URL", "http://supervisor/core"),
        token=os.environ.get("SUPERVISOR_TOKEN", ""),
    )
    await ha_client.start()
    app["ha_client"] = ha_client

    entity_cache = EntityCache()
    try:
        await entity_cache.load(ha_client)
    except Exception as exc:
        logger.warning("EntityCache load failed: %s", exc)
    try:
        await entity_cache.load_area_registry(ha_client)
    except Exception as exc:
        logger.warning("Area registry load failed: %s", exc)
    ha_client.add_state_listener(entity_cache.on_state_changed)
    app["entity_cache"] = entity_cache

    data_path = os.environ.get("AGENTS_DATA_PATH", "/data/agents.json")
    engine = AgentEngine(ha_client=ha_client, data_path=data_path)
    engine.set_entity_cache(entity_cache)  # wire cache before start() opens WebSocket
    await engine.start()
    app["engine"] = engine

    embedding_index = EmbeddingIndex()
    asyncio.create_task(
        embedding_index.build(entity_cache.get_all_useful()),
        name="embedding_index_build",
    )
    app["embedding_index"] = embedding_index

    notify_config = {
        "ha_notify_service": os.environ.get("HA_NOTIFY_SERVICE", "notify.notify"),
        "telegram_token": os.environ.get("TELEGRAM_TOKEN", ""),
        "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
        "retropanel_url": os.environ.get("RETROPANEL_URL", "http://retropanel:8098"),
    }
    app["theme"] = os.environ.get("THEME", "auto")
    api_key = os.environ.get("CLAUDE_API_KEY", "")
    usage_path = os.environ.get("USAGE_DATA_PATH", "/data/usage.json")
    if api_key:
        runner = ClaudeRunner(
            api_key=api_key,
            ha_client=ha_client,
            notify_config=notify_config,
            usage_path=usage_path,
            entity_cache=entity_cache,
            embedding_index=embedding_index,
        )
        app["claude_runner"] = runner
        engine.set_claude_runner(runner)
    else:
        app["claude_runner"] = None


async def _on_cleanup(app: web.Application) -> None:
    await app["engine"].stop()
    await app["ha_client"].stop()


def create_app() -> web.Application:
    app = web.Application()

    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)

    static_path = os.path.join(os.path.dirname(__file__), "static")
    app.router.add_static("/static", static_path, show_index=False)

    app.router.add_get("/", _serve_index)
    app.router.add_get("/config", _serve_config)
    app.router.add_get("/api/health", _handle_health)
    app.router.add_get("/api/status", handle_status)
    app.router.add_get("/api/config", handle_config)
    app.router.add_get("/api/usage", handle_usage)
    app.router.add_post("/api/usage/reset", handle_reset_usage)
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_get("/api/agents", handle_list_agents)
    app.router.add_post("/api/agents", handle_create_agent)
    app.router.add_get("/api/agents/{agent_id}", handle_get_agent)
    app.router.add_put("/api/agents/{agent_id}", handle_update_agent)
    app.router.add_delete("/api/agents/{agent_id}", handle_delete_agent)
    app.router.add_post("/api/agents/{agent_id}/run", handle_run_agent)
    app.router.add_get("/api/entities", handle_list_entities)

    return app


async def _serve_index(request: web.Request) -> web.Response:
    path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if not os.path.exists(path):
        return web.Response(text="UI not yet available", status=503)
    return web.FileResponse(path)


async def _serve_config(request: web.Request) -> web.Response:
    path = os.path.join(os.path.dirname(__file__), "static", "config.html")
    if not os.path.exists(path):
        return web.Response(text="UI not yet available", status=503)
    return web.FileResponse(path)


async def _handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "version": "0.1.5"})
