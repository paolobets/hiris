"""Tests for the canonical /api/entities handler (hiris.app.api.handlers_entities).

SP-4 Fase B Task 1: handlers_entities.handle_list_entities is now the ONLY
implementation of /api/entities. The unreachable flat-array copy that used to
live in handlers_chatbots.py has been deleted; its 5 tests are moved here,
rewritten against the canonical wrapped shape
({"entities": [{entity_id, friendly_name, domain, device_class, state}]})
instead of the dead code's flat array ({id, name, state, domain}).
"""
import pytest
from aiohttp import web

from hiris.app.api.handlers_entities import handle_list_entities


class _Cache:
    def all_states(self):
        return [
            {"id": "light.salotto", "name": "Luce Salotto", "state": "on",
             "domain": "light", "device_class": None},
            {"id": "sensor.porta_bat", "name": "Batteria Porta", "state": "80",
             "domain": "sensor", "device_class": "battery"},
        ]


def _app(cache=None):
    app = web.Application()
    app["entity_cache"] = cache if cache is not None else _Cache()
    app.router.add_get("/api/entities", handle_list_entities)
    return app


# ---------------------------------------------------------------------------
# Step 1 (brief): `q` filtering on the canonical handler
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_q_filters_by_id_and_name(aiohttp_client):
    client = await aiohttp_client(_app())
    r = await client.get("/api/entities?q=salotto")
    body = await r.json()
    ids = [e["entity_id"] for e in body["entities"]]
    assert ids == ["light.salotto"]

    r2 = await client.get("/api/entities?q=BATTERIA")   # case-insensitive, su friendly_name
    assert [e["entity_id"] for e in (await r2.json())["entities"]] == ["sensor.porta_bat"]


@pytest.mark.asyncio
async def test_shape_is_always_wrapped_with_entities_key(aiohttp_client):
    client = await aiohttp_client(_app())
    body = await (await client.get("/api/entities")).json()
    assert isinstance(body, dict) and "entities" in body
    e = body["entities"][0]
    assert {"entity_id", "friendly_name", "domain"} <= set(e)


@pytest.mark.asyncio
async def test_q_combines_with_domain(aiohttp_client):
    client = await aiohttp_client(_app())
    body = await (await client.get("/api/entities?q=a&domain=sensor")).json()
    assert [e["entity_id"] for e in body["entities"]] == ["sensor.porta_bat"]


# ---------------------------------------------------------------------------
# Moved + rewritten from tests/test_handlers_chatbots.py (Step 4 of the brief).
#
# These 5 tests originally exercised handlers_chatbots.handle_list_entities,
# an unreachable copy never registered on any route (server.py registers
# handlers_entities.handle_list_entities instead) -- they were green on dead
# code and gave false confidence. Rewritten here against the real handler and
# its canonical wrapped/keyed shape.
# ---------------------------------------------------------------------------

class _SortCache:
    def __init__(self, states):
        self._states = states

    def all_states(self):
        return self._states


@pytest.mark.asyncio
async def test_list_entities_returns_all_entities(aiohttp_client):
    cache = _SortCache([
        {"id": "switch.relay", "state": "off",  "name": "Relay",   "domain": "switch"},
        {"id": "light.salon",  "state": "on",   "name": "Salon",   "domain": "light"},
        {"id": "sensor.temp",  "state": "21.5", "name": "Temp",    "domain": "sensor"},
    ])
    client = await aiohttp_client(_app(cache))
    body = await (await client.get("/api/entities")).json()
    entities = body["entities"]

    assert len(entities) == 3
    ids = {e["entity_id"] for e in entities}
    assert ids == {"switch.relay", "light.salon", "sensor.temp"}
    for e in entities:
        assert e["domain"] == e["entity_id"].split(".")[0]


@pytest.mark.asyncio
async def test_list_entities_search_filter(aiohttp_client):
    cache = _SortCache([
        {"id": "light.salon",   "state": "on",  "name": "Salon Light", "domain": "light"},
        {"id": "sensor.temp",   "state": "21",  "name": "Temperature", "domain": "sensor"},
        {"id": "light.kitchen", "state": "off", "name": "Kitchen",     "domain": "light"},
    ])
    client = await aiohttp_client(_app(cache))
    body = await (await client.get("/api/entities?q=light")).json()
    entities = body["entities"]
    assert entities  # the bug: these used to vanish behind an unregistered route
    assert all(
        "light" in e["entity_id"] or "light" in e["friendly_name"].lower()
        for e in entities
    )


@pytest.mark.asyncio
async def test_list_entities_empty_cache(aiohttp_client):
    client = await aiohttp_client(_app(_SortCache([])))
    body = await (await client.get("/api/entities")).json()
    assert body["entities"] == []


@pytest.mark.asyncio
async def test_list_entities_missing_name_field(aiohttp_client):
    cache = _SortCache([
        {"id": "sensor.weird", "state": "unavailable"},  # no "name", no "domain"
    ])
    client = await aiohttp_client(_app(cache))
    body = await (await client.get("/api/entities")).json()
    entities = body["entities"]
    assert len(entities) == 1
    # `None`, MAI l'entity_id. Questa prova asseriva il contrario -- cioe'
    # DOCUMENTAVA il difetto: un id tecnico spacciato per nome, e chi legge
    # senza modo di sapere se «sensor.weird» fosse un nome vero o un ripiego.
    # E' la disciplina opposta a quella che `costruisci_indice` dichiara e
    # rispetta: «un id tecnico non entra qui, ne' tale e quale ne' ingentilito».
    # L'`entity_id` e' nella stessa riga: chi vuole ripiegare lo fa sapendo
    # cosa sta mostrando.
    assert entities[0]["friendly_name"] is None
    assert entities[0]["entity_id"] == "sensor.weird"
    assert entities[0]["domain"] == "sensor"


@pytest.mark.asyncio
async def test_list_entities_search_case_insensitive(aiohttp_client):
    cache = _SortCache([
        {"id": "light.salon", "state": "on", "name": "Luce Soggiorno", "domain": "light"},
    ])
    client = await aiohttp_client(_app(cache))
    body = await (await client.get("/api/entities?q=SOGGIORNO")).json()
    entities = body["entities"]
    assert len(entities) == 1
    assert entities[0]["entity_id"] == "light.salon"
