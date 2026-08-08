"""Test per le tre letture diagnostiche di HAClient:
system_health (WS), logbook (REST) e render_template (REST).

Stile: fake della sessione aiohttp + asserzione sull'URL esatto chiamato.
Tutti i metodi sono di sola lettura e degradano in silenzio: nessuna
eccezione deve mai raggiungere il chiamante.
"""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, parse_qs, unquote

import pytest
from unittest.mock import AsyncMock, MagicMock

from hiris.app.proxy.ha_client import (
    HAClient,
    MAX_LOGBOOK_ENTRIES,
    MAX_LOGBOOK_HOURS,
    MAX_TEMPLATE_LEN,
    MAX_TEMPLATE_RESPONSE_LEN,
    _truncate,
)


@pytest.fixture
def client():
    return HAClient(base_url="http://supervisor/core", token="test-token")


def _resp(status=200, text=None, json_data=None):
    """Risposta aiohttp finta usabile come context manager asincrono."""
    resp = AsyncMock()
    resp.status = status
    resp.raise_for_status = MagicMock()
    resp.text = AsyncMock(return_value=text if text is not None else "")
    resp.json = AsyncMock(return_value=json_data)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _fake_session(client, method, resp=None, exc=None):
    """Installa una sessione finta su client e ritorna la lista delle chiamate
    registrate come (url, kwargs)."""
    calls = []

    def _call(url, *args, **kwargs):
        calls.append((url, kwargs))
        if exc is not None:
            raise exc
        return resp

    client._session = MagicMock()
    setattr(client._session, method, MagicMock(side_effect=_call))
    return calls


def _start_ore_indietro(url: str) -> float:
    """Quante ore indietro rispetto ad adesso punta lo start ISO nel path."""
    parsed = urlsplit(url)
    start = datetime.fromisoformat(unquote(parsed.path.split("/api/logbook/")[1]))
    return (datetime.now(timezone.utc) - start).total_seconds() / 3600


# --------------------------------------------------------------------------
# get_system_health
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_system_health_maps_domains(client, monkeypatch):
    """Mappa dominio -> informazioni; i valori "tipizzati" di HA vengono
    appiattiti e le forme non riconosciute ignorate senza sollevare."""
    captured = {}

    async def fake_ws_request(msg_type, extra=None, timeout=10.0):
        captured["msg_type"] = msg_type
        return {
            "homeassistant": {"info": {"version": "2026.7.1",
                                       "installation_type": "Home Assistant OS",
                                       "dev": False}},
            "cloud": {"info": {"logged_in": True,
                               "subscription_expiration": {"type": "date",
                                                           "value": "2027-01-01"}}},
            "mqtt": {"info": {"broker": {"type": "failed",
                                         "error": "connection refused"}}},
            "recorder": {"info": {"oldest_recorder_run": {"type": "pending"}}},
            # forme inattese: vanno ignorate, non devono far esplodere nulla
            "rotto": "non e' un dict",
            "vuoto": {},
            "senza_info": {"can_reach_server": "ok"},
        }

    monkeypatch.setattr(client, "_ws_request", fake_ws_request)
    out = await client.get_system_health()

    assert captured["msg_type"] == "system_health/info"
    assert out["homeassistant"] == {"version": "2026.7.1",
                                    "installation_type": "Home Assistant OS",
                                    "dev": False}
    assert out["cloud"] == {"logged_in": True,
                            "subscription_expiration": "2027-01-01"}
    assert out["mqtt"] == {"broker": "connection refused"}
    assert out["recorder"] == {"oldest_recorder_run": "pending"}
    assert out["senza_info"] == {"can_reach_server": "ok"}
    assert "rotto" not in out
    assert "vuoto" not in out


@pytest.mark.asyncio
async def test_get_system_health_empty_on_ws_failure(client, monkeypatch):
    async def fake_ws_request(msg_type, extra=None, timeout=10.0):
        return None

    monkeypatch.setattr(client, "_ws_request", fake_ws_request)
    assert await client.get_system_health() == {}


@pytest.mark.asyncio
async def test_get_system_health_empty_on_unexpected_shape(client, monkeypatch):
    """Il formato di system_health/info non e' documentato: se HA risponde con
    qualcosa che non e' una mappa, il dato vale semplicemente "non disponibile"."""
    async def fake_ws_request(msg_type, extra=None, timeout=10.0):
        return ["non", "una", "mappa"]

    monkeypatch.setattr(client, "_ws_request", fake_ws_request)
    assert await client.get_system_health() == {}


@pytest.mark.asyncio
async def test_get_system_health_never_raises(client, monkeypatch):
    async def fake_ws_request(msg_type, extra=None, timeout=10.0):
        raise OSError("ws down")

    monkeypatch.setattr(client, "_ws_request", fake_ws_request)
    assert await client.get_system_health() == {}


# --------------------------------------------------------------------------
# get_logbook
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_logbook_builds_url_without_entity(client):
    """Senza entity_id: path /api/logbook/<start ISO>, nessun parametro entity,
    end_time presente. Lo start deve corrispondere a now - hours."""
    calls = _fake_session(client, "get", _resp(200, json_data=[]))
    await client.get_logbook(entity_id=None, hours=6)

    url = calls[0][0]
    parsed = urlsplit(url)
    assert parsed.path.startswith("/core/api/logbook/")
    start = datetime.fromisoformat(unquote(parsed.path.split("/api/logbook/")[1]))
    atteso = datetime.now(timezone.utc) - timedelta(hours=6)
    assert abs((start - atteso).total_seconds()) < 60

    qs = parse_qs(parsed.query)
    assert "entity" not in qs
    end = datetime.fromisoformat(qs["end_time"][0])
    assert abs((end - datetime.now(timezone.utc)).total_seconds()) < 60


@pytest.mark.asyncio
async def test_get_logbook_includes_entity_param(client):
    calls = _fake_session(client, "get", _resp(200, json_data=[]))
    await client.get_logbook(entity_id="light.cucina", hours=1)

    qs = parse_qs(urlsplit(calls[0][0]).query)
    assert qs["entity"] == ["light.cucina"]


@pytest.mark.asyncio
async def test_get_logbook_extracts_fields(client):
    payload = [
        {"when": "2026-08-01T10:00:00+00:00", "name": "Luce cucina",
         "message": "e' stata accesa", "entity_id": "light.cucina",
         "domain": "light", "context_user_id": "abc"},
        {"when": "2026-08-01T10:05:00+00:00", "name": "Luce cucina",
         "message": "e' stata spenta", "entity_id": "light.cucina"},
    ]
    _fake_session(client, "get", _resp(200, json_data=payload))
    out = await client.get_logbook(entity_id="light.cucina", hours=2)

    assert out == [
        {"when": "2026-08-01T10:00:00+00:00", "name": "Luce cucina",
         "message": "e' stata accesa", "entity_id": "light.cucina"},
        {"when": "2026-08-01T10:05:00+00:00", "name": "Luce cucina",
         "message": "e' stata spenta", "entity_id": "light.cucina"},
    ]


@pytest.mark.asyncio
async def test_get_logbook_empty_on_bad_status(client):
    _fake_session(client, "get", _resp(404, json_data=[]))
    assert await client.get_logbook(entity_id=None, hours=1) == []


@pytest.mark.asyncio
async def test_get_logbook_empty_on_non_list_payload(client):
    _fake_session(client, "get", _resp(200, json_data={"message": "boom"}))
    assert await client.get_logbook(entity_id=None, hours=1) == []


@pytest.mark.asyncio
async def test_get_logbook_empty_on_exception(client):
    _fake_session(client, "get", exc=OSError("connection refused"))
    assert await client.get_logbook(entity_id=None, hours=1) == []


@pytest.mark.asyncio
async def test_get_logbook_caps_entries_keeping_most_recent(client):
    """Il logbook di una settimana puo' essere enorme e finirebbe nel prompt:
    si tiene solo la coda piu' recente, fino al cap dichiarato."""
    payload = [{"when": f"t{i}", "name": "n", "message": "m",
                "entity_id": "light.cucina"}
               for i in range(MAX_LOGBOOK_ENTRIES + 50)]
    _fake_session(client, "get", _resp(200, json_data=payload))
    out = await client.get_logbook(entity_id=None, hours=168)

    assert len(out) == MAX_LOGBOOK_ENTRIES
    assert out[-1]["when"] == f"t{MAX_LOGBOOK_ENTRIES + 49}"
    assert out[0]["when"] == "t50"


@pytest.mark.asyncio
async def test_get_logbook_rejects_invalid_entity_id(client):
    """entity_id ostile: mai comporre l'URL, nessuna chiamata HTTP."""
    calls = _fake_session(client, "get", _resp(200, json_data=[]))
    assert await client.get_logbook(entity_id="light.cucina&evil=1", hours=1) == []
    assert calls == []


@pytest.mark.asyncio
async def test_get_logbook_skips_non_dict_entries(client):
    _fake_session(client, "get", _resp(200, json_data=[
        "non un dict",
        {"when": "t", "name": "n", "message": "m", "entity_id": "light.x"},
    ]))
    out = await client.get_logbook(entity_id=None, hours=1)
    assert out == [{"when": "t", "name": "n", "message": "m",
                    "entity_id": "light.x"}]


@pytest.mark.asyncio
async def test_get_logbook_caps_after_filtering(client):
    """Il cap si applica DOPO aver scartato le voci non valide: altrimenti si
    restituiscono meno voci del massimo pur avendone di valide piu' vecchie."""
    payload = [{"when": f"t{i}", "name": "n", "message": "m",
                "entity_id": "light.cucina"}
               for i in range(MAX_LOGBOOK_ENTRIES)]
    payload += ["non un dict"] * 100
    _fake_session(client, "get", _resp(200, json_data=payload))
    out = await client.get_logbook(entity_id=None, hours=24)

    assert len(out) == MAX_LOGBOOK_ENTRIES
    assert out[0]["when"] == "t0"


# --- normalizzazione di `hours` -------------------------------------------
# `hours` arriva direttamente da una tool-call dell'LLM: puo' essere assurdo o
# allucinato. Nessun valore deve mai sollevare verso il chiamante.

_ORE_OSTILI = [-5, 0, None, "abc", float("nan"), float("inf"), 18_000_000, 10**12]


@pytest.mark.asyncio
@pytest.mark.parametrize("hours", _ORE_OSTILI)
async def test_get_logbook_never_raises_on_hostile_hours(client, hours):
    _fake_session(client, "get", _resp(200, json_data=[]))
    assert await client.get_logbook(entity_id=None, hours=hours) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("hours", [-5, 0, 0.4])
async def test_get_logbook_clamps_hours_to_minimum(client, hours):
    """Finestra non positiva: si clampa a un'ora, non si sbaglia il verso."""
    calls = _fake_session(client, "get", _resp(200, json_data=[]))
    await client.get_logbook(entity_id=None, hours=hours)

    assert abs(_start_ore_indietro(calls[0][0]) - 1) < 0.02


@pytest.mark.asyncio
@pytest.mark.parametrize("hours", [None, "abc", float("nan"), object()])
async def test_get_logbook_falls_back_on_non_numeric_hours(client, hours):
    """Valore non convertibile: finestra di default di 24 ore."""
    calls = _fake_session(client, "get", _resp(200, json_data=[]))
    await client.get_logbook(entity_id=None, hours=hours)

    assert abs(_start_ore_indietro(calls[0][0]) - 24) < 0.02


@pytest.mark.asyncio
@pytest.mark.parametrize("hours", [float("inf"), 18_000_000, 10**12,
                                   MAX_LOGBOOK_HOURS + 1])
async def test_get_logbook_clamps_hours_to_maximum(client, hours):
    """Valori enormi: la finestra e' limitata a MAX_LOGBOOK_HOURS, cosi' HA non
    deve scandire l'intero database del recorder."""
    calls = _fake_session(client, "get", _resp(200, json_data=[]))
    await client.get_logbook(entity_id=None, hours=hours)

    assert abs(_start_ore_indietro(calls[0][0]) - MAX_LOGBOOK_HOURS) < 0.02


# --------------------------------------------------------------------------
# _truncate
# --------------------------------------------------------------------------

def test_truncate_never_exceeds_cap():
    """Il contratto e' "marcatore incluso nel cap": con un cap troppo piccolo
    per ospitarlo si taglia e basta, ma il cap non si sfora mai."""
    assert _truncate("abc", 10) == "abc"
    for cap in (0, 1, 5, 10, 11, 12, 50):
        assert len(_truncate("x" * 5000, cap)) <= cap
    lungo = _truncate("x" * 5000, 100)
    assert len(lungo) == 100 and lungo.endswith("[troncato]")


# --------------------------------------------------------------------------
# render_template
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_render_template_posts_and_returns_text(client):
    """POST /api/template con body {"template": ...}; la risposta e' TESTO,
    non JSON."""
    calls = _fake_session(client, "post", _resp(200, text="21.5"))
    out = await client.render_template("{{ states('sensor.temp') }}")

    assert out == {"result": "21.5"}
    url, kwargs = calls[0]
    assert url == "http://supervisor/core/api/template"
    assert kwargs["json"] == {"template": "{{ states('sensor.temp') }}"}


@pytest.mark.asyncio
async def test_render_template_truncates_long_result(client):
    _fake_session(client, "post", _resp(200, text="x" * (MAX_TEMPLATE_RESPONSE_LEN * 2)))
    out = await client.render_template("{{ states }}")

    assert len(out["result"]) <= MAX_TEMPLATE_RESPONSE_LEN
    assert "troncato" in out["result"]


@pytest.mark.asyncio
async def test_render_template_returns_truncated_ha_error(client):
    """Il messaggio d'errore del template serve all'LLM per correggersi, ma HA
    puo' allegarci un traceback intero: va restituito TRONCATO."""
    body = "Error rendering template: UndefinedError: 'x' is undefined\n" + \
           "Traceback (most recent call last):\n" + ("  file riga\n" * 500)
    _fake_session(client, "post", _resp(400, text=body))
    out = await client.render_template("{{ x }}")

    assert "result" not in out
    assert "UndefinedError" in out["error"]
    assert len(out["error"]) <= MAX_TEMPLATE_RESPONSE_LEN


@pytest.mark.asyncio
async def test_render_template_rejects_too_long_template(client):
    calls = _fake_session(client, "post", _resp(200, text="ok"))
    out = await client.render_template("x" * (MAX_TEMPLATE_LEN + 1))

    assert "error" in out and "result" not in out
    assert calls == []


@pytest.mark.asyncio
async def test_render_template_rejects_empty_template(client):
    calls = _fake_session(client, "post", _resp(200, text="ok"))
    for bad in ("", "   ", None, 42):
        out = await client.render_template(bad)
        assert "error" in out and "result" not in out
    assert calls == []


@pytest.mark.asyncio
async def test_render_template_error_on_exception_without_echoing_exc(client):
    """Degrado silenzioso: errore generico, mai l'eco di str(exc)."""
    _fake_session(client, "post", exc=OSError("segreto interno 12345"))
    out = await client.render_template("{{ 1 + 1 }}")

    assert "error" in out
    assert "segreto interno" not in out["error"]
