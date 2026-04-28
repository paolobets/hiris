# hiris/app/server.py
import asyncio
import json
import logging
import os
import shutil
import aiohttp
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
from .version import read_version
from .proxy.ha_client import HAClient
from .proxy.entity_cache import EntityCache
from .proxy.knowledge_db import KnowledgeDB
from .proxy.semantic_context_map import SemanticContextMap
from .proxy.memory_store import MemoryStore
from .backends.embeddings import build_embedding_provider
from .api.middleware_internal_auth import internal_auth_middleware
from .mqtt_publisher import MQTTPublisher

logger = logging.getLogger(__name__)


def _find_ha_config_dir() -> str | None:
    """Return the HA config directory path inside the container, or None if not mounted.

    Different Supervisor versions mount the config volume at different paths:
    - /config  (documented standard, most Supervisor versions)
    - /homeassistant  (used in some older/newer variants)
    We probe both and return the first that looks like the real HA config.
    """
    for candidate in ("/config", "/homeassistant"):
        if (
            os.path.exists(os.path.join(candidate, "configuration.yaml"))
            or os.path.isdir(os.path.join(candidate, ".storage"))
        ):
            return candidate
    return None


def _deploy_card_to_www(slug: str = "hiris") -> None:
    """Copy hiris-chat-card.js to <ha-config>/www/{slug}/ for auth-free Lovelace access.

    Requires 'config:rw' in the add-on map (config.yaml).
    """
    ha_config = _find_ha_config_dir()
    if ha_config is None:
        logger.error(
            "HA config directory not found at /config or /homeassistant — "
            "card cannot be deployed. Ensure 'config:rw' is in the add-on map, "
            "then stop and restart the add-on. "
            "Until fixed, /local/%s/hiris-chat-card.js will return 404.",
            slug,
        )
        return

    src = os.path.join(os.path.dirname(__file__), "static", "hiris-chat-card.js")
    dst_dir = os.path.join(ha_config, "www", slug)
    dst = os.path.join(dst_dir, "hiris-chat-card.js")
    try:
        os.makedirs(dst_dir, exist_ok=True)
        shutil.copy2(src, dst)
        logger.info("HIRIS card deployed to %s", dst)
    except Exception as exc:
        logger.error("Failed to deploy HIRIS card to %s: %s", dst, exc, exc_info=True)


async def _ws_await(ws, msg_id: int, timeout: float = 10.0) -> dict:
    """Read WebSocket messages until we get the one matching msg_id."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise asyncio.TimeoutError(f"Timeout waiting for WS message id={msg_id}")
        msg = await asyncio.wait_for(ws.receive_json(), timeout=remaining)
        if msg.get("id") == msg_id:
            return msg


async def _write_ingress_config(supervisor_token: str, slug: str = "hiris") -> None:
    """Write /homeassistant/www/{slug}/hiris-ingress.json with the real ingress URL.

    The HA Supervisor uses a randomly-generated ingress token (not the add-on slug)
    as the path component in /api/hassio_ingress/{token}/.  The Lovelace card reads
    this file (no auth required — /local/ is served publicly) to discover the correct
    URL before making any API call.
    """
    ha_config = _find_ha_config_dir()
    if ha_config is None:
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://supervisor/addons/self/info",
                headers={"Authorization": f"Bearer {supervisor_token}"},
            ) as resp:
                if resp.status != 200:
                    logger.warning(
                        "Supervisor /addons/self/info returned %s — "
                        "card will fall back to slug-based ingress URL",
                        resp.status,
                    )
                    return
                data = await resp.json()
    except Exception as exc:
        logger.warning("Cannot reach Supervisor API (%s) — skipping ingress config", exc)
        return

    ingress_url = (data.get("data") or {}).get("ingress_url")
    if not ingress_url:
        logger.warning("Supervisor did not return ingress_url — skipping ingress config")
        return

    dst_dir = os.path.join(ha_config, "www", slug)
    dst = os.path.join(dst_dir, "hiris-ingress.json")
    try:
        os.makedirs(dst_dir, exist_ok=True)
        with open(dst, "w", encoding="utf-8") as f:
            json.dump({"ingress_url": ingress_url}, f)
        logger.info("HIRIS ingress config written: %s → %s", ingress_url, dst)
    except Exception as exc:
        logger.error("Failed to write ingress config to %s: %s", dst, exc)


async def _register_lovelace_card(ha_base_url: str, token: str, slug: str = "hiris") -> None:
    """Register /local/{slug}/hiris-chat-card.js?v=VERSION as a Lovelace module resource.

    Uses the HA WebSocket API, which works even when the REST endpoint is unavailable.
    Migrates stale URLs (old ingress URL and older versioned /local/ URLs). Idempotent.
    The ?v= query param forces the browser to fetch the new JS on every version bump.
    """
    version = read_version()
    new_url = f"/local/{slug}/hiris-chat-card.js?v={version}"
    old_url = f"/api/hassio_ingress/{slug}/static/hiris-chat-card.js"
    ws_url = (
        ha_base_url.replace("http://", "ws://").replace("https://", "wss://")
        + "/api/websocket"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                # Authenticate
                handshake = await asyncio.wait_for(ws.receive_json(), timeout=10.0)
                if handshake.get("type") == "auth_required":
                    await ws.send_json({"type": "auth", "access_token": token})
                    auth_resp = await asyncio.wait_for(ws.receive_json(), timeout=10.0)
                    if auth_resp.get("type") != "auth_ok":
                        logger.warning("HA WebSocket auth failed — Lovelace registration skipped")
                        return

                # List existing resources
                await ws.send_json({"id": 1, "type": "lovelace/resources"})
                list_resp = await _ws_await(ws, msg_id=1)

                if not list_resp.get("success"):
                    # YAML mode or HA version without resources support
                    err_msg = list_resp.get("error", {}).get("message", "unsupported")
                    logger.info(
                        "Lovelace resources not manageable via WebSocket (%s) — "
                        "add manually in lovelace config: url: %s  type: module",
                        err_msg, new_url,
                    )
                    return

                resources: list[dict] = list_resp.get("result", [])
                msg_id = 2

                # Remove stale URLs: old ingress URL and any /local/ URL that is not
                # the current versioned URL (handles version upgrades and bare URL left
                # by older add-on versions).
                base_local = f"/local/{slug}/hiris-chat-card.js"
                for resource in resources:
                    url = resource.get("url", "")
                    is_stale = (
                        url == old_url
                        or (url.startswith(base_local) and url != new_url)
                    )
                    if is_stale:
                        await ws.send_json({
                            "id": msg_id,
                            "type": "lovelace/resources/delete",
                            "resource_id": resource["id"],
                        })
                        del_resp = await _ws_await(ws, msg_id)
                        if del_resp.get("success"):
                            logger.info("Removed stale Lovelace resource: %s", url)
                        msg_id += 1

                # Idempotency check against the current versioned URL
                for resource in resources:
                    if resource.get("url") == new_url:
                        logger.debug("HIRIS Lovelace card already registered: %s", new_url)
                        return

                # Register
                await ws.send_json({
                    "id": msg_id,
                    "type": "lovelace/resources/create",
                    "res_type": "module",
                    "url": new_url,
                })
                create_resp = await _ws_await(ws, msg_id)

                if create_resp.get("success"):
                    logger.info(
                        "HIRIS Lovelace card registered ✓ url=%s — reload HA UI to activate",
                        new_url,
                    )
                else:
                    logger.warning(
                        "Lovelace registration failed: %s",
                        create_resp.get("error", {}).get("message", "unknown"),
                    )
    except Exception as exc:
        logger.warning("Lovelace card registration error: %s", exc)


async def _on_startup(app: web.Application) -> None:
    from .claude_runner import ClaudeRunner
    from .proxy.semantic_map import SemanticMap
    from .llm_router import LLMRouter

    app["internal_token"] = os.environ.get("INTERNAL_TOKEN", "")
    ha_base_url = os.environ.get("HA_BASE_URL", "http://supervisor/core")
    if not ha_base_url.startswith("http://supervisor"):
        logger.warning("HA_BASE_URL is %r — expected http://supervisor/core in production", ha_base_url)
    ha_client = HAClient(
        base_url=ha_base_url,
        token=os.environ.get("SUPERVISOR_TOKEN", ""),
    )
    await ha_client.start()
    app["ha_client"] = ha_client

    # Deploy card JS and ingress config to /homeassistant/www/, register Lovelace resource
    hiris_slug = os.environ.get("HIRIS_SLUG", "hiris")
    _deploy_card_to_www(hiris_slug)
    await _write_ingress_config(os.environ.get("SUPERVISOR_TOKEN", ""), hiris_slug)
    await _register_lovelace_card(
        ha_base_url,
        os.environ.get("SUPERVISOR_TOKEN", ""),
        hiris_slug,
    )

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

    context_map = SemanticContextMap(
        cache_path=os.path.join(data_dir, "semantic_context_map.json")
    )
    context_map.load()
    context_map.build(entity_cache, knowledge_db=knowledge_db)
    app["context_map"] = context_map
    logger.info("SemanticContextMap ready")

    _apprise_raw = os.environ.get("APPRISE_URLS", "[]")
    try:
        _apprise_urls: list[str] = json.loads(_apprise_raw)
        if not isinstance(_apprise_urls, list):
            _apprise_urls = []
    except Exception:
        _apprise_urls = []
    notify_config = {
        "ha_notify_service": os.environ.get("HA_NOTIFY_SERVICE", "notify.notify"),
        "apprise_urls": _apprise_urls,
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

    mqtt_pub = MQTTPublisher()
    await mqtt_pub.start(
        host=os.environ.get("MQTT_HOST", ""),
        port=int(os.environ.get("MQTT_PORT", "1883")),
        user=os.environ.get("MQTT_USER", ""),
        password=os.environ.get("MQTT_PASSWORD", ""),
    )
    app["mqtt_publisher"] = mqtt_pub
    engine.set_mqtt_publisher(mqtt_pub)

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
    openai_api_key = os.environ.get("OPENAI_API_KEY", "")

    # Memory / RAG config
    mem_provider = os.environ.get("MEMORY_EMBEDDING_PROVIDER", "")
    mem_model = os.environ.get("MEMORY_EMBEDDING_MODEL", "")
    memory_rag_k = int(os.environ.get("MEMORY_RAG_K", "5"))
    _mem_ret_raw = os.environ.get("MEMORY_RETENTION_DAYS", "90")
    memory_retention_days: int | None = None if _mem_ret_raw == "0" else int(_mem_ret_raw)

    embedder = build_embedding_provider(
        provider=mem_provider,
        model=mem_model,
        openai_api_key=openai_api_key,
        local_model_url=local_model_url,
    )
    memory_store = MemoryStore(db_path=os.path.join(data_dir, "hiris_memory.db"))
    app["memory_store"] = memory_store
    app["embedding_provider"] = embedder
    app["memory_rag_k"] = memory_rag_k

    # Daily retention job (chat messages + expired memories)
    from .chat_store import delete_old_messages as _delete_old_messages

    def _run_retention() -> None:
        from .chat_store import HISTORY_RETENTION_DAYS
        if HISTORY_RETENTION_DAYS > 0:
            n = _delete_old_messages(data_dir, HISTORY_RETENTION_DAYS)
            if n:
                logger.info("Retention: deleted %d old chat messages", n)
        n2 = memory_store.delete_expired()
        if n2:
            logger.info("Retention: deleted %d expired memories", n2)

    engine._scheduler.add_job(
        _run_retention,
        trigger="cron",
        hour=3,
        minute=0,
        id="hiris_retention",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    if api_key:
        runner = ClaudeRunner(
            api_key=api_key,
            ha_client=ha_client,
            notify_config=notify_config,
            usage_path=usage_path,
            entity_cache=entity_cache,
            semantic_map=semantic_map,
            memory_store=memory_store,
            embedding_provider=embedder,
            memory_retention_days=memory_retention_days,
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
        engine.set_task_engine(task_engine)
        engine.set_notify_config(notify_config)
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
    if "mqtt_publisher" in app:
        await app["mqtt_publisher"].stop()
    if "knowledge_db" in app:
        app["knowledge_db"].close()
    if "memory_store" in app:
        app["memory_store"].close()
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
    app = web.Application(middlewares=[internal_auth_middleware, _security_headers])

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
    return web.json_response({"status": "ok", "version": read_version()})
