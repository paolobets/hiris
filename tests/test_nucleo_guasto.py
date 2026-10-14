"""Il nucleo che non si compone si dichiara in UN posto (D-64; Chiusura, 13/10/2026).

Fino a quel giorno `compose_briefing` aveva tre chiamanti e tre comportamenti
sul guasto: la chat lo dichiarava con un testo suo, le due strade della
promessa (`keeper/exchange.py`) ripiegavano su "" in silenzio, e
`GET /api/briefing` rispondeva 500. Il nucleo guasto e' un fatto sulla casa
come gli altri: lo dice il compositore, e ogni porta riceve la stessa frase.
"""
import pytest

from hiris.app.api.handlers_home_space import BRIEFING_FAILED, compose_briefing
from tests._runner_finto import RunnerFinto


class _MemoriaGuasta:
    """Un `memoria.db` in lock: ogni lettura solleva, come in produzione."""

    def count(self):
        raise RuntimeError("database is locked")

    def fetch(self, **_):
        raise RuntimeError("database is locked")


def _app_guasta() -> dict:
    return {"memory_store": _MemoriaGuasta()}


def test_il_compositore_dichiara_il_guasto_invece_di_sollevare():
    """Mutazione ESEGUITA il 13/10/2026: `compose_briefing` senza la sua rete
    -- rossa qui (RuntimeError) e sulla rotta."""
    testo, riepilogo = compose_briefing(_app_guasta())
    assert testo == BRIEFING_FAILED
    assert "un guasto" in testo
    # Il riepilogo non mente su cio' che il testo non contiene: niente
    # ricordi esclusi da contare (non si sa), il guasto fra le lacune.
    assert riepilogo["chars"] == len(testo)
    assert riepilogo["excluded_memories"] is None
    assert riepilogo["notices"] and riepilogo["truncated"] is False


@pytest.mark.asyncio
async def test_la_rotta_del_nucleo_mostra_il_guasto_invece_di_un_500(aiohttp_client):
    from aiohttp import web

    from hiris.app.api.handlers_home_space import handle_get_briefing

    app = web.Application()
    app["memory_store"] = _MemoriaGuasta()
    app.router.add_get("/api/briefing", handle_get_briefing)
    client = await aiohttp_client(app)

    resp = await client.get("/api/briefing")
    assert resp.status == 200
    corpo = await resp.json()
    assert corpo["text"] == BRIEFING_FAILED


@pytest.mark.asyncio
async def test_la_promessa_sulla_catena_riceve_la_stessa_frase():
    """Prima: `briefing = ""`, e il turno della promessa leggeva una casa
    vuota invece di un guasto."""
    from hiris.app.keeper.exchange import interpreta_promise

    async def _conclude(_runner, **kwargs):
        await kwargs["dispatcher"].dispatch(
            "conclude", {"avvisare": False, "testo": "niente"})

    modello = RunnerFinto(turno=_conclude)
    app = {"llm_router": modello, **_app_guasta()}
    await interpreta_promise(app, {"id": "p1", "frase": "dimmi", "domanda": "guarda",
                                   "istantanea": []})
    assert modello.ultima["context_str"] == BRIEFING_FAILED


def test_la_promessa_sul_ponte_riceve_la_stessa_frase(monkeypatch):
    from hiris.app.keeper import exchange

    accodati = []
    monkeypatch.setattr(exchange, "enqueue_turn",
                        lambda app, species, cols, context, **kw:
                        accodati.append(context) or ("j1", 5))
    exchange._enqueue_to_bridge(_app_guasta(), {"id": "p1", "frase": "dimmi",
                                                "domanda": "guarda"})
    assert accodati[0]["contesto"] == BRIEFING_FAILED
