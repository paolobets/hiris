# hiris/app/api/handlers_agents.py
from dataclasses import asdict
from aiohttp import web


async def handle_list_agents(request: web.Request) -> web.Response:
    engine = request.app["engine"]
    return web.json_response(list(engine.list_agents().values()))


async def handle_create_agent(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    required = {"name", "type", "trigger"}
    missing = required - set(body.keys())
    if missing:
        return web.json_response({"error": f"Missing required fields: {missing}"}, status=400)

    engine = request.app["engine"]
    agent = engine.create_agent(body)
    return web.json_response(asdict(agent), status=201)


async def handle_get_agent(request: web.Request) -> web.Response:
    engine = request.app["engine"]
    agent = engine.get_agent(request.match_info["agent_id"])
    if not agent:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response(asdict(agent))


async def handle_update_agent(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    engine = request.app["engine"]
    agent = engine.update_agent(request.match_info["agent_id"], body)
    if not agent:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response(asdict(agent))


async def handle_delete_agent(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    engine = request.app["engine"]
    agent = engine.get_agent(agent_id)
    if agent is not None and agent.is_default:
        return web.json_response({"error": "Cannot delete default agent"}, status=409)
    deleted = engine.delete_agent(agent_id)
    if not deleted:
        return web.json_response({"error": "Not found"}, status=404)
    return web.Response(status=204)


async def handle_run_agent(request: web.Request) -> web.Response:
    engine = request.app["engine"]
    agent = engine.get_agent(request.match_info["agent_id"])
    if not agent:
        return web.json_response({"error": "Not found"}, status=404)
    result = await engine.run_agent(agent)
    return web.json_response({"result": result})


async def handle_list_entities(request: web.Request) -> web.Response:
    cache = request.app["entity_cache"]
    q = request.rel_url.query.get("q", "").lower().strip()
    _MAX_Q_LEN = 100
    if len(q) > _MAX_Q_LEN:
        return web.json_response({"error": "Query too long"}, status=400)
    entities = []
    for e in cache.get_all():
        domain = e["id"].split(".")[0]
        entities.append({
            "id": e["id"],
            "name": e.get("name", ""),
            "state": e.get("state", ""),
            "domain": domain,
        })
    if q:
        entities = [
            e for e in entities
            if q in e["id"].lower() or q in e["name"].lower() or q in e["domain"].lower()
        ]
    entities.sort(key=lambda e: e["id"])
    return web.json_response(entities)
