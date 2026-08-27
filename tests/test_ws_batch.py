"""_ws_batch: N comandi su una connessione sola.

Il finto WebSocket registra quante volte si e' connesso: e' la cosa che questi
test difendono davvero, perche' prima ogni lettura ne apriva una nuova.
"""
from unittest.mock import patch

import pytest

from hiris.app.proxy.ha_client import HAClient


class _FintoWS:
    def __init__(self, registro):
        self._registro = registro
        self._ricevuti = []
        self._da_consegnare = [{"type": "auth_required"}]

    async def receive_json(self):
        if self._da_consegnare:
            return self._da_consegnare.pop(0)
        raise AssertionError("nessun messaggio da consegnare")

    async def send_json(self, payload):
        self._ricevuti.append(payload)
        if payload.get("type") == "auth":
            self._da_consegnare.append({"type": "auth_ok"})
            return
        self._registro["comandi"].append(payload)
        self._da_consegnare.append({
            "id": payload["id"], "type": "result", "success": True,
            "result": [{"eco": payload["type"]}],
        })

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FintaSessione:
    def __init__(self, registro):
        self._registro = registro

    def ws_connect(self, url):
        self._registro["connessioni"] += 1
        return _FintoWS(self._registro)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


@pytest.fixture
def registro():
    return {"connessioni": 0, "comandi": []}


def _client():
    return HAClient(base_url="http://ha.test", token="t")


@pytest.mark.asyncio
async def test_sei_comandi_una_connessione_sola(registro):
    comandi = [(f"comando/{i}", None) for i in range(6)]
    with patch("aiohttp.ClientSession", lambda *a, **k: _FintaSessione(registro)):
        risposte = await _client()._ws_batch(comandi)
    assert registro["connessioni"] == 1
    assert len(risposte) == 6
    assert [r["result"][0]["eco"] for r in risposte] == [f"comando/{i}" for i in range(6)]


@pytest.mark.asyncio
async def test_le_risposte_seguono_l_ordine_dei_comandi(registro):
    with patch("aiohttp.ClientSession", lambda *a, **k: _FintaSessione(registro)):
        risposte = await _client()._ws_batch([("primo", None), ("secondo", {"x": 1})])
    assert risposte[0]["result"][0]["eco"] == "primo"
    assert risposte[1]["result"][0]["eco"] == "secondo"
    assert registro["comandi"][1]["x"] == 1


@pytest.mark.asyncio
async def test_nessun_comando_nessuna_connessione(registro):
    with patch("aiohttp.ClientSession", lambda *a, **k: _FintaSessione(registro)):
        assert await _client()._ws_batch([]) == []
    assert registro["connessioni"] == 0


@pytest.mark.asyncio
async def test_ws_request_restituisce_il_solo_risultato(registro):
    with patch("aiohttp.ClientSession", lambda *a, **k: _FintaSessione(registro)):
        risultato = await _client()._ws_request("qualcosa")
    assert risultato == [{"eco": "qualcosa"}]


@pytest.mark.asyncio
async def test_ws_command_restituisce_il_messaggio_intero(registro):
    with patch("aiohttp.ClientSession", lambda *a, **k: _FintaSessione(registro)):
        msg = await _client()._ws_command("qualcosa")
    assert msg["success"] is True
    assert msg["id"] == 1


@pytest.mark.asyncio
async def test_una_connessione_fallita_non_solleva(registro):
    def esplode(*a, **k):
        raise OSError("rete assente")
    with patch("aiohttp.ClientSession", esplode):
        assert await _client()._ws_batch([("a", None), ("b", None)]) == [None, None]
