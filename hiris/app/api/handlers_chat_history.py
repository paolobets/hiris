from aiohttp import web
from ..chat_store import load_history, clear_history

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
    messages = load_history(data_dir)
    return web.json_response({"messages": messages})


async def handle_clear_chat_history(request: web.Request) -> web.Response:
    data_dir = request.app["data_dir"]
    clear_history(data_dir)
    return web.json_response({"ok": True})
