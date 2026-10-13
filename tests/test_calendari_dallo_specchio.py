"""I calendari di questa casa dallo specchio (A-34, F1 della Chiusura,
13/10/2026): `House.calendars`.

Fino a quel giorno lo strumento `calendar` chiedeva l'elenco a Home Assistant
(`GET /api/calendars`) mentre lo specchio lo aveva gia'. La rotta, letta nel
sorgente (tag `2026.10.1`, `CalendarListView.get`), rende `{"name":
state.name, "entity_id"}` per ogni entita' del componente e le ordina con
`sorted(..., key=name)`: qui si sorveglia che lo specchio dia lo stesso
insieme, nello stesso ordine, e col nome che HIRIS da' a ogni altra entita'.
"""
from __future__ import annotations

from hiris.app.home_space.house import House
from hiris.app.home_space.topology import live_mirror


def _house(rows, registry=()):
    return House({"entita": list(registry)}, live_mirror(rows))


def test_solo_le_entita_calendario():
    house = _house([{"id": "calendar.famiglia", "state": "off", "name": "Famiglia"},
                    {"id": "sensor.calendario_finto", "state": "1", "name": "Calendario"}])
    assert house.calendars() == [{"id": "calendar.famiglia", "nome": "Famiglia"}]


def test_l_ordine_e_quello_di_home_assistant():
    """`sorted` sul nome, come la rotta: distingue le maiuscole (le maiuscole
    prima), come `sorted` di Python. Mutazione ESEGUITA: `House.calendars`
    senza `sorted` -- rossa (l'ordine dello specchio)."""
    house = _house([{"id": "calendar.zeta", "state": "off", "name": "zeta"},
                    {"id": "calendar.beta", "state": "off", "name": "Beta"},
                    {"id": "calendar.alfa", "state": "off", "name": "alfa"}])
    assert [c["nome"] for c in house.calendars()] == ["Beta", "alfa", "zeta"]


def test_senza_friendly_name_il_nome_del_registro_poi_l_id():
    """Home Assistant ripiega sull'`object_id` con gli spazi; HIRIS fa come
    per ogni altra entita' (`House.name`): il nome del registro, poi l'id."""
    house = _house([{"id": "calendar.lavoro", "state": "off"},
                    {"id": "calendar.casa", "state": "off"}],
                   registry=[{"id": "calendar.lavoro", "nome": "Lavoro"}])
    assert house.calendars() == [{"id": "calendar.lavoro", "nome": "Lavoro"},
                                 {"id": "calendar.casa", "nome": "calendar.casa"}]


def test_nessun_calendario_e_un_elenco_vuoto():
    assert _house([{"id": "light.uno", "state": "on"}]).calendars() == []
