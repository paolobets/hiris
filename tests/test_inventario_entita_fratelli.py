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
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
from aiohttp import web

from hiris.app.api.handlers_entities import handle_list_entities
from hiris.app.brain.briefing import build_briefing_bundle, render_briefing_template
from hiris.app.proxy.entity_cache import EntityCache
from hiris.app.tools.dispatcher import ToolDispatcher
from hiris.app.tools.ha_tools import get_entity_states


class _HA:
    def __init__(self, stati=None) -> None:
        self._stati = stati or []

    async def get_states(self, ids):
        return self._stati


async def _cache_viva() -> EntityCache:
    cache = EntityCache()
    await cache.load(_HA([{"entity_id": "light.cucina", "state": "on",
                           "attributes": {"friendly_name": "Cucina"}}]))
    return cache


# ── get_entity_states ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_entity_states_con_cache_mai_caricata_non_dice_che_lentita_non_ce():
    cache = EntityCache()
    assert cache.loaded is False

    res = await get_entity_states(_HA(), ["light.cucina"], entity_cache=cache)

    assert isinstance(res, dict) and res.get("error"), (
        "elenco vuoto = «quell'entita' non esiste»: qui non si e' potuto guardare"
    )
    assert "pront" in res["error"].lower()


@pytest.mark.asyncio
async def test_get_entity_states_dal_dispatcher_dichiara_lo_stesso_guasto():
    """Il fratello deve dire la stessa cosa dei tre strumenti gia' corretti."""
    disp = ToolDispatcher(ha_client=MagicMock(), notify_config={},
                          entity_cache=EntityCache())

    res = await disp.dispatch("get_entity_states", {"ids": ["light.cucina"]})

    assert isinstance(res, dict) and "pront" in res.get("error", "").lower()


@pytest.mark.asyncio
async def test_get_entity_states_con_cache_viva_risponde_normalmente():
    cache = await _cache_viva()

    res = await get_entity_states(_HA(), ["light.cucina"], entity_cache=cache)

    assert [e["id"] for e in res] == ["light.cucina"]


@pytest.mark.asyncio
async def test_get_entity_states_senza_cache_legge_ancora_da_home_assistant():
    """Non regressione: senza cache cablata il tool ha sempre letto dal vivo, ed
    e' un percorso legittimo -- non va trasformato in un guasto."""
    ha = _HA([{"entity_id": "light.cucina", "state": "on",
               "attributes": {"friendly_name": "Cucina"}}])

    res = await get_entity_states(ha, ["light.cucina"], entity_cache=None)

    assert [e["id"] for e in res] == ["light.cucina"]


@pytest.mark.asyncio
async def test_get_entity_states_con_cache_viva_e_vuota_resta_un_elenco_vuoto():
    """Il controcanto: una cache caricata che non contiene quell'entita' e' una
    risposta vera, non un guasto."""
    cache = EntityCache()
    await cache.load(_HA([]))

    res = await get_entity_states(_HA(), ["light.cucina"], entity_cache=cache)

    assert res == []


# ── briefing ─────────────────────────────────────────────────────────────────

_OGGI = date(2026, 8, 2)


def _bundle(cache):
    return build_briefing_bundle(None, cache, today=_OGGI, allow_sensitive=True)


@pytest.mark.asyncio
async def test_briefing_con_cache_mai_caricata_non_dichiara_la_casa_chiusa():
    bundle = _bundle(EntityCache())

    assert bundle["home"].get("open_now_unavailable") is True
    testo = render_briefing_template(bundle)
    assert "non ho potuto controllare" in testo.lower()
    assert "nessuna apertura" not in testo.lower(), (
        "il maggiordomo affermerebbe una cosa che non ha verificato"
    )


def test_briefing_senza_cache_non_dichiara_la_casa_chiusa():
    bundle = _bundle(None)

    assert bundle["home"].get("open_now_unavailable") is True
    assert "nessuna apertura" not in render_briefing_template(bundle).lower()


def test_briefing_con_cache_che_solleva_non_dichiara_la_casa_chiusa():
    class _CacheRotta:
        loaded = True

        def all_states(self):
            raise RuntimeError("inventario illeggibile")

    bundle = _bundle(_CacheRotta())

    assert bundle["home"].get("open_now_unavailable") is True


@pytest.mark.asyncio
async def test_briefing_con_cache_viva_e_nessuna_apertura_resta_come_prima():
    """Controcanto: una casa davvero tutta chiusa deve continuare a sentirsi
    dire che non c'e' nulla da segnalare, senza dubbi aggiunti."""
    cache = await _cache_viva()
    bundle = _bundle(cache)

    assert "open_now_unavailable" not in bundle["home"]
    testo = render_briefing_template(bundle)
    assert "non ho potuto controllare" not in testo.lower()
    assert "nessuna apertura" in testo.lower()


@pytest.mark.asyncio
async def test_il_riepilogo_per_il_modello_porta_la_lacuna():
    """Il testo puo' essere composto dal modello: se la lacuna non entra nel
    riepilogo, il modello afferma comunque che e' tutto chiuso."""
    from hiris.app.brain.briefing import build_briefing_message

    messaggio = build_briefing_message(_bundle(EntityCache()))

    assert "open_now_unavailable" in messaggio


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
