"""Fix 1 — l'inventario delle entita' deve ricaricarsi da solo.

Il task precedente ha insegnato agli strumenti a dire «non ancora pronto»
invece di «la casa e' vuota» quando il caricamento iniziale della cache non e'
mai riuscito. Corretto, ma nessuno ri-esegue quel caricamento: `_on_startup`
logga l'errore e prosegue. Con Home Assistant momentaneamente irraggiungibile
all'avvio dell'addon, i tre strumenti che leggono l'inventario rispondevano
«non ancora pronto» PER SEMPRE, fino a un riavvio manuale: piu' onesto di
prima, ma peggiore da usare.

Qui si pinna il ricaricamento periodico: finche' `load()` non e' mai riuscita
si riprova; appena riesce, il lavoro diventa un controllo di una bandiera e
non tocca piu' Home Assistant.
"""
from __future__ import annotations

import inspect
from contextlib import suppress

import pytest

from hiris.app import server
from hiris.app.proxy.entity_cache import EntityCache, unreadable_inventory_error


class _HA:
    """Home Assistant finto che sa essere giu' e poi tornare.

    Conta le chiamate perche' il test piu' importante e' su cio' che NON deve
    succedere: nessuna lettura quando la cache e' gia' viva.
    """

    def __init__(self, *, giu: bool = False) -> None:
        self.giu = giu
        self.chiamate_stati = 0

    async def get_states(self, ids):
        self.chiamate_stati += 1
        if self.giu:
            raise RuntimeError("connessione rifiutata su http://supervisor/core")
        return [{"entity_id": "light.cucina", "state": "on",
                 "attributes": {"friendly_name": "Cucina"}}]


@pytest.mark.asyncio
async def test_ricarica_linventario_dopo_un_avvio_senza_home_assistant():
    """Il caso vero: l'addon parte, HA non risponde, la cache resta non
    caricata. Quando HA torna, il lavoro periodico deve rimetterla in piedi
    senza che l'utente riavvii nulla."""
    cache = EntityCache()
    ha_giu = _HA(giu=True)
    with suppress(RuntimeError):
        await cache.load(ha_giu)
    assert cache.loaded is False

    ha = _HA()
    ricaricato = await server.ricarica_inventario_entita(cache, ha)

    assert ricaricato is True
    assert cache.loaded is True
    assert [e["id"] for e in cache.get_all()] == ["light.cucina"]


async def _get_entities_on_come_lo_strumento(cache):
    """Stessa forma del vecchio ramo `get_entities_on` di `ToolDispatcher.dispatch`
    (uscito -- fetta E2 Task 7): il guasto sull'inventario si controlla PRIMA
    di leggere, esattamente come faceva il dispatcher. `tools.ha_tools.
    get_entities_on` era un pass-through di una riga a `cache.get_on()` --
    uscita anche lei (fetta E2 Task 8, orfana dallo stesso Task 7): si chiama
    `cache.get_on()` direttamente."""
    guasto = unreadable_inventory_error(cache)
    if guasto is not None:
        return guasto
    # `get_on()` e' uscita col censimento del 17/08/2026: si legge lo specchio
    # direttamente. Il soggetto di questa finta non era l'accessore -- e' il
    # controllo del guasto PRIMA della lettura, che resta identico.
    return [e for e in cache.all_states() if e["state"] == "on"]


@pytest.mark.asyncio
async def test_dopo_la_ricarica_gli_strumenti_tornano_a_rispondere():
    """Il sintomo che l'utente vede: prima «non ancora pronto», poi la casa."""
    cache = EntityCache()

    prima = await _get_entities_on_come_lo_strumento(cache)
    assert isinstance(prima, dict) and "pront" in prima.get("error", "").lower()

    await server.ricarica_inventario_entita(cache, _HA())

    dopo = await _get_entities_on_come_lo_strumento(cache)
    assert [e["id"] for e in dopo] == ["light.cucina"]


@pytest.mark.asyncio
async def test_non_ricarica_quando_la_cache_e_gia_viva():
    """Il caricamento serve solo finche' non e' mai riuscito: una cache viva si
    aggiorna gia' dagli eventi di stato, e rileggere tutta la casa a ogni giro
    sarebbe traffico inutile verso Home Assistant."""
    cache = EntityCache()
    ha = _HA()
    await cache.load(ha)
    letture_iniziali = ha.chiamate_stati

    ricaricato = await server.ricarica_inventario_entita(cache, ha)

    assert ricaricato is False
    assert ha.chiamate_stati == letture_iniziali, (
        "cache gia' caricata: nessuna lettura aggiuntiva verso Home Assistant"
    )


@pytest.mark.asyncio
async def test_home_assistant_ancora_giu_non_solleva_e_lascia_riprovare():
    """Il lavoro gira nello scheduler: un guasto deve restare nel log, non
    salire. E la cache deve restare dichiaratamente non pronta, cosi' il giro
    successivo riprova."""
    cache = EntityCache()
    ha_giu = _HA(giu=True)

    ricaricato = await server.ricarica_inventario_entita(cache, ha_giu)

    assert ricaricato is False
    assert cache.loaded is False

    # Il giro dopo, con HA tornato, deve funzionare.
    assert await server.ricarica_inventario_entita(cache, _HA()) is True


@pytest.mark.asyncio
async def test_senza_cache_o_senza_client_non_solleva():
    assert await server.ricarica_inventario_entita(None, _HA()) is False
    assert await server.ricarica_inventario_entita(EntityCache(), None) is False


def test_il_lavoro_periodico_e_registrato_come_gli_altri():
    """Convenzione degli altri lavori periodici (scansione di salute, spazzata
    del ponte, potatura): `engine._scheduler.add_job` con un id `hiris_*` e
    `replace_existing`."""
    sorgente = inspect.getsource(server._on_startup)

    assert "hiris_entity_cache_reload" in sorgente
    assert "ricarica_inventario_entita" in sorgente
    # Cadenza breve: un'indisponibilita' passeggera di Home Assistant deve
    # rientrare in pochi minuti, non alla prossima notte.
    blocco = sorgente[sorgente.index("hiris_entity_cache_reload") - 400:
                      sorgente.index("hiris_entity_cache_reload") + 200]
    assert 'trigger="interval"' in blocco
    assert "minutes=2" in blocco
    assert "replace_existing=True" in blocco
