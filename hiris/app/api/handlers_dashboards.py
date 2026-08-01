"""Undo di una sostituzione di plancia: elenco degli snapshot e ri-applicazione."""
import logging

from aiohttp import web

from ..proxy.dashboard_backups import (
    discard_latest_backup, latest_backup, list_backups,
)

logger = logging.getLogger(__name__)


async def handle_list_dashboard_backups(request: web.Request) -> web.Response:
    """Quali plance hanno uno snapshot ripristinabile, e da quando.

    L'affordance "Annulla" va derivata da qui e non dalla memoria della pagina:
    altrimenti un replace approvato da un'altra schermata non la mostra mai e un
    refresh del browser la perde, mentre lo snapshot resta sul disco irraggiungibile.

    Risposta di soli metadati: le config delle plance non escono da questo
    endpoint. Quando mostrare l'undo in modo prominente e quando in modo discreto
    lo decide il frontend guardando "saved_at"."""
    data_dir = request.app.get("data_dir")
    if not data_dir:
        return web.json_response({"error": "servizio non disponibile"}, status=503)
    return web.json_response({"backups": list_backups(data_dir)})


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
        # Scrittura rifiutata da HA: il ripristino non e' avvenuto, quindi lo
        # snapshot resta dov'e'. Consumarlo qui brucerebbe l'unica via di
        # ritorno proprio quando l'utente deve poter riprovare.
        return web.json_response(
            {"error": f"Ripristino non riuscito: {msg}"}, status=502)
    # Scrittura riuscita: quello snapshot E' ora lo stato corrente della
    # plancia. Continuare a elencarlo come "annulla" sarebbe un no-op che
    # dopo un refresh riproporrebbe di annullare cio' che e' gia' annullato:
    # l'elenco del server deve restare l'unica fonte di verita'.
    if not discard_latest_backup(data_dir, url_path):
        # La plancia e' stata ripristinata davvero: per l'utente e' un
        # successo. Resta una voce di troppo nell'elenco, non un errore.
        logger.warning(
            "Ripristino di '%s' riuscito ma lo snapshot non e' stato consumato: "
            "restera' elencato come ripristinabile.", url_path)
    return web.json_response({"ok": True, "url_path": url_path})
