# hiris/app/server.py
import asyncio
import logging
import os
from aiohttp import web
from .api.handlers_chat import handle_chat
from .api.handlers_agents import (
    handle_list_agents, handle_create_agent, handle_get_agent,
    handle_update_agent, handle_delete_agent, handle_run_agent,
    handle_list_entities, handle_get_agent_usage, handle_reset_agent_usage,
    handle_context_preview,
)
from .api.handlers_status import handle_status
from .api.handlers_config import handle_config
from .api.handlers_usage import handle_usage, handle_reset_usage
from .api.handlers_chat_history import handle_get_chat_history, handle_clear_chat_history
from .api.handlers_tasks import handle_list_tasks, handle_get_task, handle_cancel_task
from .agent_engine import AgentEngine
from .task_engine import TaskEngine
from .proxy.ha_client import HAClient
from .proxy.entity_cache import EntityCache
from .proxy.knowledge_db import KnowledgeDB
from .proxy.semantic_context_map import SemanticContextMap

logger = logging.getLogger(__name__)


async def _on_startup(app: web.Application) -> None:
    from .claude_runner import ClaudeRunner
    from .proxy.semantic_map import SemanticMap
    from .llm_router import LLMRouter

    ha_base_url = os.environ.get("HA_BASE_URL", "http://supervisor/core")
    if not ha_base_url.startswith("http://supervisor"):
        logger.warning("HA_BASE_URL is %r — expected http://supervisor/core in production", ha_base_url)
    ha_client = HAClient(
        base_url=ha_base_url,
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
    data_dir = os.path.dirname(os.path.abspath(data_path))
    app["data_dir"] = data_dir

    # Build semantic map
    semantic_map = SemanticMap(data_dir=data_dir)
    semantic_map.load()
    ambiguous = semantic_map.build_from_cache(entity_cache)
    app["semantic_map"] = semantic_map
    ha_client.add_registry_listener(semantic_map.on_entity_added)

    engine = AgentEngine(ha_client=ha_client, data_path=data_path)
    engine.set_entity_cache(entity_cache)
    await engine.start()
    app["engine"] = engine

    knowledge_db = KnowledgeDB(
        db_path=os.path.join(data_dir, "hiris_knowledge.db")
    )
    app["knowledge_db"] = knowledge_db

    context_map = SemanticContextMap()
    context_map.build(entity_cache, knowledge_db=knowledge_db)
    app["context_map"] = context_map
    logger.info("SemanticContextMap ready")

    notify_config = {
        "ha_notify_service": os.environ.get("HA_NOTIFY_SERVICE", "notify.notify"),
        "telegram_token": os.environ.get("TELEGRAM_TOKEN", ""),
        "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
        "retropanel_url": os.environ.get("RETROPANEL_URL", "http://retropanel:8098"),
    }
    app["theme"] = os.environ.get("THEME", "auto")

    tasks_data_path = os.environ.get("TASKS_DATA_PATH", "/data/tasks.json")
    task_engine = TaskEngine(
        ha_client=ha_client,
        entity_cache=entity_cache,
        notify_config=notify_config,
        data_path=tasks_data_path,
    )
    await task_engine.start()
    app["task_engine"] = task_engine

    api_key = os.environ.get("CLAUDE_API_KEY", "")
    usage_path = os.environ.get("USAGE_DATA_PATH", "/data/usage.json")
    primary_model = os.environ.get("PRIMARY_MODEL", "claude-sonnet-4-6")
    local_model_url = os.environ.get("LOCAL_MODEL_URL", "")
    if local_model_url:
        try:
            from .backends.ollama import _validate_ollama_url
            _validate_ollama_url(local_model_url)
        except ValueError as exc:
            logger.error("Invalid LOCAL_MODEL_URL (%s) — disabling local model", exc)
            local_model_url = ""
    local_model_name = os.environ.get("LOCAL_MODEL_NAME", "")

    if api_key:
        runner = ClaudeRunner(
            api_key=api_key,
            ha_client=ha_client,
            notify_config=notify_config,
            usage_path=usage_path,
            entity_cache=entity_cache,
            semantic_map=semantic_map,
        )
        router = LLMRouter(
            runner=runner,
            local_model_url=local_model_url,
            local_model_name=local_model_name,
        )
        semantic_map.set_router(router)
        app["claude_runner"] = runner   # backward compat
        app["llm_router"] = router
        engine.set_claude_runner(router)
        runner.set_task_engine(task_engine)

        # Kick off LLM classification for ambiguous entities (background, non-blocking)
        if ambiguous:
            asyncio.create_task(
                semantic_map._classify_unknown_batch(),
                name="semantic_map_initial_classify",
            )
    else:
        app["claude_runner"] = None
        app["llm_router"] = None


async def _on_cleanup(app: web.Application) -> None:
    from .chat_store import close_all_stores
    if "knowledge_db" in app:
        app["knowledge_db"].close()
    if "task_engine" in app:
        await app["task_engine"].stop()
    await app["engine"].stop()
    await app["ha_client"].stop()
    close_all_stores()


@web.middleware
async def _security_headers(request: web.Request, handler) -> web.Response:
    response = await handler(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    # X-Frame-Options omesso: HA Ingress carica l'UI in un iframe
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


def create_app() -> web.Application:
    app = web.Application(middlewares=[_security_headers])

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
    app.router.add_get("/api/agents/{agent_id}/usage", handle_get_agent_usage)
    app.router.add_post("/api/agents/{agent_id}/usage/reset", handle_reset_agent_usage)
    app.router.add_get("/api/agents/{agent_id}/context-preview", handle_context_preview)
    app.router.add_get("/api/agents/{agent_id}/chat-history", handle_get_chat_history)
    app.router.add_delete("/api/agents/{agent_id}/chat-history", handle_clear_chat_history)
    app.router.add_get("/api/tasks", handle_list_tasks)
    app.router.add_get("/api/tasks/{task_id}", handle_get_task)
    app.router.add_delete("/api/tasks/{task_id}", handle_cancel_task)

    return app


_NO_CACHE = {"Cache-Control": "no-store"}


async def _serve_index(request: web.Request) -> web.Response:
    path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if not os.path.exists(path):
        return web.Response(text="UI not yet available", status=503)
    return web.FileResponse(path, headers=_NO_CACHE)


async def _serve_config(request: web.Request) -> web.Response:
    path = os.path.join(os.path.dirname(__file__), "static", "config.html")
    if not os.path.exists(path):
        return web.Response(text="UI not yet available", status=503)
    return web.FileResponse(path, headers=_NO_CACHE)


async def _handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "version": "0.4.2"})
