"""A3 — «non hai impegni domani» quando Home Assistant non ha risposto.

`get_calendar_events` restituiva un elenco vuoto sia quando i calendari erano
davvero senza eventi, sia quando l'elenco dei calendari non si era potuto
leggere; e ogni singolo calendario che falliva veniva saltato in silenzio, cosi'
un'agenda parziale sembrava completa. Il modello non aveva modo di distinguere,
e l'utente si sentiva dire che e' libero.
"""
from __future__ import annotations

import pytest

from hiris.app.tools.calendar_tools import get_calendar_events


class _HA:
    """Home Assistant finto: `calendari` puo' essere una lista o un'eccezione;
    `eventi` mappa entity_id -> lista di eventi oppure eccezione da sollevare."""

    def __init__(self, calendari=None, eventi=None):
        self._calendari = calendari if calendari is not None else []
        self._eventi = eventi or {}

    async def get_calendars(self):
        if isinstance(self._calendari, Exception):
            raise self._calendari
        return self._calendari

    async def get_calendar_events_range(self, entity_id, start, end):
        esito = self._eventi.get(entity_id, [])
        if isinstance(esito, Exception):
            raise esito
        return esito


def _evento(summary: str) -> dict:
    return {"summary": summary,
            "start": {"dateTime": "2026-08-03T10:00:00+00:00"},
            "end": {"dateTime": "2026-08-03T11:00:00+00:00"}}


@pytest.mark.asyncio
async def test_elenco_calendari_non_leggibile_e_un_guasto_non_unagenda_vuota():
    ha = _HA(calendari=RuntimeError("HA non raggiungibile su 192.168.1.95"))

    res = await get_calendar_events(ha, hours=24)

    assert isinstance(res, dict), "serve una forma che possa portare l'errore"
    assert res.get("error"), "il guasto va dichiarato al modello"
    assert res.get("events") == []
    # Il dettaglio dell'eccezione resta nel log del server.
    assert "192.168.1.95" not in res["error"]


@pytest.mark.asyncio
async def test_un_calendario_che_fallisce_non_viene_saltato_in_silenzio():
    ha = _HA(
        calendari=[{"entity_id": "calendar.casa"}, {"entity_id": "calendar.lavoro"}],
        eventi={
            "calendar.casa": [_evento("Dentista")],
            "calendar.lavoro": RuntimeError("timeout"),
        },
    )

    res = await get_calendar_events(ha, hours=24)

    assert [e["summary"] for e in res["events"]] == ["Dentista"]
    assert res.get("error"), "un'agenda parziale non deve sembrare completa"
    assert res.get("unavailable_calendars") == ["calendar.lavoro"]
    assert "timeout" not in res["error"]


@pytest.mark.asyncio
async def test_calendario_singolo_che_fallisce_e_un_guasto():
    ha = _HA(eventi={"calendar.lavoro": RuntimeError("timeout")})

    res = await get_calendar_events(ha, hours=24, calendar_entity="calendar.lavoro")

    assert res["events"] == []
    assert res.get("error")
    assert res.get("unavailable_calendars") == ["calendar.lavoro"]


@pytest.mark.asyncio
async def test_agenda_davvero_vuota_non_e_un_errore():
    """Il caso opposto, che deve restare distinguibile: i calendari si leggono
    e non c'e' nulla in programma."""
    ha = _HA(calendari=[{"entity_id": "calendar.casa"}], eventi={"calendar.casa": []})

    res = await get_calendar_events(ha, hours=24)

    assert res["events"] == []
    assert "error" not in res
    assert not res.get("unavailable_calendars")


@pytest.mark.asyncio
async def test_nessun_calendario_configurato_non_e_un_errore():
    res = await get_calendar_events(_HA(calendari=[]), hours=24)
    assert res["events"] == []
    assert "error" not in res


@pytest.mark.asyncio
async def test_eventi_ordinati_e_marcati_col_calendario_di_provenienza():
    ha = _HA(
        calendari=[{"entity_id": "calendar.casa"}, {"entity_id": "calendar.lavoro"}],
        eventi={
            "calendar.casa": [{"summary": "Cena",
                               "start": {"dateTime": "2026-08-03T20:00:00+00:00"}}],
            "calendar.lavoro": [{"summary": "Riunione",
                                 "start": {"dateTime": "2026-08-03T09:00:00+00:00"}}],
        },
    )

    res = await get_calendar_events(ha, hours=48)

    assert [e["summary"] for e in res["events"]] == ["Riunione", "Cena"]
    assert res["events"][0]["calendar"] == "calendar.lavoro"
    assert "error" not in res
