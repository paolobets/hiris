"""TDD tests for review A/#4 (SSRF/path-injection): get_automation_config() must
validate `automation_id` against the same strict slug regex the sibling
trigger_automation/toggle_automation branches use, BEFORE building any HA REST URL.

A payload like 'automation.x/../../config/core/config' must be rejected outright —
never string-concatenated into the request path, and no HTTP request may be made.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.proxy.ha_client import HAClient


@pytest.fixture
def client():
    return HAClient(base_url="http://supervisor/core", token="test-token")


TRAVERSAL_PAYLOADS = [
    "automation.x/../../config/core/config",   # path traversal via entity_id prefix
    "x/../../config/core/config",              # path traversal via bare object_id
    "automation.x y",                          # space
    "automation.http://evil.com",              # scheme-like injection
    "../../../api/config/core/config",         # raw traversal, no automation. prefix
    "automation.foo?x=1",                      # query-string injection
    "automation.foo#frag",                     # fragment injection
]


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", TRAVERSAL_PAYLOADS)
async def test_get_automation_config_rejects_traversal_no_request_built(client, payload):
    with patch("aiohttp.ClientSession.get") as mock_get:
        await client.start()
        res = await client.get_automation_config(payload)
        await client.stop()
    assert "error" in res
    mock_get.assert_not_called()


def _get_mock(status=200, json_body=None):
    resp = AsyncMock()
    resp.status = status
    resp.raise_for_status = MagicMock()
    resp.json = AsyncMock(return_value=json_body or {})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


@pytest.mark.asyncio
async def test_get_automation_config_valid_entity_id_still_works(client):
    states_resp = _get_mock(200, {"attributes": {"id": "42"}})
    config_resp = _get_mock(200, {"alias": "Test", "trigger": [], "action": []})
    with patch("aiohttp.ClientSession.get", side_effect=[states_resp, config_resp]) as mock_get:
        await client.start()
        res = await client.get_automation_config("automation.my_id")
        await client.stop()
    assert res == {"alias": "Test", "trigger": [], "action": []}
    assert mock_get.call_count == 2
    assert mock_get.call_args_list[0].args[0] == "http://supervisor/core/api/states/automation.my_id"
    assert mock_get.call_args_list[1].args[0] == "http://supervisor/core/api/config/automation/config/42"


@pytest.mark.asyncio
async def test_get_automation_config_valid_bare_object_id_still_works(client):
    states_resp = _get_mock(200, {"attributes": {"id": "7"}})
    config_resp = _get_mock(200, {"alias": "Bare", "trigger": [], "action": []})
    with patch("aiohttp.ClientSession.get", side_effect=[states_resp, config_resp]) as mock_get:
        await client.start()
        res = await client.get_automation_config("my_id")
        await client.stop()
    assert res == {"alias": "Bare", "trigger": [], "action": []}
    assert mock_get.call_args_list[0].args[0] == "http://supervisor/core/api/states/automation.my_id"


@pytest.mark.asyncio
async def test_get_automation_config_numeric_id_still_works(client):
    # Purely numeric ids skip the entity_id lookup entirely (unchanged fast path).
    config_resp = _get_mock(200, {"alias": "Numeric", "trigger": [], "action": []})
    with patch("aiohttp.ClientSession.get", return_value=config_resp) as mock_get:
        await client.start()
        res = await client.get_automation_config("42")
        await client.stop()
    assert res == {"alias": "Numeric", "trigger": [], "action": []}
    assert mock_get.call_args_list[0].args[0] == "http://supervisor/core/api/config/automation/config/42"
