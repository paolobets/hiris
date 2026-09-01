import json
from unittest.mock import MagicMock

import pytest
from aiohttp.test_utils import make_mocked_request

from hiris.app.api.handlers_chat_history import handle_clear_chat_history, handle_get_chat_history
from hiris.app.chat_store import close_all_stores


@pytest.fixture(autouse=True)
def reset_stores():
    close_all_stores()
    yield
    close_all_stores()


def _make_app(data_dir: str) -> MagicMock:
    from hiris.app.impostazioni_chat import ChatSettings

    # Task 12: handle_get_chat_history legge anche app["impostazioni_chat"]
    # (giorni_conservazione) -- senza questa chiave il MagicMock tornerebbe
    # None e `.giorni_conservazione` esploderebbe con AttributeError.
    valori = {"data_dir": data_dir, "impostazioni_chat": ChatSettings()}
    app = MagicMock()
    app.__getitem__ = MagicMock(side_effect=lambda k: valori.get(k))
    return app


# fetta E5 Task 4 ("nasce la rotta onesta, muore il placeholder"): la rotta
# reale (server.py) e' ora `GET/DELETE /api/chat/history`, senza nessun
# identificatore nel percorso -- c'e' UNA cronologia (dalla E4 Task 5), non
# c'e' piu' niente da scegliere. Gli handler sotto non leggevano l'id da
# match_info nemmeno prima: cambia solo la richiesta mockata, non il loro
# corpo.
#
# `test_get_chat_history_ignores_path_placeholder_value` (pin della E4 Task
# 5: "qualunque valore nel placeholder {agent_id} legge la STESSA
# cronologia") e' uscito qui, non spostato: il suo soggetto era il
# placeholder stesso, che questo task cancella dalla rotta -- non c'e' piu'
# nessun placeholder da poter ignorare. Non falliva per costruzione a
# livello di singolo test (chiamava l'handler direttamente con un
# match_info costruito a mano, bypassando il router: l'handler non lo
# leggeva ne' prima ne' dopo), ma lo scenario che pinnava non esiste piu' a
# livello di prodotto: verificato con `app.router.resolve()` su un
# `create_app()` reale, `/api/chatbots/qualunque-cosa-mai-esistita/
# chat-history` risolve a `MatchInfoError` (404) dopo questo task, contro
# `UrlMappingMatchInfo` prima. Il comportamento che restava vivo -- "la
# cronologia e' unica, chi la legge la legge sempre uguale" -- resta pinnato
# da `test_get_chat_history_returns_messages` e
# `test_get_chat_history_empty_when_no_messages` sotto, che non hanno
# bisogno di un placeholder arbitrario per dirlo.

@pytest.mark.asyncio
async def test_get_chat_history_returns_messages(tmp_path):
    from hiris.app.chat_store import append_messages
    append_messages([{"role": "user", "content": "ciao"}], str(tmp_path))

    app = _make_app(str(tmp_path))
    request = make_mocked_request(
        "GET", "/api/chat/history", app=app, match_info={},
    )

    resp = await handle_get_chat_history(request)
    data = json.loads(resp.body)
    assert data["messages"] == [{"role": "user", "content": "ciao"}]


@pytest.mark.asyncio
async def test_get_chat_history_empty_when_no_messages(tmp_path):
    app = _make_app(str(tmp_path))
    request = make_mocked_request(
        "GET", "/api/chat/history", app=app, match_info={},
    )

    resp = await handle_get_chat_history(request)
    data = json.loads(resp.body)
    assert data["messages"] == []


@pytest.mark.asyncio
async def test_clear_chat_history_removes_messages(tmp_path):
    from hiris.app.chat_store import append_messages, load_history
    append_messages([{"role": "user", "content": "ciao"}], str(tmp_path))

    app = _make_app(str(tmp_path))
    request = make_mocked_request(
        "DELETE", "/api/chat/history", app=app, match_info={},
    )

    resp = await handle_clear_chat_history(request)
    data = json.loads(resp.body)
    assert data["ok"] is True
    assert load_history(str(tmp_path)) == []


@pytest.mark.asyncio
async def test_clear_chat_history_noop_when_empty(tmp_path):
    app = _make_app(str(tmp_path))
    request = make_mocked_request(
        "DELETE", "/api/chat/history", app=app, match_info={},
    )

    resp = await handle_clear_chat_history(request)
    data = json.loads(resp.body)
    assert data["ok"] is True
