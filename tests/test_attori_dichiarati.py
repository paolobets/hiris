"""Gli attori dichiarati (decisione 13 della spec 2026-10-01; Tappa 7, Task 7).

Fino al 07/10/2026 i turni di sfondo con strumenti -- analista, proponente,
«Rendila automatica» -- costruivano il dispatcher con soffitto `None`, e
`None` non negava niente: vedevano i corpi delle automazioni, il registro di
sistema, e potevano comandare. Adesso il mestiere dichiara il suo soffitto
(`steering.Species.gestures`), il guardiano lo passa al dispatcher, e un
dispatcher senza soffitto non si costruisce.

I mestieri si CHIEDONO a `steering.SPECIES`: un mestiere nuovo con un
guardiano entra in queste prove senza toccarle.
"""
from __future__ import annotations

import pytest

from hiris.app import steering
from hiris.app.api.handlers_chat import create_tool_dispatcher
from hiris.app.api.soffitto import GESTI, declared_ceiling

#: I mestieri con un guardiano, chiesti alla dichiarazione.
_GUARDED = sorted(name for name, s in steering.SPECIES.items() if s.guard is not None)


def test_la_derivazione_dei_mestieri_con_guardiano_non_si_e_rotta():
    """Un insieme vuoto renderebbe verdi le prove qui sotto senza guardare
    niente. Ogni mestiere con strumenti che non e' la chat ne' la promessa
    (il cui soffitto e' quello della persona) ha un guardiano: e' la stessa
    domanda vista dall'altra parte, quindi non ricopia un elenco."""
    with_tools = {name for name, s in steering.SPECIES.items() if not s.self_contained}
    assert _GUARDED
    assert set(_GUARDED) == with_tools - {"chat", steering.PROMISE_SPECIES}


@pytest.mark.asyncio
@pytest.mark.parametrize("name", _GUARDED)
async def test_il_dispatcher_di_ogni_attore_porta_il_soffitto_DICHIARATO(name):
    """Il guardiano del mestiere costruisce il dispatcher col soffitto della
    sua dichiarazione, sulla catena e sul ponte (la stessa funzione).

    Mutazione ESEGUITA (07/10/2026): in `mind/analyst_turn.guard` tolto
    `soffitto=` e tolto il rifiuto di `None` in `create_tool_dispatcher` (cioe'
    il comportamento di prima) -- rossa su `analista` (`None == {...}`).
    Togliendo solo `soffitto=` la prova e' rossa con il `ValueError` del
    costruttore: e' la stessa protezione, vista prima."""
    species = steering.SPECIES[name]
    dispatcher = await species.guard({}, "turno-prova")
    below = dispatcher._below
    assert below._soffitto == species.ceiling(), (name, below._soffitto)


@pytest.mark.parametrize("name", _GUARDED)
def test_un_attore_legge_e_amministra_ma_NON_comanda(name):
    """La decisione 13, scritta: e' un elenco di ammissione -- enuncia cosa
    puo' un attore, non ricopia niente. Al livello di chi amministra perche'
    cio' che gli attori producono lo legge solo chi amministra; comandare no,
    perche' un attore non tocca la casa senza un si'.

    Mutazione ESEGUITA (07/10/2026): `comandare` aggiunto a
    `steering._ACTOR_GESTURES` -- rossa sui tre mestieri."""
    ceiling = steering.SPECIES[name].ceiling()
    assert {g: ceiling[g] for g in GESTI} == {
        "leggere": True, "comandare": False, "amministrare": True}
    assert ceiling["perche"], "un gesto negato porta il suo perche'"


def test_un_dispatcher_SENZA_soffitto_non_si_costruisce():
    """`None` era «tutto»: adesso e' un errore di chi costruisce.

    Mutazione ESEGUITA (07/10/2026): tolto il rifiuto in
    `create_tool_dispatcher` -- rossa (`DID NOT RAISE`)."""
    with pytest.raises(ValueError, match="nessun soffitto"):
        create_tool_dispatcher({})


def test_un_guardiano_senza_gesti_non_si_dichiara():
    """Un mestiere con guardiano e senza gesti costruirebbe un dispatcher
    senza soffitto: la dichiarazione stessa lo rifiuta."""
    async def _guard(app, exchange=None):
        return None

    with pytest.raises(ValueError, match="gesti"):
        steering.Species("prova", "prova", list, steering.PRIORITY_BACKGROUND,
                         guard=_guard)


def test_un_gesto_sconosciuto_non_entra_nel_soffitto():
    with pytest.raises(ValueError, match="gesti sconosciuti"):
        declared_ceiling({"leggere", "costruire"})
