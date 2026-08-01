"""Undo di una sostituzione di plancia: ri-applica l'ultimo snapshot."""
import logging

from aiohttp import web

from ..proxy.dashboard_backups import latest_backup

logger = logging.getLogger(__name__)


async def handle_restore_dashboard(request: web.Request) -> web.Response:
    ha = request.app.get("ha_client")
    data_dir = request.app.get("data_dir")
    if ha is None or not data_dir:
        return web.json_response({"error": "servizio non disponibile"}, status=503)
    url_path = request.match_info["url_path"]
    config = latest_backup(data_dir, url_path)
    if config is None:
        return web.json_response(
            {"error": "Nessuno snapshot disponibile per questa plancia"}, status=404)
    result = await ha.save_dashboard_config(url_path, config)
    if not isinstance(result, dict) or result.get("error"):
        msg = result.get("error") if isinstance(result, dict) else "errore sconosciuto"
        return web.json_response(
            {"error": f"Ripristino non riuscito: {msg}"}, status=502)
    return web.json_response({"ok": True, "url_path": url_path})
