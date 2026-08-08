import json
import pytest
from unittest.mock import MagicMock
from aiohttp.test_utils import make_mocked_request
from hiris.app.api.handlers_chat_history import handle_get_chat_history, handle_clear_chat_history
from hiris.app.chat_store import close_all_stores


@pytest.fixture(autouse=True)
def reset_stores():
    close_all_stores()
    yield
    close_all_stores()


def _make_app(data_dir: str) -> MagicMock:
    app = MagicMock()
    app.__getitem__ = MagicMock(side_effect=lambda k: data_dir if k == "data_dir" else None)
    return app


# fetta E4 Task 5 ("un bot solo"): chat_store non ha piu' un chatbot_id per
# cui filtrare -- c'e' UNA cronologia. Il placeholder {agent_id} nel path
# resta nella richiesta mockata sotto solo perche' la rotta reale
# (server.py) lo dichiara ancora nel pattern per compatibilita' di
# superficie (agents.js compone ancora l'URL con l'id del bot di default) --
# gli handler non lo leggono piu' da match_info.

@pytest.mark.asyncio
async def test_get_chat_history_returns_messages(tmp_path):
    from hiris.app.chat_store import append_messages
    append_messages([{"role": "user", "content": "ciao"}], str(tmp_path))

    app = _make_app(str(tmp_path))
    request = make_mocked_request(
        "GET", "/api/chatbots/hiris-default/chat-history", app=app,
        match_info={"agent_id": "hiris-default"},
    )

    resp = await handle_get_chat_history(request)
    data = json.loads(resp.body)
    assert data["messages"] == [{"role": "user", "content": "ciao"}]


@pytest.mark.asyncio
async def test_get_chat_history_empty_when_no_messages(tmp_path):
    app = _make_app(str(tmp_path))
    request = make_mocked_request(
        "GET", "/api/chatbots/hiris-default/chat-history", app=app,
        match_info={"agent_id": "hiris-default"},
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
        "DELETE", "/api/chatbots/hiris-default/chat-history", app=app,
        match_info={"agent_id": "hiris-default"},
    )

    resp = await handle_clear_chat_history(request)
    data = json.loads(resp.body)
    assert data["ok"] is True
    assert load_history(str(tmp_path)) == []


@pytest.mark.asyncio
async def test_clear_chat_history_noop_when_empty(tmp_path):
    app = _make_app(str(tmp_path))
    request = make_mocked_request(
        "DELETE", "/api/chatbots/hiris-default/chat-history", app=app,
        match_info={"agent_id": "hiris-default"},
    )

    resp = await handle_clear_chat_history(request)
    data = json.loads(resp.body)
    assert data["ok"] is True


@pytest.mark.asyncio
async def test_get_chat_history_ignores_path_placeholder_value(tmp_path):
    """Pin dichiarato del comportamento del Task 5: qualunque valore nel
    placeholder {agent_id} (anche uno mai esistito) legge la STESSA, unica
    cronologia -- il placeholder non seleziona piu' nulla."""
    from hiris.app.chat_store import append_messages
    append_messages([{"role": "user", "content": "unica"}], str(tmp_path))

    app = _make_app(str(tmp_path))
    request = make_mocked_request(
        "GET", "/api/chatbots/qualunque-cosa-mai-esistita/chat-history", app=app,
        match_info={"agent_id": "qualunque-cosa-mai-esistita"},
    )

    resp = await handle_get_chat_history(request)
    data = json.loads(resp.body)
    assert data["messages"] == [{"role": "user", "content": "unica"}]
