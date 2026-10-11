"""Le ancore dei ricordi dicono se il loro riferimento c'e' ancora, da TUTTE
le porte (G-21, Tappa 8, Task 1, 08/10/2026).

Fino a quel giorno la pagina Memoria riceveva per ogni ancora `nome_attuale`
ed `esiste` (`handlers_memory._resolve_tether`), e il modello l'ancora grezza
-- da `view` (dettaglio di un ricordo, ricordi ancorati) e da `fetch` -- e non
poteva dire «quell'entita' non c'e' piu'». La regola vive in `House.tether`; i
ricordi non si cancellano.

Mutazione ESEGUITA: `sanitized_memories` che ignora la casa (nessuna
risoluzione) -- rosse le prove di `view` e di `fetch`; `House.tether` che
risponde `esiste: False` anche col registro caduto -- rossa la prova del
registro caduto.
"""
import pytest

from hiris.app.home_space.house import House
from hiris.app.home_space.queries import view
from hiris.app.home_space.reader import HomeSpace
from hiris.app.home_space.tools import ToolDispatcher
from hiris.app.home_space.topology import Mirror
from hiris.app.memory.store import MemoryStore

_REGISTRI = {
    "piani": [], "aree": [{"area_id": "cucina", "name": "Cucina"}],
    "dispositivi": [], "etichette": [], "categorie": [], "integrazioni": [],
    "entita": [{"entity_id": "light.cucina", "name": "Luce cucina",
                "area_id": "cucina"}],
}

_VIVA = {"tipo": "entita", "riferimento": "light.cucina", "nome_visto": "luce"}
_SPARITA = {"tipo": "entita", "riferimento": "light.vecchia", "nome_visto": "vecchia"}


@pytest.fixture
def anagrafe(tmp_path):
    casa = HomeSpace(str(tmp_path))
    casa.hold_registries(dict(_REGISTRI))
    yield casa
    casa.close()


@pytest.fixture
def memoria(tmp_path):
    m = MemoryStore(str(tmp_path / "memoria.db"))
    yield m
    m.close()


def test_l_ancora_dice_se_c_e_ancora(anagrafe):
    casa = House.read(anagrafe, None)
    assert casa.tether(_VIVA) == {**_VIVA, "nome_attuale": "Luce cucina", "esiste": True}
    assert casa.tether(_SPARITA) == {**_SPARITA, "nome_attuale": None, "esiste": False}


def test_un_anagrafe_mai_letta_non_afferma_un_assenza(tmp_path):
    casa = House.read(HomeSpace(str(tmp_path)), None)
    assert casa.tether(_SPARITA)["esiste"] is None
    assert casa.unverifiable_tether_kinds() == {"area", "entita", "dispositivo"}


def test_il_registro_caduto_lascia_esiste_a_None_solo_per_il_suo_tipo(anagrafe):
    anagrafe.hold_registries(dict(_REGISTRI), unavailable=["entita"])
    casa = House.read(anagrafe, None)
    assert casa.tether(_SPARITA)["esiste"] is None
    area = {"tipo": "area", "riferimento": "soffitta", "nome_visto": "soffitta"}
    assert casa.tether(area)["esiste"] is False


def test_view_porta_l_ancora_risolta_nel_dettaglio_e_fra_gli_ancorati(anagrafe, memoria):
    ident = memoria.remember("spegni la luce vecchia", detto_da="paolo",
                             ancore=[_VIVA, _SPARITA])
    casa = House.read(anagrafe, None)
    dettaglio = view(casa, [], memoria.fetch(), "ricordo", ident)
    assert [a["esiste"] for a in dettaglio["ancore"]] == [True, False]
    entita = view(casa, [], memoria.fetch(), "entita", "light.cucina")
    assert [a["esiste"] for a in entita["ricordi"][0]["ancore"]] == [True, False]


@pytest.mark.asyncio
async def test_fetch_porta_l_ancora_risolta(anagrafe, memoria):
    memoria.remember("spegni la luce vecchia", detto_da="paolo", ancore=[_SPARITA])
    esito = await ToolDispatcher(anagrafe, memoria).dispatch(
        "fetch", {"riferimento": "light.vecchia"})
    assert esito["ricordi"][0]["ancore"][0]["esiste"] is False
    # Il ricordo resta: sono parole del proprietario.
    assert memoria.count() == 1


def test_il_nome_dell_ancora_e_il_nome_vivo(anagrafe):
    """S-22 (Tappa 9, F3, 08/10/2026): il nome di un'entita' ancorata e' il
    nome che Home Assistant mostra (`House.name`, `topology.live_name`: il
    `friendly_name` dello specchio, poi il registro, poi l'id), non il solo
    nome del registro. Fino a quel giorno `House.tether` leggeva la voce
    dell'indice della memoria (`name` o `original_name`), e la pagina Memoria
    mostrava un'entita' senza nome nel registro col nome visto il giorno del
    ricordo, o col suo id.

    Mutazione ESEGUITA: `House.tether` che torna a leggere `entry.get("nome")`
    -- rossa con `assert None == 'Luce del portico'`."""
    registri = dict(_REGISTRI, entita=[
        *_REGISTRI["entita"], {"entity_id": "light.portico", "area_id": "cucina"}])
    anagrafe.hold_registries(registri)
    letta = House.read(anagrafe, None)
    casa = House(letta.home_space, Mirror(names={"light.portico": "Luce del portico"}))
    portico = {"tipo": "entita", "riferimento": "light.portico", "nome_visto": "portico"}
    assert casa.tether(portico)["nome_attuale"] == "Luce del portico"
    # Una regola sola: per ogni genere d'ancora, il nome e' quello di `House.name`.
    for ancora in (_VIVA, portico, {"tipo": "area", "riferimento": "cucina"}):
        assert casa.tether(ancora)["nome_attuale"] == casa.name(
            ancora["tipo"], ancora["riferimento"])


def test_il_nome_mostrato_non_e_mai_l_id(anagrafe):
    """08/10/2026 (`ux-ui-specialist` sulla pagina Memoria, giro su `1d7a909`):
    un dispositivo senza nome in Home Assistant usciva col suo id come
    `nome_attuale` (il ripiego di `topology.device_name`), e la pagina lo
    mostrava a chi aveva detto «la lavatrice». Il ripiego e' uno, in
    `render._shown`: nome di oggi, nome di allora, produttore e modello,
    «dispositivo senza nome» -- mai l'id.

    Mutazioni ESEGUITE: `House.tether` che torna a passare il nome uguale
    all'id -- rossa con `('d_lav', 'd_lav', 'attuale')`; `_shown` senza il ramo del
    costruttore -- rossa con `'dispositivo senza nome' == 'Bosch WAX'`."""
    from hiris.app.home_space.render import render_memory
    registri = dict(_REGISTRI, dispositivi=[
        {"id": "d_lav", "name": None, "manufacturer": "Bosch", "model": "WAX"},
        {"id": "d_muto", "name": None}])
    anagrafe.hold_registries(registri)
    casa = House.read(anagrafe, None)

    def ancora(riferimento, visto=None):
        a = {"tipo": "dispositivo", "riferimento": riferimento}
        if visto:
            a["nome_visto"] = visto
        resa = render_memory({"id": 1, "ancore": [a]}, casa)["ancore"][0]
        return resa["nome_attuale"], resa["nome_mostrato"], resa["nome_di"]

    assert ancora("d_lav") == (None, "Bosch WAX", "costruttore")
    assert ancora("d_muto") == (None, "dispositivo senza nome", "nessuno")
    assert ancora("d_lav", "lavatrice") == (
        None, "lavatrice (nome di allora; ora senza nome in Home Assistant)", "visto")
    assert ancora("d_via", "asciugatrice") == (
        None, ("asciugatrice — non esiste più in Home Assistant. Il ricordo resta "
               "valido, ma non è più collegato a niente."), "visto")
    assert ancora("d_via") == (None, "un dispositivo che non esiste più", "nessuno")
    resa = render_memory({"id": 2, "ancore": [_VIVA]}, casa)["ancore"][0]
    assert (resa["nome_mostrato"], resa["nome_di"]) == ("Luce cucina", "attuale")


def test_i_generi_d_ancora_sono_gli_stessi_nel_server_e_nella_pagina():
    """I generi d'ancora vivono in `memory.resolver.STORE_KEY_PER_TYPE`; il
    ripiego del nome (`render._NAMELESS`) e le etichette della pagina
    Memoria (`TETHER_TYPE_LABELS`, `memory-route.js`) li elencano. Un genere
    nuovo che entra da una parte sola si mostrerebbe senza nome o senza
    etichetta: la prova lo dice.
    Mutazione ESEGUITA: togliere `area` da `_NAMELESS` -- rossa."""
    import re
    from pathlib import Path

    from hiris.app.home_space.render import _NAMELESS
    from hiris.app.memory.resolver import STORE_KEY_PER_TYPE
    js = (Path(__file__).parent.parent / "hiris" / "app" / "static" / "config"
          / "memory-route.js").read_text(encoding="utf-8")
    labels = re.search(r"var TETHER_TYPE_LABELS = \{([^}]*)\}", js)
    assert labels, "TETHER_TYPE_LABELS non si trova piu' in memory-route.js"
    js_kinds = set(re.findall(r"(\w+):", labels.group(1)))
    assert set(_NAMELESS) == set(STORE_KEY_PER_TYPE) == js_kinds
