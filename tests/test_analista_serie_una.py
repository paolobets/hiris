"""La serie dell'analista si compone in un posto solo (D-34).

Sul ponte la domanda parte all'accodamento (`analyst_round`) e la risposta si
applica minuti dopo, alla raccolta (`_collect_analyst_turn`): tutte e due
hanno bisogno della serie e della memoria dell'analista. Fino al 14/10/2026
ognuna le componeva da se', riga per riga; ora le chiedono a
`server._analyst_inputs`. Qui si prova la proprieta': sugli stessi archivi
le due strade vedono la stessa serie e la stessa memoria.

Mutazione ESEGUITA (14/10/2026): la raccolta rimessa a comporre la serie da
se', senza `analyst.with_deviation` -- rossa (la serie della raccolta non ha
lo scarto). Ripristino verificato con `git status`.
"""
from __future__ import annotations

import json

import pytest

from hiris.app import server, steering
from hiris.app.home_space import historian
from hiris.app.mind import analyst_turn
from hiris.app.mind.store import ObservationsStore
from hiris.app.reasoning.queue import ReasoningQueue
from hiris.app.usage.store import UsageStore


def _report(day: str, value: float) -> dict:
    return {"giorno": day, "obiettivo": None,
            "misure": [{"soggetto": "dev1", "nome": "Inverter", "misura": "prelievo",
                        "operazione": "somma_periodo", "valore": value,
                        "unita": "kWh", "copertura": 1.0}],
            "forme": [], "cronaca": []}


class _Queue:
    latest_if_decided = ReasoningQueue.latest_if_decided

    def __init__(self, turn):
        self.turn = turn

    def latest(self, kind, **_filters):
        return self.turn


@pytest.fixture()
def app(tmp_path):
    store = ObservationsStore(str(tmp_path / "oss.db"))
    usage = UsageStore(str(tmp_path / "consumi.db"))
    for day, value in (("2026-09-15", 1.0), ("2026-09-16", 4.0), ("2026-09-17", 2.0)):
        store.replace_report(day, _report(day, value))
    try:
        yield {"observations": store, "usage": usage, "bridge_active": False}
    finally:
        store.close()
        usage.close()


@pytest.mark.asyncio
async def test_accodamento_e_raccolta_vedono_la_stessa_serie(app, monkeypatch):
    today = historian.today(historian.house_timezone(None)).isoformat()
    seen = {}
    real_bridge, real_apply = analyst_turn.bridge_turn, analyst_turn.apply_analysis

    def _bridge(series, previous, **kwargs):
        seen["accodamento"] = (series, previous)
        return real_bridge(series, previous, **kwargs)

    def _apply(series, reply, *, previous, **kwargs):
        seen["raccolta"] = (series, previous)
        return real_apply(series, reply, previous=previous, **kwargs)

    monkeypatch.setattr(analyst_turn, "bridge_turn", _bridge)
    monkeypatch.setattr(analyst_turn, "apply_analysis", _apply)
    monkeypatch.setattr(steering, "who_answers", lambda app: ("ponte", ""))
    monkeypatch.setattr(server, "enqueue_turn", lambda app, species, wake, job: ("j", 5))
    monkeypatch.setattr(server, "turn_in_flight", lambda app, kind: False)
    await server.analyst_round(app)

    app["reasoning_queue"] = _Queue({
        "status": "decided", "wake": {"giorno": today},
        "decision": {"reply": json.dumps({"osservazioni": []}), "tools_called": [],
                     "outcome": "riuscito"}})
    server._collect_analyst_turn(app, app["observations"], today)

    assert seen["accodamento"][0]["serie"], "la derivazione non ha composto nessuna serie"
    assert seen["raccolta"] == seen["accodamento"]
