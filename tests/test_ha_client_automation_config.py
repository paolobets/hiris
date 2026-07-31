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


# ---------------------------------------------------------------------------
# Bug live-verify #2 (overwrite automazioni): quando la proposta NON riporta
# l'id (l'LLM spesso lo omette "modificando"), risolvi per alias/friendly_name
# UNIVOCO -> modifica quella automazione invece di crearne un doppione.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_automation_id_by_alias_unique_match(client):
    client.get_automations = AsyncMock(return_value=[
        {"entity_id": "automation.a", "attributes": {"friendly_name": "Luci sera", "id": "1699999999"}},
        {"entity_id": "automation.b", "attributes": {"friendly_name": "Altra", "id": "1700000000"}},
    ])
    assert await client.resolve_automation_id_by_alias("Luci sera") == "1699999999"


@pytest.mark.asyncio
async def test_resolve_automation_id_by_alias_ambiguous_or_absent_is_none(client):
    client.get_automations = AsyncMock(return_value=[
        {"entity_id": "automation.a", "attributes": {"friendly_name": "Dup", "id": "1"}},
        {"entity_id": "automation.b", "attributes": {"friendly_name": "Dup", "id": "2"}},
    ])
    assert await client.resolve_automation_id_by_alias("Dup") is None          # ambiguo
    assert await client.resolve_automation_id_by_alias("Inesistente") is None  # assente


@pytest.mark.asyncio
async def test_resolve_automation_id_by_alias_failsafe_on_error(client):
    client.get_automations = AsyncMock(side_effect=Exception("boom"))
    assert await client.resolve_automation_id_by_alias("x") is None


def _capture_post(posted):
    def _post(url, json=None):
        posted["url"] = url
        posted["body"] = json
        return _get_mock(status=200, json_body={})
    return _post


@pytest.mark.asyncio
async def test_create_automation_overwrites_by_alias_when_id_missing(client):
    client.get_automations = AsyncMock(return_value=[
        {"entity_id": "automation.luci", "attributes": {"friendly_name": "Luci sera", "id": "1699999999"}},
    ])
    client.call_service = AsyncMock(return_value=True)  # salta il reload reale
    posted = {}
    client._session = MagicMock()
    client._session.post = MagicMock(side_effect=_capture_post(posted))

    res = await client.create_automation({"alias": "Luci sera", "trigger": [], "action": []})

    assert res.get("ok") is True and res["id"] == "1699999999", res
    assert posted["url"].endswith("/api/config/automation/config/1699999999")
    assert posted["body"]["id"] == "1699999999"  # id coerente nel body scritto


@pytest.mark.asyncio
async def test_create_automation_mints_new_when_no_alias_match(client):
    client.get_automations = AsyncMock(return_value=[])  # nessun match
    client.call_service = AsyncMock(return_value=True)
    posted = {}
    client._session = MagicMock()
    client._session.post = MagicMock(side_effect=_capture_post(posted))

    res = await client.create_automation({"alias": "Nuova", "trigger": [], "action": []})

    assert res.get("ok") is True
    assert res["id"].isdigit() and res["id"] != "1699999999"  # id coniato, non esistente
    assert posted["url"].endswith("/api/config/automation/config/" + res["id"])
