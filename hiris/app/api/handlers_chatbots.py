# hiris/app/api/handlers_chatbots.py
from aiohttp import web
from ..impostazioni_chat import ID_CHAT_DEFAULT


# fetta E4 Task 4 ("un bot solo"): l'entita' Chatbot esce, sostituita dalle
# impostazioni della chat (`hiris/app/impostazioni_chat.py`) -- un bot solo,
# senza id. `handle_list_chatbots` resta il solo handler di questo modulo:
# superficie di compatibilita' fino al Task 10 della E5, che la smonta.
#
# Chi la chiama, aggiornato a fine Task 5 della E5 -- perche' le due ragioni
# scritte qui alla E4 non valgono piu' NESSUNA delle due: la pagina chat se
# n'e' staccata col Task 3 (nome e tetto di turni arrivano da
# `GET /api/impostazioni-chat`, l'indicatore "connesso" da `GET api/health`,
# vedi static/chat/agents.js) e la card Lovelace, che era l'altro chiamante,
# e' **uscita dal prodotto** col Task 5. Restano solo le pagine della SPA di
# configurazione -- config/dashboard.js, config/main.js (il contatore in
# sidebar), config/chatbots-list.js, config/chatbot-editor.js,
# config/models-route.js, config/usage-route.js, config/tasks-route.js --
# cioe' esattamente le pagine che il Task 10 smonta insieme alla rotta.
# Spegnerla prima di loro le lascerebbe rotte in silenzio.
#
# Il payload perde `usage`/`budget_eur` (leggevano `runner.get_chatbot_usage`,
# un concetto per-persona che non esiste piu' con una sola chat senza id):
# l'elenco dei consumi torna nella E5. `status` e' un valore letterale, non piu' un
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
