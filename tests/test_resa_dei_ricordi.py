"""La resa di un ricordo: una funzione sola, la stessa forma da ogni porta
(Tappa 9, fetta F3, 08/10/2026; C-41, D6).

Un ricordo esce da tre vie: il dettaglio di `search` (`queries.
_view_memory`), i `ricordi` ancorati nelle schede e la pagina Memoria
(`GET /api/memories`); fino al 12/10/2026 (Tappa 9, F6) anche da `fetch`.
Fino all'08/10/2026 ognuna lo componeva da se':
`corretto_da_utente` usciva dalla pagina come booleano, da `fetch` e dalle
schede come l'intero della colonna, e dal dettaglio per niente (C-41).

Mutazioni ESEGUITE:
- `_view_memory` che torna a comporre il ricordo a mano (senza
  `corretto_da_utente`) -- rosse `test_il_dettaglio_dice_se_lo_hai_corretto`
  (`KeyError: 'corretto_da_utente'`) e la prova delle porte;
- la pagina che torna a mandare la riga dell'archivio con le ancore risolte
  (senza `render_memory`) -- rossa la prova delle porte, sulla chiave
  `genere` della pagina;
- un chiamante nuovo di `render_memory` in `home_space/briefing.py` -- rossa
  `test_ogni_porta_della_resa_e_guardata`, che lo nomina.
"""
from __future__ import annotations

import re
import sys
from datetime import UTC
from pathlib import Path

import pytest
from aiohttp.test_utils import make_mocked_request

from hiris.app.api.handlers_chat import create_tool_dispatcher
from hiris.app.api.soffitto import consente
from hiris.app.home_space.historian import home_space_zone, house_timezone
from hiris.app.home_space.house import House
from hiris.app.home_space.queries import view
from hiris.app.home_space.reader import HOME_SPACE_KEY
from hiris.app.home_space.render import render_memory
from hiris.app.home_space.topology import Mirror
from hiris.app.memory.store import MEMORY_STORE_KEY
from hiris.app.proxy.entity_cache import ENTITY_CACHE_KEY
from tests._casa_sintetica import synthetic_inputs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fotografia_porte

_APP = Path(__file__).resolve().parents[1] / "hiris" / "app"

#: Le porte che questa prova guarda, per modulo che chiama la resa. E' una
#: lista di AMMISSIONE: un chiamante nuovo di `render_memory` e' rosso finche'
#: qui non si scrive da quale porta la sua forma si confronta con le altre.
_DOORS = {
    "home_space/queries.py": "search (dettaglio e schede)",
    "home_space/house_query.py": "search (le righe: per nome e per genere, D-45)",
    "api/handlers_memory.py": "GET /api/memories",
}


def test_ogni_porta_della_resa_e_guardata():
    """I chiamanti di `render_memory` si chiedono al sorgente: ognuno ha la sua
    porta in `_DOORS`, e nessuna porta di `_DOORS` e' senza chiamante."""
    callers = {str(path.relative_to(_APP)) for path in _APP.rglob("*.py")
               if path.name != "render.py"
               and re.search(r"\brender_memory\(", path.read_text(encoding="utf-8"))}
    assert callers == set(_DOORS)


def test_il_dettaglio_dice_se_lo_hai_corretto():
    """C-41: `corretto_da_utente` esce anche dal dettaglio di un ricordo, come
    booleano -- prima usciva solo dalla pagina."""
    ricordi = [{"id": 3, "testo": "fra 19 e 20", "corretto_da_utente": 1,
                "ancore": [], "condizioni": []}]
    dettaglio = view(House({}, Mirror()), [], ricordi, "ricordo", 3)
    assert dettaglio["corretto_da_utente"] is True
    assert dettaglio["genere"] == "ricordo"


def test_una_chiave_assente_resta_assente():
    """«Non lo so» non diventa «so che non c'e'»: una riga senza la colonna non
    esce con `null` (vocabolario dei campi, regola 1)."""
    resa = render_memory({"id": 1, "testo": "x", "forza": None}, House({}, Mirror()),
                         zone=UTC)
    assert resa == {"genere": "ricordo", "id": 1, "testo": "x", "forza": None}


@pytest.mark.asyncio
async def test_lo_stesso_ricordo_ha_la_stessa_forma_da_ogni_porta(tmp_path):
    """Un ricordo corretto dal proprietario, ancorato a un'area: dalla pagina,
    dal dettaglio di `search` e dalla scheda dell'area in `search` esce lo
    STESSO dizionario, ed e' quello di `render_memory`."""
    async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path)) as app:
        memory = app[MEMORY_STORE_KEY]
        area = app[HOME_SPACE_KEY].read()["aree"][0]["id"]
        ident = memory.remember("d'inverno qui la voglio fra 19 e 20", detto_da="paolo",
                                ancore=[{"tipo": "area", "riferimento": area,
                                         "nome_visto": "qui"}])
        memory.correggi(ident, forza="preferenza")

        page = await _route(app, "/api/memories")
        from_page = next(m for m in page["memories"] if m["id"] == ident)

        dispatcher = create_tool_dispatcher(app, soffitto=consente(None, ruolo="amministratore"))
        detail = (await dispatcher.dispatch("search", {
            "genere": "ricordo", "riferimento": str(ident)}))["voci"][0]
        assert detail.pop("esiste") is True
        card = (await dispatcher.dispatch("search", {
            "genere": "area", "riferimento": area}))["voci"][0]
        from_card = next(m for m in card["ricordi"] if m["id"] == ident)
        # Un secondo ricordo, perche' l'elenco resti un elenco di righe e non
        # si apra nel dettaglio (D-45, 12/10/2026).
        memory.remember("un altro ricordo")
        rows = (await dispatcher.dispatch("search", {"genere": "ricordo"}))["voci"]
        from_row = next(m for m in rows if m["id"] == ident)

        house = House.read(app[HOME_SPACE_KEY], app[ENTITY_CACHE_KEY])
        zone = home_space_zone(house_timezone(app[HOME_SPACE_KEY]))
        expected = render_memory(memory.get(ident), house, zone=zone)
        assert expected["corretto_da_utente"] is True
        # L'istante nell'ora della casa da ogni porta, pagina compresa
        # (11/10/2026: la pagina riceveva l'epoca, il modello l'ISO).
        assert isinstance(expected["detto_il"], str)
        assert expected["ancore"][0]["esiste"] is True
        assert {"pagina": from_page, "dettaglio": detail, "scheda": from_card,
                "riga": from_row} == {
            "pagina": expected, "dettaglio": expected, "scheda": expected, "riga": expected}


def test_la_scheda_di_un_automazione_porta_i_ricordi_ancorati_a_lei():
    """M-32: la scheda di un comportamento cercava i ricordi con l'ancora
    `("automazione", id)`, un tipo che il vocabolario delle ancore non ha
    (`resolver.STORE_KEY_PER_TYPE`: area, entita, dispositivo): la chiave
    `ricordi` era sempre vuota. Un'automazione e' un'entita' del registro di
    Home Assistant (`automation.x`), e `remember` la ancora come `entita`:
    la scheda chiede quella coppia.

    Mutazione ESEGUITA: `_view_behavior` che torna a cercare il tipo del
    comportamento -- rossa con `assert [] == [4]`."""
    behavior = [{"id": "automation.sveglia", "tipo": "automazione", "nome": "Sveglia",
                 "corpo": None}]
    ricordi = [{"id": 4, "testo": "la sveglia non suona nel weekend",
                "ancore": [{"tipo": "entita", "riferimento": "automation.sveglia"}],
                "condizioni": []}]
    scheda = view(House({}, Mirror()), behavior, ricordi, "automazione", "automation.sveglia")
    assert [m["id"] for m in scheda["ricordi"]] == [4]


async def _route(app, path: str) -> dict:
    """La risposta di una rotta GET del prodotto, chiesta al suo router."""
    import json
    handler = next(route.handler for route in app.router.routes()
                   if route.method == "GET" and route.resource is not None
                   and route.resource.canonical == path)
    response = await handler(make_mocked_request("GET", path, app=app))
    return json.loads(response.body)
