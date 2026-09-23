"""I ripieghi arrivano alla pagina Consumi (reperto C-5c, 23/09/2026).

Scriverli e non mostrarli sarebbe il registro con un altro nome. La pagina dei
soldi e' dove il proprietario va a chiedersi perche' la bolletta e' cresciuta,
e la risposta «ventidue giri dell'analista sono passati a consumo» sta li'.
"""
import json
import pathlib

import pytest

from hiris.app.api.handlers_usage import handle_usage
from hiris.app.usage.store import UsageStore

RADICE = pathlib.Path(__file__).resolve().parents[1]


class _Richiesta:
    def __init__(self, app, query=None):
        self.app = app
        self.query = query or {}


@pytest.fixture()
def app(tmp_path):
    store = UsageStore(str(tmp_path / "consumi.db"))
    store.log("claude", "claude-opus-4-7", token_in=10, token_out=5,
              cost_usd=0.01, cost_state="noto", now=1_758_000_000.0)
    try:
        yield {"usage": store}, store
    finally:
        store.close()


async def _leggi(app):
    risposta = await handle_usage(_Richiesta(app))
    return json.loads(risposta.body.decode("utf-8"))


@pytest.mark.asyncio
async def test_la_rotta_porta_i_ripieghi(app):
    """Mutazione ESEGUITA: togliere la chiave dal payload -- rossa."""
    applicazione, store = app
    store.log_fallback("analista", "tetto giornaliero", now=1_758_000_000.0)

    corpo = await _leggi(applicazione)

    assert corpo["fallbacks"] == [{
        "day": "2025-09-16", "agent": "analista", "reason": "tetto giornaliero",
        "count": 1, "first_ts": 1_758_000_000.0, "last_ts": 1_758_000_000.0}]


@pytest.mark.asyncio
async def test_senza_ripieghi_la_chiave_c_e_ed_e_VUOTA(app):
    """Vuota, non assente: «non e' mai successo» e «non lo so» sono due cose
    diverse, e la pagina deve poter scrivere la prima.

    Mutazione ESEGUITA: omettere la chiave quando non ci sono righe -- rossa."""
    applicazione, _store = app

    corpo = await _leggi(applicazione)

    assert corpo["fallbacks"] == []


# **Che la PAGINA li disegni si prova in `tests/js/usage-route.test.mjs`**, con
# la pagina montata per davvero.
#
# Qui c'era una prova che cercava «fallbacks» e «usage-fallbacks» nel sorgente,
# ed e' nata verde senza saper fallire: togliendo la CHIAMATA alla sezione le
# due parole restavano nel file -- nella definizione della funzione, che
# nessuno chiamava piu'. Guardava il file invece del comportamento.
