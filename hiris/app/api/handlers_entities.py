from __future__ import annotations
from aiohttp import web


def _csv(v: str | None):
    return {x.strip() for x in v.split(",") if x.strip()} if v else None


def filter_entities(states, domains, device_classes) -> list[dict]:
    out = []
    for s in states or []:
        eid = s.get("id") or s.get("entity_id")
        if not eid:
            continue
        dom = eid.split(".", 1)[0]
        dc = s.get("device_class")
        if domains and dom not in domains:
            continue
        if device_classes and dc not in device_classes:
            continue
        out.append({"entity_id": eid, "friendly_name": s.get("name") or eid,
                    "domain": dom, "device_class": dc})
    return out[:1000]


async def handle_list_entities(request: web.Request) -> web.Response:
    cache = request.app.get("entity_cache")
    if cache is None or not hasattr(cache, "all_states"):
        return web.json_response({"entities": []})
    ents = filter_entities(cache.all_states(),
                           _csv(request.query.get("domain")),
                           _csv(request.query.get("device_class")))
    return web.json_response({"entities": ents})
