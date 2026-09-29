"""search e' l'unica porta che legge la casa; view non esiste piu' come
strumento (spec `2026-09-29-una-porta-sola-per-la-casa.md` §2, §4)."""
import pathlib

import pytest

from hiris.app.api.soffitto import consente
from hiris.app.home_space.tools import KNOWLEDGE_TOOLS, ToolDispatcher
from hiris.app.keeper.exchange import SOLA_LETTURA
from hiris.app.memory.store import MemoryStore
from tests.test_knowledge_tools import _semina_casa
from tests.test_mind_actuator_guards import _attributi, porte_home_assistant

_PERSONA_MARTA = {"specie": "persona", "id": "u-marta"}


@pytest.fixture
def archivio_casa(tmp_path):
    a = _semina_casa(tmp_path)
    yield a
    a.close()


@pytest.fixture
def memoria(tmp_path):
    m = MemoryStore(str(tmp_path / "memoria.db"))
    yield m
    m.close()


@pytest.fixture
def dispatcher(archivio_casa, memoria):
    return ToolDispatcher(archivio_casa, memoria)


@pytest.fixture
def dispatcher_as_user(archivio_casa, memoria):
    """Lo stesso costruttore, col soffitto di chi non amministra -- come le
    prove di `_AUTOMATION_BODY_ADMIN_ONLY` in `tests/test_admission.py`."""
    return ToolDispatcher(archivio_casa, memoria,
                          soffitto=consente(_PERSONA_MARTA, ruolo="utente"),
                          subject=_PERSONA_MARTA)


def test_view_non_e_piu_uno_strumento():
    """Mutazione ESEGUITA: rimettere VIEW_TOOL_DEF nel catalogo -- rossa."""
    nomi = [d["name"] for d in KNOWLEDGE_TOOLS]
    assert "view" not in nomi and "search" in nomi
    assert "view" not in SOLA_LETTURA


def test_search_dichiara_tutti_i_filtri_e_nessuno_e_obbligatorio():
    """Mutazione ESEGUITA: un `"required": ["nome"]` nello schema -- rossa."""
    search = next(d for d in KNOWLEDGE_TOOLS if d["name"] == "search")
    schema = search["input_schema"]
    assert set(schema["properties"]) == {
        "nome", "genere", "riferimento", "tipo", "stato", "classe", "area",
        "piano", "integrazione", "fermo_da", "cambiato_da", "sopra", "sotto",
        "in_esecuzione", "includi_nascoste", "includi_servizio", "ordina",
        "limite", "salta"}
    assert not schema.get("required")


@pytest.mark.asyncio
async def test_una_domanda_di_stato_passa_dai_filtri(dispatcher):
    """Mutazione ESEGUITA: `_search` risponde nella forma vecchia
    (`{"trovati": []}`) senza passare dalla porta -- rossa."""
    r = await dispatcher.dispatch("search", {"tipo": "light", "stato": "on"})
    assert {"trovate", "escluse", "profondita", "voci"} <= set(r)


@pytest.mark.asyncio
async def test_un_riferimento_da_il_dettaglio_di_prima(dispatcher):
    """Il dettaglio completo e' quello che dava `view`: stessa forma.

    Mutazione ESEGUITA: `detail=` legato a una funzione che restituisce
    `{"id": riferimento}` invece del dettaglio di `queries.view` -- rossa."""
    r = await dispatcher.dispatch("search", {"genere": "area",
                                             "riferimento": "cucina"})
    assert r["profondita"] == "completa"
    assert r["voci"][0]["esiste"] is True
    assert r["voci"][0]["entita"]


@pytest.mark.asyncio
async def test_chi_non_amministra_non_vede_il_corpo_di_un_automazione(dispatcher_as_user):
    """Review Focus 5. Mutazione ESEGUITA: non applicare `_ceiling_denies`
    nel dettaglio completo -- rossa."""
    r = await dispatcher_as_user.dispatch(
        "search", {"genere": "automazione", "riferimento": "automation.sveglia"})
    assert r["voci"][0]["esiste"] is True
    assert "corpo" not in r["voci"][0] or r["voci"][0]["corpo"] is None


@pytest.mark.asyncio
async def test_chi_amministra_vede_il_corpo_di_un_automazione(dispatcher):
    """Il gemello della prova sopra: senza di lui, un dettaglio che perdesse il
    corpo per TUTTI la farebbe passare. Mutazione ESEGUITA: `_ceiling_denies`
    sempre vero nel dettaglio completo -- rossa."""
    r = await dispatcher.dispatch(
        "search", {"genere": "automazione", "riferimento": "automation.sveglia"})
    assert r["voci"][0]["corpo"] == {"trigger": []}


@pytest.mark.asyncio
async def test_un_ricordo_si_apre_col_suo_numero_anche_scritto_come_testo(
        dispatcher, memoria):
    """`riferimento` arriva come stringa (`parse_filters` lo rende testo), e
    l'id di un ricordo e' un intero. Mutazione ESEGUITA: togliere la
    conversione in `_full_detail_sync` -- rossa (`esiste: False`)."""
    ident = memoria.remember("mi piace il caffe' la mattina", detto_da="paolo",
                             modality="fatto")
    r = await dispatcher.dispatch("search", {"genere": "ricordo",
                                             "riferimento": str(ident)})
    assert r["voci"][0]["esiste"] is True
    assert r["voci"][0]["testo"] == "mi piace il caffe' la mattina"


@pytest.mark.asyncio
async def test_un_filtro_sbagliato_torna_l_errore_della_porta(dispatcher):
    """`parse_filters` dice cosa non va: `_search` lo restituisce com'e'.
    Mutazione ESEGUITA: passare a `query_house` anche un esito d'errore --
    rossa (AttributeError, dichiarato come guasto dello strumento)."""
    r = await dispatcher.dispatch("search", {"genere": "piano"})
    assert r["errore"].startswith("genere «piano» sconosciuto")


@pytest.mark.asyncio
async def test_un_nome_che_non_combacia_non_dice_che_la_cosa_non_esiste(dispatcher):
    """Il divieto del 24/09/2026 sopravvive alla porta nuova: una ricerca per
    nome senza esito non e' «non esiste». Mutazione ESEGUITA: togliere il
    ramo `nulla_riconosciuto` da `_search` -- rossa."""
    r = await dispatcher.dispatch("search", {"nome": "xyzzy qwerty"})
    assert r["trovate"] == 0
    assert r["nulla_riconosciuto"] is True
    assert r.get("suggerimento")


@pytest.mark.asyncio
async def test_una_domanda_per_filtri_senza_esito_non_porta_il_suggerimento_dei_nomi(
        dispatcher):
    """`nulla_riconosciuto` parla di NOMI: su «luci con stato xyz» non c'e'
    nessun nome da non aver riconosciuto, e `escluse` dice gia' cosa manca.
    Mutazione ESEGUITA: dichiararlo a ogni `trovate == 0` -- rossa."""
    r = await dispatcher.dispatch("search", {"tipo": "light", "stato": "xyz"})
    assert r["trovate"] == 0
    assert "nulla_riconosciuto" not in r


def test_la_porta_della_casa_non_tocca_mai_una_porta_di_home_assistant():
    """Mutazione ESEGUITA: una chiamata `ha.call_service` in house_query.py -- rossa."""
    root = pathlib.Path(__file__).resolve().parents[1] / "hiris" / "app" / "home_space"
    for nome in ("house_query.py", "privacy.py"):
        usati = _attributi((root / nome).read_text(encoding="utf-8"))
        assert not usati & porte_home_assistant(), nome
