"""Sul ponte, un dispatcher per turno (Tappa 6, Task 8; D-63).

Fino al 06/10/2026 la rotta `POST /api/mcp` costruiva un `ToolDispatcher`
nuovo a OGNI `tools/call`: un turno del ponte con tre chiamate di strumenti
leggeva la casa tre volte (anagrafe, specchio, gerarchia), mentre la catena
la legge una volta per turno (`House`, Tappa 3). Misurato su `8529b30` con la
prova qui sotto: tre chiamate, tre dispatcher, tre case.

Il turno si riconosce dall'intestazione che il ponte gia' porta,
`X-HIRIS-Turno` (`agent/runner.py::config_mcp`): la stessa che conta i giri.
"""
from __future__ import annotations

import json

import pytest

from hiris.app.api import handlers_mcp
from hiris.app.home_space import house as house_module
from tests.test_mcp_route import INTESTAZIONI_CLI, _chiama_cerca, rotta  # noqa: F401


@pytest.fixture
def conti(monkeypatch):
    """Quante case e quanti dispatcher nascono: si contano alla fonte, la
    lettura della casa e l'unico costruttore del dispatcher."""
    contati = {"case": 0, "dispatcher": 0}
    leggi = house_module.House.read.__func__
    costruisci = handlers_mcp.create_tool_dispatcher

    def _leggi(cls, *a, **k):
        contati["case"] += 1
        return leggi(cls, *a, **k)

    def _costruisci(*a, **k):
        contati["dispatcher"] += 1
        return costruisci(*a, **k)

    monkeypatch.setattr(house_module.House, "read", classmethod(_leggi))
    monkeypatch.setattr(handlers_mcp, "create_tool_dispatcher", _costruisci)
    return contati


async def _tre_ricerche(client, intestazioni):
    for i in range(3):
        corpo = await (await _chiama_cerca(client, i, intestazioni)).json()
        assert "isError" not in corpo["result"], corpo
        assert json.loads(corpo["result"]["content"][0]["text"])["trovate"]


@pytest.mark.asyncio
async def test_un_turno_con_tre_chiamate_legge_UNA_casa(rotta, conti):
    """Rossa su `8529b30`: «3 case, 3 dispatcher».

    Mutazione ESEGUITA il 06/10/2026: il dispatcher ricostruito a ogni
    chiamata (la riga che lo ricorda nel turno tolta) -- rossa con 3 case."""
    client, _ = rotta
    await _tre_ricerche(client, {**INTESTAZIONI_CLI, "X-HIRIS-Turno": "turno-uno"})
    assert (conti["case"], conti["dispatcher"]) == (1, 1), (
        f"{conti['case']} case, {conti['dispatcher']} dispatcher per un turno solo")


@pytest.mark.asyncio
async def test_due_turni_non_si_prestano_il_dispatcher(rotta, conti):
    """Il dispatcher porta l'identita' del turno (la guardia dell'officina
    rifiuta una `confirm` nello stesso turno della `propose`): due turni,
    due dispatcher."""
    client, _ = rotta
    await _tre_ricerche(client, {**INTESTAZIONI_CLI, "X-HIRIS-Turno": "turno-a"})
    await _tre_ricerche(client, {**INTESTAZIONI_CLI, "X-HIRIS-Turno": "turno-b"})
    assert conti["dispatcher"] == 2


@pytest.mark.asyncio
async def test_senza_turno_si_costruisce_a_ogni_chiamata(rotta, conti):
    """Un chiamante che non porta `X-HIRIS-Turno` non ha un turno a cui
    legare il dispatcher: si comporta come prima, e il log lo dice gia'
    (`test_mcp_route.py`)."""
    client, _ = rotta
    await _tre_ricerche(client, INTESTAZIONI_CLI)
    assert conti["dispatcher"] == 3


@pytest.mark.asyncio
async def test_il_dispatcher_esce_quando_il_turno_scade(rotta, conti):
    """Un turno piu' vecchio della scadenza del ponte (`bridge_deadline_min`,
    la scadenza della Tappa 6, Task 2) non ha piu' chi aspetti la sua
    risposta: il suo dispatcher, e la casa che tiene, si lasciano andare.
    Il contatore dei giri invece resta: se ripartisse, il tetto si
    aggirerebbe durando (`test_mcp_route.py::test_un_turno_attivo_non_viene_
    mai_espulso`).

    Mutazione ESEGUITA il 06/10/2026: tolto il rilascio per eta' -- rossa,
    il dispatcher del turno vecchio resta."""
    client, _ = rotta
    intestazioni = {**INTESTAZIONI_CLI, "X-HIRIS-Turno": "turno-vecchio"}
    await _chiama_cerca(client, 1, intestazioni)
    turno = client.app[handlers_mcp.ROUNDS_PER_EXCHANGE_KEY]["turno-vecchio"]
    assert turno.dispatcher is not None
    minuti = handlers_mcp.bridge_deadline_min(client.app.get("models_config"))
    turno.since -= minuti * 60 + 1

    # Un altro turno chiama: il vecchio viene lasciato andare.
    await _chiama_cerca(client, 2, {**INTESTAZIONI_CLI, "X-HIRIS-Turno": "turno-nuovo"})
    assert turno.dispatcher is None
    assert turno.rounds == 1
