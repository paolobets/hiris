"""Test per le tre letture diagnostiche di HAClient:
system_health (WS), diario (REST) e render_template (REST).

Stile: fake della sessione aiohttp + asserzione sull'URL esatto chiamato.
Tutti i metodi sono di sola lettura e degradano senza sollevare: `diario`
distingue pero' il vuoto dal guasto, vedi tests/test_ha_client_tempo.py.
"""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, parse_qs, unquote

import pytest
from unittest.mock import AsyncMock, MagicMock

from hiris.app.proxy.ha_client import (
    HAClient,
    MAX_DIARIO_VOCI,
    MAX_DIARIO_ORE,
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
# diario (era get_logbook)
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_diario_builds_url_without_entity(client):
    """Senza entita': path /api/logbook/<start ISO>, nessun parametro entity,
    end_time presente. Lo start deve corrispondere a now - ore."""
    calls = _fake_session(client, "get", _resp(200, json_data=[]))
    await client.diario(entita=None, ore=6)

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
async def test_diario_includes_entity_param(client):
    calls = _fake_session(client, "get", _resp(200, json_data=[]))
    await client.diario(entita="light.cucina", ore=1)

    qs = parse_qs(urlsplit(calls[0][0]).query)
    assert qs["entity"] == ["light.cucina"]


@pytest.mark.asyncio
async def test_diario_extracts_fields(client):
    payload = [
        {"when": "2026-08-01T10:00:00+00:00", "name": "Luce cucina",
         "message": "e' stata accesa", "entity_id": "light.cucina",
         "domain": "light", "context_user_id": "abc"},
        {"when": "2026-08-01T10:05:00+00:00", "name": "Luce cucina",
         "message": "e' stata spenta", "entity_id": "light.cucina"},
    ]
    _fake_session(client, "get", _resp(200, json_data=payload))
    esito = await client.diario(entita="light.cucina", ore=2)

    assert esito == {"voci": [
        {"quando": "2026-08-01T10:00:00+00:00", "nome": "Luce cucina",
         "messaggio": "e' stata accesa", "entita": "light.cucina"},
        {"quando": "2026-08-01T10:05:00+00:00", "nome": "Luce cucina",
         "messaggio": "e' stata spenta", "entita": "light.cucina"},
    ], "troncato": False, "ore": 2}


@pytest.mark.asyncio
async def test_diario_un_guasto_non_e_un_diario_vuoto_bad_status(client):
    _fake_session(client, "get", _resp(404, json_data=[]))
    esito = await client.diario(entita=None, ore=1)
    assert "voci" not in esito
    assert "errore" in esito


@pytest.mark.asyncio
async def test_diario_un_guasto_non_e_un_diario_vuoto_payload(client):
    _fake_session(client, "get", _resp(200, json_data={"message": "boom"}))
    esito = await client.diario(entita=None, ore=1)
    assert "voci" not in esito
    assert "errore" in esito


@pytest.mark.asyncio
async def test_diario_un_guasto_non_e_un_diario_vuoto_exception(client):
    _fake_session(client, "get", exc=OSError("connection refused"))
    esito = await client.diario(entita=None, ore=1)
    assert "voci" not in esito
    assert "errore" in esito


@pytest.mark.asyncio
async def test_diario_caps_entries_keeping_most_recent(client):
    """Il diario di una settimana puo' essere enorme e finirebbe nel prompt:
    si tiene solo la coda piu' recente, fino al cap dichiarato -- e il
    troncamento e' dichiarato invece che dedotto."""
    payload = [{"when": f"t{i}", "name": "n", "message": "m",
                "entity_id": "light.cucina"}
               for i in range(MAX_DIARIO_VOCI + 50)]
    _fake_session(client, "get", _resp(200, json_data=payload))
    esito = await client.diario(entita=None, ore=168)

    assert len(esito["voci"]) == MAX_DIARIO_VOCI
    assert esito["voci"][-1]["quando"] == f"t{MAX_DIARIO_VOCI + 49}"
    assert esito["voci"][0]["quando"] == "t50"
    assert esito["troncato"] is True
    assert esito["ore"] == 168


@pytest.mark.asyncio
async def test_diario_rejects_invalid_entity_id(client):
    """entita' ostile: mai comporre l'URL, nessuna chiamata HTTP, e il
    rifiuto e' un guasto dichiarato -- non un diario vuoto."""
    calls = _fake_session(client, "get", _resp(200, json_data=[]))
    esito = await client.diario(entita="light.cucina&evil=1", ore=1)
    assert "voci" not in esito
    assert "errore" in esito
    assert calls == []


@pytest.mark.asyncio
async def test_diario_skips_non_dict_entries(client):
    _fake_session(client, "get", _resp(200, json_data=[
        "non un dict",
        {"when": "t", "name": "n", "message": "m", "entity_id": "light.x"},
    ]))
    esito = await client.diario(entita=None, ore=1)
    assert esito["voci"] == [{"quando": "t", "nome": "n", "messaggio": "m",
                              "entita": "light.x"}]
    assert esito["troncato"] is False


@pytest.mark.asyncio
async def test_diario_caps_after_filtering(client):
    """Il cap si applica DOPO aver scartato le voci non valide: altrimenti si
    restituiscono meno voci del massimo pur avendone di valide piu' vecchie."""
    payload = [{"when": f"t{i}", "name": "n", "message": "m",
                "entity_id": "light.cucina"}
               for i in range(MAX_DIARIO_VOCI)]
    payload += ["non un dict"] * 100
    _fake_session(client, "get", _resp(200, json_data=payload))
    esito = await client.diario(entita=None, ore=24)

    assert len(esito["voci"]) == MAX_DIARIO_VOCI
    assert esito["voci"][0]["quando"] == "t0"
    assert esito["troncato"] is False


# --- normalizzazione di `ore` -----------------------------------------------
# `ore` arriva direttamente da una tool-call dell'LLM: puo' essere assurdo o
# allucinato. Nessun valore deve mai sollevare verso il chiamante.

_ORE_OSTILI = [-5, 0, None, "abc", float("nan"), float("inf"), 18_000_000, 10**12]


@pytest.mark.asyncio
@pytest.mark.parametrize("ore", _ORE_OSTILI)
async def test_diario_never_raises_on_hostile_ore(client, ore):
    _fake_session(client, "get", _resp(200, json_data=[]))
    esito = await client.diario(entita=None, ore=ore)
    assert esito["voci"] == []
    assert "errore" not in esito


@pytest.mark.asyncio
@pytest.mark.parametrize("ore", [-5, 0, 0.4])
async def test_diario_clamps_ore_to_minimum(client, ore):
    """Finestra non positiva: si clampa a un'ora, non si sbaglia il verso."""
    calls = _fake_session(client, "get", _resp(200, json_data=[]))
    esito = await client.diario(entita=None, ore=ore)

    assert abs(_start_ore_indietro(calls[0][0]) - 1) < 0.02
    assert esito["ore"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("ore", [None, "abc", float("nan"), object()])
async def test_diario_falls_back_on_non_numeric_ore(client, ore):
    """Valore non convertibile: finestra di default di 24 ore."""
    calls = _fake_session(client, "get", _resp(200, json_data=[]))
    esito = await client.diario(entita=None, ore=ore)

    assert abs(_start_ore_indietro(calls[0][0]) - 24) < 0.02
    assert esito["ore"] == 24


@pytest.mark.asyncio
@pytest.mark.parametrize("ore", [float("inf"), 18_000_000, 10**12,
                                 MAX_DIARIO_ORE + 1])
async def test_diario_clamps_ore_to_maximum(client, ore):
    """Valori enormi: la finestra e' limitata a MAX_DIARIO_ORE, cosi' HA non
    deve scandire l'intero database del recorder."""
    calls = _fake_session(client, "get", _resp(200, json_data=[]))
    esito = await client.diario(entita=None, ore=ore)

    assert abs(_start_ore_indietro(calls[0][0]) - MAX_DIARIO_ORE) < 0.02
    assert esito["ore"] == MAX_DIARIO_ORE


@pytest.mark.asyncio
async def test_diario_usa_il_suo_tetto_non_quello_di_tempo():
    """L'unificazione di normalizza_ore: diario ha tetto 168, tempo.py ha tetto
    2160. Questo test verifica che diario usi il suo tetto specifico. Se togli
    tetto=MAX_DIARIO_ORE dalla chiamata di normalizza_ore in ha_client.py, il
    diario clatherebbe il valore 200 a 2160 invece di 168 e il test
    fallirebbe."""
    client = HAClient(base_url="http://supervisor/core", token="test-token")
    calls = _fake_session(client, "get", _resp(200, json_data=[]))
    # 200 ore: fra il tetto di diario (168) e il tetto di tempo (2160)
    esito = await client.diario(entita=None, ore=200)

    # Con il tetto corretto di diario (168), la finestra inizia 168 ore indietro
    assert abs(_start_ore_indietro(calls[0][0]) - MAX_DIARIO_ORE) < 0.02
    assert esito["ore"] == MAX_DIARIO_ORE


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


# --- La forma VERA del logbook, misurata sulla casa il 24/08/2026 -----


@pytest.mark.asyncio
async def test_diario_il_testo_di_un_cambio_di_stato_vive_in_state(client):
    """La misura del 24/08/2026: su 755 voci vere, **754 portano `state` e una
    sola porta `message`**. Il diario proiettava solo `message`, quindi
    «accaduto» rispondeva con duecento voci che dicevano nome e ora e
    NIENT'ALTRO -- uno strumento che non poteva rispondere alla domanda per
    cui esiste.

    I due campi restano DUE, non si fondono: «on» e «entered zone Casa» sono
    fatti di natura diversa, e chi legge deve poterli distinguere.
    """
    corpo = [
        {"state": "on", "entity_id": "binary_sensor.movimento",
         "name": "Movimento", "when": "2026-08-24T16:34:04.487614+00:00"},
        {"name": "iPhone di Marta", "message": "entered zone Casa",
         "entity_id": "zone.home", "domain": "mobile_app",
         "when": "2026-08-24T17:05:55.727146+00:00"},
    ]
    _fake_session(client, "get", resp=_resp(200, json_data=corpo))
    esito = await client.diario(None, 3)
    assert esito["voci"][0]["stato"] == "on"
    assert esito["voci"][0]["messaggio"] is None
    assert esito["voci"][1]["messaggio"] == "entered zone Casa"
    assert esito["voci"][1]["stato"] is None
