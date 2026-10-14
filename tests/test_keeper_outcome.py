"""`keeper/outcome.py`: la chiusura di una promessa fuori dall'orologio, nei
suoi due gemelli -- il fallimento (`fail_unfinished`) e il successo
(`keep_concluded`, D-24, Chiusura)."""
from __future__ import annotations

from pathlib import Path

import pytest

from hiris.app.keeper.outcome import ALREADY_CLOSED, CLOSED, UNKNOWN, keep_concluded
from hiris.app.keeper.store import AGENDA_KEY
from hiris.app.keeper.sweeper import SWEEPER_KEY
from hiris.app.provider_occurrences import OCCURRENCES_KEY
from hiris.app.states import KEPT, TAKEN

pytestmark = pytest.mark.asyncio


class _Archivio:
    def __init__(self, stato):
        self.riga = None if stato is None else {"id": "p1", "stato": stato}

    def read(self, ident):
        return self.riga if ident == "p1" else None


class _Orologio:
    def __init__(self):
        self.chiuse = []

    async def concludi_chiedi(self, promise, answer, *, now):
        self.chiuse.append((promise["id"], answer, now))


class _Registro:
    def __init__(self):
        self.successi = []

    def successo(self, provider):
        self.successi.append(provider)


def _app(stato, *, orologio=True):
    return {AGENDA_KEY: _Archivio(stato), OCCURRENCES_KEY: _Registro(),
            **({SWEEPER_KEY: _Orologio()} if orologio else {})}


async def test_una_promessa_presa_si_conclude_dall_orologio_e_si_conta():
    """D-24: fino al 13/10/2026 la rotta MCP rifaceva a mano rileggi, `stato
    != TAKEN`, chiudi e conta. Ora il giro e' uno, accanto al suo gemello di
    fallimento. Mutazione ESEGUITA (13/10/2026): tolta la riga che conta il
    successo -- rossa qui e in `test_mcp_exchange_promise`."""
    app = _app(TAKEN)
    assert await keep_concluded(app, "p1", {"testo": "fatto"}, now=5.0) == CLOSED
    assert app[SWEEPER_KEY].chiuse == [("p1", {"testo": "fatto"}, 5.0)]
    assert app[OCCURRENCES_KEY].successi == ["subscription"]


async def test_una_promessa_gia_conclusa_non_si_riconsegna_ne_si_conta():
    """Fra il primo controllo e adesso puo' essere arrivata la scadenza o un
    `conclude` gemello: niente seconda riga, niente seconda push, niente
    successo contato. Mutazione ESEGUITA (13/10/2026): tolto il controllo
    `stato != TAKEN` -- rossa qui (prima di questa prova nessuna lo vedeva)."""
    app = _app(KEPT)
    assert await keep_concluded(app, "p1", {"testo": "x"}, now=5.0) == ALREADY_CLOSED
    assert app[SWEEPER_KEY].chiuse == []
    assert app[OCCURRENCES_KEY].successi == []


@pytest.mark.parametrize("app", [_app(None), _app(TAKEN, orologio=False)],
                         ids=["promessa-assente", "orologio-assente"])
async def test_senza_promessa_o_senza_orologio_non_si_chiude_niente(app):
    assert await keep_concluded(app, "p1", {"testo": "x"}, now=5.0) == UNKNOWN
    assert app[OCCURRENCES_KEY].successi == []


def test_l_archivio_delle_promesse_non_si_porta_dietro_il_loop_del_modello():
    """N152-2 (giro 152): `keeper/promise.py` importava `steering` per una
    stringa sola, e con lui `claude_runner` e la coda del ponte. La frase sta
    in una foglia (`answer_reasons.py`). La prova importa `promise` in un
    interprete pulito e guarda cosa si e' portato dietro. Mutazione ESEGUITA
    (13/10/2026): l'import rimesso da `steering` -- rossa."""
    import subprocess
    import sys

    codice = ("import sys, hiris.app.keeper.promise; "
              "print(sorted(m for m in sys.modules if m in "
              "('hiris.app.steering', 'hiris.app.claude_runner', "
              "'hiris.app.reasoning.queue')))")
    fatto = subprocess.run([sys.executable, "-c", codice], capture_output=True,
                           text=True, check=True)
    assert fatto.stdout.strip() == "[]"


def test_la_frase_del_modello_che_non_risponde_ha_una_casa_sola():
    """N152-2: `steering` la legge dalla foglia invece di ridefinirla.
    Mutazione ESEGUITA (13/10/2026): la riga rimessa in `steering` -- rossa."""
    from hiris.app import answer_reasons, steering

    assert steering.NO_ANSWER_REASON is answer_reasons.NO_ANSWER_REASON
    assert "NO_ANSWER_REASON = " not in Path(steering.__file__).read_text(encoding="utf-8")
