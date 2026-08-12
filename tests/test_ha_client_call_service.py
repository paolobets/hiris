import pytest
from hiris.app.proxy.ha_client import HAClient


class FintaRisposta:
    def __init__(self, payload, stato=200):
        self._payload = payload
        self.status = stato

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def json(self):
        return self._payload


class FintaSessione:
    def __init__(self, payload, stato=200):
        self.payload = payload
        self.stato = stato
        self.chiamate = []

    def post(self, url, json=None):
        self.chiamate.append((url, json))
        return FintaRisposta(self.payload, self.stato)


@pytest.mark.asyncio
async def test_call_service_compone_url_e_corpo():
    client = HAClient("http://ha.local:8123", "token")
    client._session = FintaSessione([{"entity_id": "light.salotto", "state": "off"}])
    cambiati = await client.call_service(
        "light", "turn_off", {"entity_id": "light.salotto"})
    url, corpo = client._session.chiamate[0]
    assert url == "http://ha.local:8123/api/services/light/turn_off"
    assert corpo == {"entity_id": "light.salotto"}
    assert cambiati == [{"entity_id": "light.salotto", "state": "off"}]


@pytest.mark.asyncio
async def test_call_service_propaga_il_rifiuto_di_home_assistant():
    client = HAClient("http://ha.local:8123", "token")
    client._session = FintaSessione({}, stato=400)
    with pytest.raises(RuntimeError):
        await client.call_service("light", "turn_off", {"entity_id": "light.x"})
