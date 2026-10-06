"""L'analista con gli strumenti (D5 del piano degli attori, Task 3.6,
06/10/2026).

Fino a qui l'analista era autosufficiente: la domanda portava tutto, e non
poteva leggere niente. Dal Task 3.6 riceve i lettori (`search`, `related`,
`history`, `mind`) e `compute`, la ricetta al volo; mai uno strumento che
scrive. Il guardiano (`analyst_turn.AnalystDispatcher`) e' lo stesso sulla
catena e sul ponte, e le letture del turno finiscono nell'analisi
(`letture`) dal registro delle chiamate, col nome nudo da tutte e due le
strade.
"""
from __future__ import annotations

import json

import pytest

from hiris.app import server, steering
from hiris.app.home_space import historian
from hiris.app.mind import analyst_turn as at
from hiris.app.mind import compute
from hiris.app.mind.store import ObservationsStore


class _Sotto:
    """Il dispatcher della chat, dal lato del guardiano: dice chi e' passato."""

    def __init__(self):
        self.passati: list[str] = []

    async def dispatch(self, name, arguments):
        self.passati.append(name)
        return {"letto": name}


#: Una casa e un Home Assistant qualunque: il guardiano li passa, non li legge.
_QUALUNQUE = object()


def _guardiano(sotto, *, ha=_QUALUNQUE, house=_QUALUNQUE):
    return at.AnalystDispatcher(sotto, ha=ha, house=house, timezone="Europe/Rome")


@pytest.mark.asyncio
async def test_il_guardiano_RIFIUTA_cio_che_non_e_un_lettore():
    """Con la frase della promessa (`steering.refused_tool`): il turno guarda
    e risponde, non tocca la casa.

    Mutazione ESEGUITA (06/10/2026): il guardiano che lascia passare tutto
    al dispatcher della chat -- rossa (`execute` passa)."""
    sotto = _Sotto()
    for nome in ("execute", "remember", "propose", "fetch"):
        esito = await _guardiano(sotto).dispatch(nome, {})
        assert "non e' disponibile mentre analizzo le misure" in esito["errore"]
    assert sotto.passati == []


@pytest.mark.asyncio
async def test_il_guardiano_lascia_passare_i_lettori():
    sotto = _Sotto()
    for nome in at.READERS:
        assert await _guardiano(sotto).dispatch(nome, {}) == {"letto": nome}
    assert sotto.passati == list(at.READERS)


@pytest.mark.asyncio
async def test_compute_lo_serve_il_guardiano_con_la_casa_del_turno(monkeypatch):
    """`compute` non esiste nella chat: lo serve il guardiano, con la STESSA
    casa dei lettori."""
    chiesti = []

    async def _compute(arguments, *, ha, house, now, timezone):
        chiesti.append((arguments, ha, house, timezone))
        return {"risposta": "ok"}

    monkeypatch.setattr(compute, "compute", _compute)
    ha, house, sotto = object(), object(), _Sotto()
    esito = await _guardiano(sotto, ha=ha, house=house).dispatch(
        compute.COMPUTE_TOOL_NAME, {"passi": []})
    assert esito == {"risposta": "ok"}
    assert chiesti == [({"passi": []}, ha, house, "Europe/Rome")]
    assert sotto.passati == []


@pytest.mark.asyncio
async def test_compute_senza_casa_dice_perche_non_si_calcola():
    esito = await _guardiano(_Sotto(), house=None).dispatch(
        compute.COMPUTE_TOOL_NAME, {"passi": []})
    assert "non posso leggere le serie" in esito["errore"]


# ── la catena ────────────────────────────────────────────────────────────

class _ModelloCheLegge:
    """Il modello dal lato del giro: riceve strumenti e guardiano, e ne
    registra l'uso come fa il runner (`last_tool_calls`)."""

    def __init__(self):
        self.ricevuti: dict = {}
        self.last_tool_calls: list = []

    async def chat(self, **kwargs):
        self.ricevuti = kwargs
        self.last_tool_calls = [{"tool": "history",
                                 "input": {"riferimento": "sensor.prelievo"}}]
        return json.dumps({"osservazioni": []})


def _resoconto(giorno):
    return {"giorno": giorno, "obiettivo": None,
            "misure": [{"soggetto": "dev1", "nome": "Inverter", "misura": "prelievo",
                        "operazione": "somma_periodo", "valore": 1.0,
                        "unita": "kWh", "copertura": 1.0}],
            "forme": [], "cronaca": []}


@pytest.fixture()
def casa(tmp_path):
    store = ObservationsStore(str(tmp_path / "oss.db"))
    for giorno in ("2026-09-15", "2026-09-16", "2026-09-17"):
        store.replace_report(giorno, _resoconto(giorno))
    modello = _ModelloCheLegge()
    app = {"observations": store, "llm_router": modello, "bridge_active": False}
    try:
        yield app, store, modello
    finally:
        store.close()


def _oggi(app):
    return historian.today(
        historian.house_timezone(app.get("home_space_store"))).isoformat()


@pytest.mark.asyncio
async def test_sulla_catena_l_analista_riceve_il_catalogo_e_il_guardiano(casa):
    """Gli strumenti li dice la dichiarazione del mestiere, la stessa che il
    ponte serve da `/api/mcp`.

    Mutazione ESEGUITA (06/10/2026): il giro della catena che non passa gli
    strumenti -- rossa."""
    app, _store, modello = casa
    await server.analyst_round(app)
    nomi = [d["name"] for d in modello.ricevuti["tools"]]
    assert nomi == list(steering.SPECIES[steering.ANALYST_SPECIES].tools_for_turn())
    assert isinstance(modello.ricevuti["dispatcher"], at.AnalystDispatcher)


@pytest.mark.asyncio
async def test_sulla_catena_le_LETTURE_vengono_dal_registro_delle_chiamate(casa):
    """Mutazione ESEGUITA (06/10/2026): il giro che non passa le chiamate del
    turno ad `apply_analysis` -- rossa (nessuna lettura nell'analisi)."""
    app, store, _modello = casa
    await server.analyst_round(app)
    assert store.analysis(_oggi(app))["letture"] == [
        {"tool": "history", "input": {"riferimento": "sensor.prelievo"}}]


# ── il ponte ─────────────────────────────────────────────────────────────

class _CodaRisposta:
    """Un turno del ponte risposto oggi, con le chiamate fatte dalla CLI:
    nomi col prefisso del server, e uno strumento proprio della CLI."""

    def __init__(self, giorno):
        self.turno = {
            "status": "decided", "wake": {"giorno": giorno},
            "decision": {"reply": json.dumps({"osservazioni": []}),
                         "tools_called": [
                             {"tool": "mcp__hiris__history",
                              "input": {"riferimento": "sensor.prelievo"}},
                             {"tool": "ToolSearch", "input": {"query": "x"}}]}}

    def latest(self, kind):
        return self.turno


def test_sul_ponte_le_letture_hanno_il_nome_NUDO(casa):
    """La stessa forma della catena (fondamenta 3): il prefisso e' del
    trasporto.

    Mutazione ESEGUITA (06/10/2026): il raccoglitore che passa i nomi come
    arrivano -- rossa (`mcp__hiris__history`)."""
    app, store, _modello = casa
    app["reasoning_queue"] = _CodaRisposta(_oggi(app))
    raccolto = server._collect_analyst_turn(app, store, _oggi(app))
    assert raccolto["analisi"]["letture"] == [
        {"tool": "history", "input": {"riferimento": "sensor.prelievo"}},
        {"tool": "ToolSearch", "input": {"query": "x"}}]
