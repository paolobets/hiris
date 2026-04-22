from dataclasses import asdict
from aiohttp import web


async def handle_list_tasks(request: web.Request) -> web.Response:
    task_engine = request.app.get("task_engine")
    if task_engine is None:
        return web.json_response([])
    agent_id = request.rel_url.query.get("agent_id")
    status = request.rel_url.query.get("status")
    tasks = task_engine.list_tasks(agent_id=agent_id or None, status=status or None)
    return web.json_response(tasks)


async def handle_get_task(request: web.Request) -> web.Response:
    task_engine = request.app.get("task_engine")
    if task_engine is None:
        return web.json_response({"error": "Not found"}, status=404)
    task = task_engine.get_task(request.match_info["task_id"])
    if task is None:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response(asdict(task))


async def handle_cancel_task(request: web.Request) -> web.Response:
    task_engine = request.app.get("task_engine")
    if task_engine is None:
        return web.json_response({"error": "Not found"}, status=404)
    cancelled = task_engine.cancel_task(request.match_info["task_id"])
    if not cancelled:
        return web.json_response({"error": "Task not found or not cancellable"}, status=404)
    return web.Response(status=204)
