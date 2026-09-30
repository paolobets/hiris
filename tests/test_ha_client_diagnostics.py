"""Test per le letture diagnostiche di HAClient:
render_template (REST) e `_truncate`. Il diario e' uscito il 30/09/2026 con
la storia, e con lei `get_system_health` (WS), senza chiamanti.

Stile: fake della sessione aiohttp + asserzione sull'URL esatto chiamato.
Tutti i metodi sono di sola lettura e degradano senza sollevare.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from hiris.app.proxy.ha_client import (
    MAX_TEMPLATE_LEN,
    MAX_TEMPLATE_RESPONSE_LEN,
    HAClient,
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


def test_truncate_e_la_stessa_funzione_di_sanitize():
    """M1 (revisione di agosto 2026): `ha_client.py::_truncate` e
    `_sanitize.py`'s `sanitize_text` usavano due implementazioni duplicate
    (stesso algoritmo, stessa costante) del taglio con marcatore. Ora
    `_truncate` E' `_sanitize.truncate_with_marker` -- non solo si comporta
    allo stesso modo, e' letteralmente lo stesso oggetto funzione, come il
    test di identita' introdotto per N1 in FIX1-report.md."""
    from hiris.app.proxy import _sanitize, ha_client
    assert ha_client._truncate is _sanitize.truncate_with_marker


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

