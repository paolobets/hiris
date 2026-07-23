import pytest
from aiohttp import web
from hiris.app.api.handlers_entities import handle_list_entities, filter_entities


def _states():
    return [
        {"id": "sensor.freezer", "name": "Freezer", "device_class": "temperature", "state": "-18"},
        {"id": "sensor.batt_porta", "name": "Batt Porta", "device_class": "battery", "state": "80"},
        {"id": "switch.irr", "name": "Irrigazione", "device_class": None, "state": "off"},
    ]


def test_filter_by_device_class():
    out = filter_entities(_states(), None, {"temperature"})
    assert [e["entity_id"] for e in out] == ["sensor.freezer"]
    assert out[0]["friendly_name"] == "Freezer" and out[0]["domain"] == "sensor"


def test_filter_by_domain():
    out = filter_entities(_states(), {"switch"}, None)
    assert [e["entity_id"] for e in out] == ["switch.irr"]


def test_no_filter_returns_all():
    assert len(filter_entities(_states(), None, None)) == 3


class _Cache:
    def __init__(self, s):
        self._s = s

    def all_states(self):
        return self._s


@pytest.mark.asyncio
async def test_handler_filters(aiohttp_client):
    app = web.Application()
    app["entity_cache"] = _Cache(_states())
    app.router.add_get("/api/entities", handle_list_entities)
    client = await aiohttp_client(app)
    r = await client.get("/api/entities?device_class=battery")
    body = await r.json()
    assert [e["entity_id"] for e in body["entities"]] == ["sensor.batt_porta"]
