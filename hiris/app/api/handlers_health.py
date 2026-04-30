from aiohttp import web


async def handle_get_ha_health(request: web.Request) -> web.Response:
    health_monitor = request.app.get("health_monitor")
    if health_monitor is None:
        return web.json_response({"error": "HealthMonitor not initialized"}, status=503)
    sections_raw = request.rel_url.query.get("sections", "")
    sections = [s.strip() for s in sections_raw.split(",") if s.strip()] or ["all"]
    snapshot = health_monitor.get_snapshot(sections)
    return web.json_response(snapshot)


async def handle_refresh_ha_health(request: web.Request) -> web.Response:
    health_monitor = request.app.get("health_monitor")
    if health_monitor is None:
        return web.json_response({"error": "HealthMonitor not initialized"}, status=503)
    await health_monitor.refresh()
    return web.json_response({"ok": True})
