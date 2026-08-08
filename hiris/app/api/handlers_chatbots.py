# hiris/app/api/handlers_chatbots.py
from aiohttp import web
from ..impostazioni_chat import ID_CHAT_DEFAULT


# fetta E4 Task 4 ("un bot solo"): l'entita' Chatbot esce, sostituita dalle
# impostazioni della chat (`hiris/app/impostazioni_chat.py`) -- un bot solo,
# senza id. `handle_list_chatbots` resta il solo handler di questo modulo:
# superficie di compatibilita' fino alla E5 (`GET /api/chatbots` -- la pagina
# chat e la card ne dipendono davvero, verificato leggendo
# static/chat/agents.js e static/hiris-chat-card.js: indicatore "connesso",
# lista, polling della card, selettore entita' del dashboard). Spegnerla
# insieme al resto del CRUD (uscito con la fetta E4 Task 3) avrebbe spento
# l'unica cosa che HIRIS oggi deve saper fare.
#
# Il payload perde `usage`/`budget_eur` (leggevano `runner.get_chatbot_usage`,
# un concetto per-persona che non esiste piu' con una sola chat senza id): la
# card mostra 0/-- (`agent.budget_eur || 0` in hiris-chat-card.js), l'elenco
# dei consumi torna nella E5. `status` e' un valore letterale, non piu' un
# lookup su `ChatbotEngine.get_chatbot_status()`: quel metodo consultava
# `_running_chatbots`/`_error_chatbots`, due insiemi il cui unico scrittore
# (`_run_chatbot`, il Test Run) e' uscito dalla fetta E4 Task 2 -- restituiva
# gia' sempre "idle", in silenzio (orfano dichiarato nel report del Task 2).
# Con l'entita' Chatbot uscita per intero, quel meccanismo non ha proprio
# piu' un posto dove stare: non esiste alcun'esecuzione che possa mettere la
# chat in "running"/"error" -- "idle" e' l'unico stato raggiungibile, ora
# dichiarato invece di simulato.
async def handle_list_chatbots(request: web.Request) -> web.Response:
    impostazioni = request.app["impostazioni_chat"]
    return web.json_response([{
        "id": ID_CHAT_DEFAULT,
        "name": impostazioni.nome,
        "enabled": True,
        "status": "idle",
        "is_default": True,
        "max_chat_turns": impostazioni.max_chat_turns,
    }])
