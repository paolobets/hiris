import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.proxy.ha_client import HAClient


@pytest.fixture
def client():
    return HAClient(base_url="http://supervisor/core", token="test-token")


def _post_mock(status=200):
    resp = AsyncMock()
    resp.status = status
    resp.text = AsyncMock(return_value="Bad" if status >= 400 else "OK")
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


@pytest.mark.asyncio
async def test_create_script_ok(client):
    post_resp = _post_mock(200)
    reload_resp = _post_mock(200)
    with patch("aiohttp.ClientSession.post", side_effect=[post_resp, reload_resp]):
        await client.start()
        res = await client.create_script("luci_sera", {"sequence": []})
        await client.stop()
    assert res == {"ok": True, "id": "luci_sera"}


@pytest.mark.asyncio
async def test_create_script_bad_slug(client):
    res = await client.create_script("Luci Sera!", {"sequence": []})
    assert "error" in res


@pytest.mark.asyncio
async def test_create_script_ha_rejects(client):
    with patch("aiohttp.ClientSession.post", return_value=_post_mock(400)):
        await client.start()
        res = await client.create_script("luci_sera", {"sequence": []})
        await client.stop()
    assert "error" in res


@pytest.mark.asyncio
async def test_create_scene_ok(client):
    post_resp = _post_mock(200)
    reload_resp = _post_mock(200)
    with patch("aiohttp.ClientSession.post", side_effect=[post_resp, reload_resp]):
        await client.start()
        res = await client.create_scene("relax", {"entities": {}})
        await client.stop()
    assert res == {"ok": True, "id": "relax"}


@pytest.mark.asyncio
async def test_create_script_empty_config(client):
    res = await client.create_script("luci_sera", {})
    assert "error" in res


@pytest.mark.asyncio
async def test_create_dashboard_ok(client):
    client._ws_command = AsyncMock(side_effect=[
        {"success": True, "result": {"url_path": "casa-mia"}},   # dashboards/create
        {"success": True, "result": None},                        # config/save
    ])
    res = await client.create_dashboard("casa-mia", "Casa Mia", {"views": [{"cards": []}]})
    assert res == {"ok": True, "url_path": "casa-mia"}
    assert client._ws_command.await_count == 2


@pytest.mark.asyncio
async def test_create_dashboard_missing_views(client):
    res = await client.create_dashboard("casa-mia", "Casa Mia", {"cards": []})
    assert "error" in res


@pytest.mark.asyncio
async def test_create_dashboard_create_fails(client):
    client._ws_command = AsyncMock(return_value={"success": False, "error": {"message": "exists"}})
    res = await client.create_dashboard("casa-mia", "Casa Mia", {"views": []})
    assert "error" in res


@pytest.mark.asyncio
async def test_create_dashboard_save_fails(client):
    client._ws_command = AsyncMock(side_effect=[
        {"success": True, "result": {"url_path": "casa-mia"}},
        {"success": False, "error": {"message": "bad config"}},
    ])
    res = await client.create_dashboard("casa-mia", "Casa Mia", {"views": []})
    assert "error" in res


@pytest.mark.asyncio
async def test_create_dashboard_save_fails_rolls_back(client):
    # create succeeds (returns the new dashboard id), config/save fails → the
    # just-created dashboard must be deleted so a retry starts clean.
    client._ws_command = AsyncMock(side_effect=[
        {"success": True, "result": {"id": "abc123", "url_path": "casa-mia"}},  # create
        {"success": False, "error": {"message": "bad config"}},                 # save fails
        {"success": True, "result": None},                                       # delete (rollback)
    ])
    res = await client.create_dashboard("casa-mia", "Casa Mia", {"views": []})
    assert "error" in res
    assert client._ws_command.await_count == 3
    rollback_call = client._ws_command.await_args_list[2]
    assert rollback_call.args[0] == "lovelace/dashboards/delete"
    assert rollback_call.args[1] == {"dashboard_id": "abc123"}


@pytest.mark.asyncio
async def test_create_dashboard_rollback_best_effort(client):
    # if the rollback delete itself fails, still return the save error (no raise).
    client._ws_command = AsyncMock(side_effect=[
        {"success": True, "result": {"id": "abc123"}},           # create
        {"success": False, "error": {"message": "bad config"}},  # save fails
        None,                                                     # delete fails (WS down)
    ])
    res = await client.create_dashboard("casa-mia", "Casa Mia", {"views": []})
    assert "error" in res and "salvataggio" in res["error"]
    assert client._ws_command.await_count == 3
