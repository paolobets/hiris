# hiris/app/server.py
import os
from aiohttp import web
from .api.handlers_chat import handle_chat
from .api.handlers_agents import handle_list_agents, handle_create_agent, handle_get_agent, handle_update_agent, handle_delete_agent, handle_run_agent
from .api.handlers_status import handle_status
from .agent_engine import AgentEngine
from .proxy.ha_client import HAClient


async def _on_startup(app: web.Application) -> None:
    from .claude_runner import ClaudeRunner

    ha_client = HAClient(
        base_url=os.environ.get("HA_BASE_URL", "http://supervisor/core"),
        token=os.environ.get("SUPERVISOR_TOKEN", ""),
    )
    await ha_client.start()
    app["ha_client"] = ha_client

    engine = AgentEngine(ha_client=ha_client)
    await engine.start()
    app["engine"] = engine

    notify_config = {
        "ha_notify_service": os.environ.get("HA_NOTIFY_SERVICE", "notify.notify"),
        "telegram_token": os.environ.get("TELEGRAM_TOKEN", ""),
        "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
        "retropanel_url": os.environ.get("RETROPANEL_URL", "http://retropanel:8098"),
    }
    restrict_raw = os.environ.get("RESTRICT_CHAT_TO_HOME", "false").lower()
    restrict_to_home = restrict_raw in ("true", "1", "yes")
    api_key = os.environ.get("CLAUDE_API_KEY", "")
    if api_key:
        runner = ClaudeRunner(
            api_key=api_key,
            ha_client=ha_client,
            notify_config=notify_config,
            restrict_to_home=restrict_to_home,
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
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_get("/api/agents", handle_list_agents)
    app.router.add_post("/api/agents", handle_create_agent)
    app.router.add_get("/api/agents/{agent_id}", handle_get_agent)
    app.router.add_put("/api/agents/{agent_id}", handle_update_agent)
    app.router.add_delete("/api/agents/{agent_id}", handle_delete_agent)
    app.router.add_post("/api/agents/{agent_id}/run", handle_run_agent)

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
    return web.json_response({"status": "ok", "version": "0.0.4"})
