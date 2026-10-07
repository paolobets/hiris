"""L'analista rifiutato: l'esito nel registro dei turni, e i problemi nella
domanda del giro dopo (D10 del piano degli attori, Task 3.6 Passo 3; scelte
del proprietario del 06/10/2026: «Si', con la colonna»).

Sulla catena e sul ponte la stessa riga: il giro scrive «rifiutata» e i
problemi sul turno che li ha prodotti (`steering.declare_refused`), e il giro
che riprova li rilegge da li' (`steering.refused_problems`). Fino a qui sulla
catena un rifiuto non restava da nessuna parte, e il modello riprovava senza
sapere perche'.
"""
from __future__ import annotations

import json

import pytest

from hiris.app import server, steering
from hiris.app.home_space import historian
from hiris.app.mind import analyst_turn as at
from hiris.app.mind.store import ObservationsStore
from hiris.app.usage.store import UsageStore

_RIFIUTATA = json.dumps({"osservazioni": [], "rimetti": [{"id": "sensor.x"}]})
_PROBLEMA = "il rimetti 1 vuole `id` e `perche`"


class _Modello:
    """Il modello dal lato del giro: risponde quello che gli si da', e tiene
    le domande."""

    def __init__(self, *risposte):
        self.risposte = list(risposte)
        self.domande: list[str] = []
        self.last_tool_calls: list = []

    async def chat(self, **kwargs):
        self.domande.append(kwargs["user_message"])
        return self.risposte.pop(0)


def _resoconto(giorno):
    return {"giorno": giorno, "obiettivo": None,
            "misure": [{"soggetto": "dev1", "nome": "Inverter", "misura": "prelievo",
                        "operazione": "somma_periodo", "valore": 1.0,
                        "unita": "kWh", "copertura": 1.0}],
            "forme": [], "cronaca": []}


@pytest.fixture()
def casa(tmp_path):
    store = ObservationsStore(str(tmp_path / "oss.db"))
    usage = UsageStore(str(tmp_path / "consumi.db"))
    for giorno in ("2026-09-15", "2026-09-16", "2026-09-17"):
        store.replace_report(giorno, _resoconto(giorno))
    app = {"observations": store, "usage": usage, "bridge_active": False}
    try:
        yield app
    finally:
        store.close()
        usage.close()


def _oggi(app):
    return historian.today(
        historian.house_timezone(app.get("home_space_store"))).isoformat()


@pytest.mark.asyncio
async def test_sulla_CATENA_il_rifiuto_si_scrive_e_torna_nella_domanda(casa):
    """Mutazioni ESEGUITE (06/10/2026): il giro della catena senza
    `declare_refused` -- rossa (l'esito resta «riuscito»); senza
    `refused_problems` -- rossa (la seconda domanda non porta il problema)."""
    app = casa
    modello = _Modello(_RIFIUTATA, json.dumps({"osservazioni": []}))
    app["llm_router"] = modello

    await server.analyst_round(app)
    riga = app["usage"].turns(species=steering.ANALYST_SPECIES)[0]
    assert riga["outcome"] == steering.REFUSED
    assert any(_PROBLEMA in p for p in riga["problems"])
    assert _PROBLEMA not in modello.domande[0]

    await server.analyst_round(app)
    assert _PROBLEMA in modello.domande[1]
    assert app["observations"].analysis(_oggi(app)) is not None


@pytest.mark.asyncio
async def test_una_risposta_buona_NON_si_segna_rifiutata(casa):
    app = casa
    app["llm_router"] = _Modello(json.dumps({"osservazioni": []}))
    await server.analyst_round(app)
    assert app["usage"].turns()[0]["outcome"] == "riuscito"


class _Coda:
    def __init__(self, turno):
        self.turno = turno

    def latest(self, kind):
        return self.turno


def test_sul_PONTE_il_raccoglitore_scrive_il_rifiuto_sulla_riga_del_turno(casa):
    """Il runner mette l'id della riga nella decisione (`turn_id`).

    Mutazione ESEGUITA (06/10/2026): il raccoglitore senza `declare_refused`
    -- rossa."""
    app = casa
    ident = app["usage"].log_turn(
        species=steering.ANALYST_SPECIES, provider="subscription", model="m",
        channel="ponte", duration_ms=1, iterations=1, tools=[],
        outcome="riuscito", now=1_758_000_000.0)
    app["reasoning_queue"] = _Coda({
        "status": "decided", "wake": {"giorno": _oggi(app)},
        "decision": {"reply": _RIFIUTATA, "tools_called": [],
                     "outcome": "riuscito", "turn_id": ident}})
    server._collect_analyst_turn(app, app["observations"], _oggi(app))
    riga = app["usage"].turns()[0]
    assert riga["outcome"] == steering.REFUSED
    assert any(_PROBLEMA in p for p in riga["problems"])


@pytest.mark.asyncio
async def test_sul_PONTE_la_domanda_accodata_porta_i_problemi(casa, monkeypatch):
    """La stessa lettura della catena: `refused_problems` sul registro.

    Mutazione ESEGUITA (06/10/2026): il giro senza `refused_problems` --
    rossa (la domanda accodata non porta il problema)."""
    app = casa
    ident = app["usage"].log_turn(
        species=steering.ANALYST_SPECIES, provider="subscription", model="m",
        channel="ponte", duration_ms=1, iterations=1, tools=[],
        outcome="riuscito", now=1_758_000_000.0)
    steering.declare_refused(app["usage"], ident, [_PROBLEMA])
    accodati = []
    monkeypatch.setattr(steering, "who_answers", lambda app: ("ponte", ""))
    monkeypatch.setattr(server, "enqueue_turn",
                        lambda app, specie, wake, job: accodati.append(job) or ("j", 5))
    monkeypatch.setattr(server, "turn_in_flight", lambda app, kind: False)
    await server.analyst_round(app)
    assert _PROBLEMA in accodati[0]["history"][0]["content"]


def test_la_domanda_porta_i_problemi_solo_se_ci_sono():
    serie = {"giorni": ["2026-09-17"], "obiettivi": [],
             "serie": [{"soggetto": "dev1", "nome": "Inverter", "misura": "prelievo",
                        "unita": "kWh", "valori": [1.0], "coperture": [1.0]}]}
    senza = at.build_question(serie)
    con = at.build_question(serie, refused=[_PROBLEMA])
    assert "non e' stata accettata" not in senza
    assert _PROBLEMA in con
