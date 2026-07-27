import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.mcp.local_client import LocalExecuteClient


@pytest.mark.asyncio
async def test_execute_posts_to_execute_api_with_token():
    captured = {}

    class _Resp:
        status = 200
        async def json(self): return {"result": {"ok": True}}
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    def fake_post(url, json=None, headers=None):
        captured["url"] = url; captured["json"] = json; captured["headers"] = headers
        return _Resp()

    c = LocalExecuteClient("http://127.0.0.1:8099", "TOK")
    with patch.object(c, "_session") as sess:
        sess.post = MagicMock(side_effect=fake_post)
        out = await c.execute("get_home_status", {"a": 1})

    assert out == {"result": {"ok": True}}
    assert captured["url"] == "http://127.0.0.1:8099/api/execute"
    assert captured["json"] == {"tool": "get_home_status", "input": {"a": 1}, "origin": "hiris-chat"}
    assert captured["headers"]["X-HIRIS-Internal-Token"] == "TOK"


@pytest.mark.asyncio
async def test_execute_returns_error_dict_on_http_failure():
    class _Resp:
        status = 502
        async def text(self): return "bad"
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    c = LocalExecuteClient("http://127.0.0.1:8099", "TOK")
    with patch.object(c, "_session") as sess:
        sess.post = MagicMock(return_value=_Resp())
        out = await c.execute("call_service", {})
    assert "error" in out


@pytest.mark.asyncio
async def test_execute_without_token_sends_no_auth_header():
    captured = {}

    class _Resp:
        status = 200
        async def json(self): return {"result": {"ok": True}}
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    def fake_post(url, json=None, headers=None):
        captured["headers"] = headers
        return _Resp()

    c = LocalExecuteClient("http://127.0.0.1:8099", "")
    with patch.object(c, "_session") as sess:
        sess.post = MagicMock(side_effect=fake_post)
        await c.execute("get_home_status", {})

    assert captured["headers"] == {}
    assert "X-HIRIS-Internal-Token" not in captured["headers"]


@pytest.mark.asyncio
async def test_execute_returns_error_dict_on_generic_exception():
    c = LocalExecuteClient("http://127.0.0.1:8099", "TOK")
    with patch.object(c, "_session") as sess:
        sess.post = MagicMock(side_effect=ConnectionError("refused"))
        out = await c.execute("get_home_status", {})

    assert isinstance(out, dict)
    assert "error" in out


@pytest.mark.asyncio
async def test_start_stop_lifecycle_is_idempotent():
    c = LocalExecuteClient("http://127.0.0.1:8099", "TOK")
    assert c._session is None

    await c.start()
    assert c._session is not None
    first_session = c._session

    # Second start() should be idempotent: no new session, no error.
    await c.start()
    assert c._session is first_session

    await c.stop()
    assert c._session is None
