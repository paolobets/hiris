from aiohttp import web

from ..chat_store import clear_history, load_history

# fetta E5 Task 4 ("il frontend"): la rotta e' `GET/DELETE
# /api/chat/cronologia` (server.py) -- nessun identificatore nel percorso,
# perche' c'e' UNA cronologia sola (chat_store non ha piu' un chatbot_id per
# cui filtrare dalla E4 Task 5). Storia: fino a questo task il path portava
# ancora un placeholder `{agent_id}` ereditato dall'epoca multi-assistente --
# accettato ma non selezionava nulla: non era nemmeno piu' letto da
# match_info (la validazione che c'era prima, `_validate_chatbot_id`, era
# gia' uscita con lui, perche' non proteggeva piu' niente). Il placeholder e'
# morto in questo task insieme al path che lo portava; gli handler sotto non
# sono cambiati di una riga, perche' non hanno mai letto l'id.


async def handle_get_chat_history(request: web.Request) -> web.Response:
    data_dir = request.app["data_dir"]
    # Task 12: prima di questo task `load_history` leggeva sempre il globale
    # `chat_store.HISTORY_RETENTION_DAYS` -- questa pagina era GIA' filtrata
    # dallo stesso numero, per accidente di implementazione condivisa, non
    # per scelta dichiarata qui. Passare `giorni_conservazione` esplicitamente
    # mantiene lo stesso comportamento invece di farlo silenziosamente
    # ricadere sul default (90) del parametro qualunque cosa l'utente abbia
    # scelto in «Impostazioni chat».
    giorni = request.app["impostazioni_chat"].giorni_conservazione
    messages = load_history(data_dir, days=giorni)
    return web.json_response({"messages": messages})


async def handle_clear_chat_history(request: web.Request) -> web.Response:
    data_dir = request.app["data_dir"]
    clear_history(data_dir)
    return web.json_response({"ok": True})
