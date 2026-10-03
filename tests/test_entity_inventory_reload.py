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

Home Assistant e' `scripts/casa_finta.py::CasaFinta` sugli ingressi sintetici
(Tappa 2, Task 12). Fino ad allora era una classe che imitava `get_states` e,
«giu'», SOLLEVAVA `RuntimeError`: il client vero non solleva (D3), rende la
busta del guasto, ed e' `EntityCache.load` a trasformarla in `HAReadError`.
Ora «giu'» e' il silenzio vero su `GET /api/states`.
"""
from __future__ import annotations

import sys
from contextlib import suppress
from pathlib import Path

import pytest

from hiris.app import server
from hiris.app.proxy.entity_cache import EntityCache, unreadable_inventory_error
from hiris.app.proxy.ha_client import HAReadError
from tests._casa_sintetica import synthetic_inputs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from casa_finta import CasaFinta

_STATES = "/api/states"


def _house(*, down: bool = False) -> CasaFinta:
    """La casa sintetica; `down` = Home Assistant che non risponde agli stati."""
    return CasaFinta(synthetic_inputs(), silence={_STATES} if down else ())


def _state_reads(house: CasaFinta) -> int:
    """Le letture degli stati che il codice ha chiesto alla casa: il test piu'
    importante e' su cio' che NON deve succedere."""
    return sum(1 for path, _ in house.calls if path == _STATES)


def _ids(states) -> list[str]:
    return sorted(s["entity_id"] for s in states)


@pytest.mark.asyncio
async def test_ricarica_linventario_dopo_un_avvio_senza_home_assistant():
    """Il caso vero: l'addon parte, HA non risponde, la cache resta non
    caricata. Quando HA torna, il lavoro periodico deve rimetterla in piedi
    senza che l'utente riavvii nulla."""
    cache = EntityCache()
    with suppress(HAReadError):
        await cache.load(_house(down=True))
    assert cache.loaded is False

    ricaricato = await server.reload_entity_inventory(cache, _house())

    assert ricaricato is True
    assert cache.loaded is True
    assert sorted(e["id"] for e in cache.all_states()) == \
        _ids(synthetic_inputs()["states"])


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

    await server.reload_entity_inventory(cache, _house())

    dopo = await _get_entities_on_come_lo_strumento(cache)
    accese = [s for s in synthetic_inputs()["states"] if s["state"] == "on"]
    assert accese, "gli ingressi sintetici devono avere qualcosa di acceso"
    assert sorted(e["id"] for e in dopo) == _ids(accese)


@pytest.mark.asyncio
async def test_non_ricarica_quando_la_cache_e_gia_viva():
    """Il caricamento serve solo finche' non e' mai riuscito: una cache viva si
    aggiorna gia' dagli eventi di stato, e rileggere tutta la casa a ogni giro
    sarebbe traffico inutile verso Home Assistant."""
    cache = EntityCache()
    house = _house()
    await cache.load(house)
    letture_iniziali = _state_reads(house)
    assert letture_iniziali == 1

    ricaricato = await server.reload_entity_inventory(cache, house)

    assert ricaricato is False
    assert _state_reads(house) == letture_iniziali, (
        "cache gia' caricata: nessuna lettura aggiuntiva verso Home Assistant"
    )


@pytest.mark.asyncio
async def test_home_assistant_ancora_giu_non_solleva_e_lascia_riprovare():
    """Il lavoro gira nello scheduler: un guasto deve restare nel log, non
    salire. E la cache deve restare dichiaratamente non pronta, cosi' il giro
    successivo riprova."""
    cache = EntityCache()
    house_down = _house(down=True)

    ricaricato = await server.reload_entity_inventory(cache, house_down)

    assert ricaricato is False
    assert cache.loaded is False
    # Ci ha provato davvero: non e' tornato `False` prima di chiedere.
    assert _state_reads(house_down) == 1

    # Il giro dopo, con HA tornato, deve funzionare.
    assert await server.reload_entity_inventory(cache, _house()) is True


@pytest.mark.asyncio
async def test_senza_cache_o_senza_client_non_solleva():
    assert await server.reload_entity_inventory(None, _house()) is False
    assert await server.reload_entity_inventory(EntityCache(), None) is False
