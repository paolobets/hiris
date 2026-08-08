from aiohttp import web
from ..chat_store import load_history, clear_history

# fetta E4 Task 5 ("un bot solo"): chat_store non ha piu' un chatbot_id per
# cui filtrare -- c'e' UNA cronologia (il Task 5 l'ha tolto dallo schema
# stesso, chat_messages/chat_sessions). Il placeholder `{agent_id}` nel path
# (server.py) resta nella rotta per compatibilita' di superficie -- lo
# compone ancora static/chat/agents.js (righe 37, 116), che costruisce l'URL
# con l'id del bot di default -- ma qui non seleziona piu' nulla: non e'
# nemmeno piu' letto da match_info. La validazione che c'era prima
# (`_validate_chatbot_id`, un pattern su un valore mai passato a nessuna
# query/percorso) e' uscita con lui: non protegge piu' niente. La rotta si
# smonta per intero nella fetta E5, insieme al resto del frontend.


async def handle_get_chat_history(request: web.Request) -> web.Response:
    data_dir = request.app["data_dir"]
    messages = load_history(data_dir)
    return web.json_response({"messages": messages})


async def handle_clear_chat_history(request: web.Request) -> web.Response:
    data_dir = request.app["data_dir"]
    clear_history(data_dir)
    return web.json_response({"ok": True})
