import json
import pytest
from unittest.mock import MagicMock
from aiohttp.test_utils import make_mocked_request
from hiris.app.api.handlers_chat_history import handle_get_chat_history, handle_clear_chat_history


def _make_app(data_dir: str) -> MagicMock:
    app = MagicMock()
    app.__getitem__ = MagicMock(side_effect=lambda k: data_dir if k == "data_dir" else None)
    return app


@pytest.mark.asyncio
async def test_get_chat_history_returns_messages(tmp_path):
    from hiris.app.chat_store import append_messages
    append_messages("agent-x", [{"role": "user", "content": "ciao"}], str(tmp_path))

    app = _make_app(str(tmp_path))
    request = make_mocked_request(
        "GET", "/api/agents/agent-x/chat-history", app=app,
        match_info={"agent_id": "agent-x"},
    )

    resp = await handle_get_chat_history(request)
    data = json.loads(resp.body)
    assert data["messages"] == [{"role": "user", "content": "ciao"}]


@pytest.mark.asyncio
async def test_get_chat_history_empty_when_no_file(tmp_path):
    app = _make_app(str(tmp_path))
    request = make_mocked_request(
        "GET", "/api/agents/missing/chat-history", app=app,
        match_info={"agent_id": "missing"},
    )

    resp = await handle_get_chat_history(request)
    data = json.loads(resp.body)
    assert data["messages"] == []


@pytest.mark.asyncio
async def test_clear_chat_history_removes_messages(tmp_path):
    from hiris.app.chat_store import append_messages, load_history
    append_messages("agent-x", [{"role": "user", "content": "ciao"}], str(tmp_path))

    app = _make_app(str(tmp_path))
    request = make_mocked_request(
        "DELETE", "/api/agents/agent-x/chat-history", app=app,
        match_info={"agent_id": "agent-x"},
    )

    resp = await handle_clear_chat_history(request)
    data = json.loads(resp.body)
    assert data["ok"] is True
    assert load_history("agent-x", str(tmp_path)) == []


@pytest.mark.asyncio
async def test_clear_chat_history_noop_when_no_file(tmp_path):
    app = _make_app(str(tmp_path))
    request = make_mocked_request(
        "DELETE", "/api/agents/missing/chat-history", app=app,
        match_info={"agent_id": "missing"},
    )

    resp = await handle_clear_chat_history(request)
    data = json.loads(resp.body)
    assert data["ok"] is True
