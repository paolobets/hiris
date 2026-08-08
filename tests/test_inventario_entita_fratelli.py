"""Fix 2 — lo stesso difetto negli strumenti fratelli che leggono la cache.

Il task precedente ha corretto i tre punti elencati nella specifica
(`get_home_status`, `get_entities_on`, `get_entities_by_domain`), ma il difetto
esiste identico dove nessuno lo cerchera' piu', proprio perche' i vicini sono a
posto:

- `tools/ha_tools.get_entity_states` con cache mai caricata rispondeva un
  elenco vuoto, cioe' «quell'entita' non esiste»;
- `brain/briefing._collect_open_now` con cache assente o mai caricata
  rispondeva «nessuna apertura»;
- `api/handlers_entities.handle_list_entities` rispondeva `{"entities": []}`,
  cioe' «questa casa non ha entita'».

Nella stessa sessione, con la stessa cache, tre strumenti dicevano «non ancora
pronto» e i fratelli «non c'e' niente».

fetta E2 Task 7: un quarto fratello viveva qui -- `get_entity_states` letto
attraverso `ToolDispatcher.dispatch`, per provare che il wrapper non perdesse
la garanzia del tool sottostante. `ToolDispatcher` e' uscito e con lui quel
wrapper; la garanzia che contava (`get_entity_states` dichiara il guasto
invece di rispondere elenco vuoto) e' rimasta provata per una fetta contro
`tools/ha_tools.get_entity_states` direttamente.

fetta E2 Task 8 ("escono i trentaquattro"): `get_entity_states` stessa e'
uscita -- orfana dallo stesso Task 7 (nessun chiamante di produzione la
invocava piu', solo questi test). La sua garanzia non ha piu' un soggetto da
proteggere: la funzione non esiste piu' in nessun percorso, ne' di
produzione ne' di test. I quattro test che la esercitavano sono stati
cancellati, non spostati -- non c'e' piu' nulla a valle da provare.

fetta E3 Task 6: il secondo fratello (`brain/briefing._collect_open_now`, via
`build_briefing_bundle`/`render_briefing_template`/`build_briefing_message`)
e' uscito col Brain che parlava -- resoconto delle 08:00, solleciti, scansione
di salute. L'intera sezione "briefing" qui sotto provava proprio quel
soggetto: cancellata, non spostata, stesso motivo del quarto fratello sopra.
Resta un solo fratello (`handle_list_entities`): vivo, la sua sezione e'
intatta.
"""
from __future__ import annotations

import pytest
from aiohttp import web

from hiris.app.api.handlers_entities import handle_list_entities
from hiris.app.proxy.entity_cache import EntityCache


class _HA:
    def __init__(self, stati=None) -> None:
        self._stati = stati or []

    async def get_states(self, ids):
        return self._stati


# ── /api/entities ────────────────────────────────────────────────────────────

def _app(cache):
    app = web.Application()
    app["entity_cache"] = cache
    app.router.add_get("/api/entities", handle_list_entities)
    return app


@pytest.mark.asyncio
async def test_api_entities_con_cache_mai_caricata_dichiara_il_guasto(aiohttp_client):
    client = await aiohttp_client(_app(EntityCache()))

    r = await client.get("/api/entities")

    assert r.status == 503
    corpo = await r.json()
    assert "pront" in corpo["error"].lower()
    assert "entities" not in corpo, (
        "un elenco vuoto qui e' «questa casa non ha entita'»"
    )


@pytest.mark.asyncio
async def test_api_entities_senza_cache_dichiara_il_guasto(aiohttp_client):
    client = await aiohttp_client(_app(None))

    r = await client.get("/api/entities")

    assert r.status == 503
    assert (await r.json())["error"]


@pytest.mark.asyncio
async def test_api_entities_con_cache_viva_e_vuota_risponde_elenco_vuoto(aiohttp_client):
    """Controcanto: caricata e senza entita' e' una risposta vera, e resta 200."""
    cache = EntityCache()
    await cache.load(_HA([]))
    client = await aiohttp_client(_app(cache))

    r = await client.get("/api/entities")

    assert r.status == 200
    assert (await r.json())["entities"] == []
