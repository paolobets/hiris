# hiris/app/api/handlers_chatbots.py
import logging
from aiohttp import web
from ..config import EUR_RATE as _EUR_RATE

logger = logging.getLogger(__name__)


# fetta E4 Task 3 ("un bot solo"): `handle_list_chatbots` e' l'unico
# handler rimasto in questo modulo -- superficie di compatibilita' fino
# alla E5. Le strade di creazione (wizard, editor vuoto, onboarding della
# chat) convergevano tutte su POST /api/chatbots con `enabled: true` di
# default: la rotta creava sempre l'entita' gia' attiva, il contrario di
# quanto prescrive lo scope. Uscita quella, sono usciti con lei GET-single/
# PUT/DELETE (servivano solo l'editor #/chatbots e il toggle della card),
# .../usage e .../usage/reset (servivano solo la pagina usage), e con essi
# `_validate_chatbot_payload`/`_validate_openrouter_model`/
# `_check_chatbot_id`, che non avevano piu' un payload/id di richiesta da
# validare. GET /api/chatbots resta perche' la pagina chat e la card ne
# dipendono davvero (indicatore "connesso", lista, polling della card --
# verificato leggendo static/chat/agents.js e static/hiris-chat-card.js):
# spegnerla insieme al resto avrebbe spento l'unica cosa che HIRIS oggi
# deve saper fare. Si smonta nella fetta E5, insieme al frontend che la
# chiama (vedi il report del task per l'elenco delle pagine lasciate rotte).
async def handle_list_chatbots(request: web.Request) -> web.Response:
    engine = request.app["engine"]
    runner = request.app.get("llm_router") or request.app.get("claude_runner")
    result = []
    for agent_id, agent_data in engine.list_chatbots().items():
        entry = dict(agent_data)
        entry["status"] = engine.get_chatbot_status(agent_id)
        budget_eur = 0.0
        usage_payload: dict = {}
        if runner:
            try:
                usage = runner.get_chatbot_usage(agent_id) or {}
                cost_usd = usage.get("cost_usd", 0.0)
                budget_eur = round(float(cost_usd) * _EUR_RATE, 4)
                usage_payload = {
                    "requests": int(usage.get("requests", 0)),
                    "input_tokens": int(usage.get("input_tokens", 0)),
                    "output_tokens": int(usage.get("output_tokens", 0)),
                    "cost_eur": budget_eur,
                    "last_run": usage.get("last_run"),
                }
            except Exception as exc:
                logger.warning("get_chatbot_usage(%s) failed: %s", agent_id, exc)
                budget_eur = 0.0
        entry["budget_eur"] = budget_eur
        entry["usage"] = usage_payload
        result.append(entry)
    return web.json_response(result)
