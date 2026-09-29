"""search e' l'unica porta che legge la casa; view non esiste piu' come
strumento (spec `2026-09-29-una-porta-sola-per-la-casa.md` §2, §4)."""
import json
import pathlib

import pytest

from hiris.app.api.soffitto import consente
from hiris.app.home_space.tools import KNOWLEDGE_TOOLS, ToolDispatcher
from hiris.app.keeper.exchange import SOLA_LETTURA
from hiris.app.memory.store import MemoryStore
from hiris.app.proxy.entity_cache import _to_minimal
from tests.test_house_query import BRIDGE_CEILING_CHARS

# Le fixture della casa seminata hanno UNA definizione, in
# `tests/test_knowledge_tools.py`: importate, pytest le trova nel namespace
# del modulo. Ricopiarle qui era un doppione (review del Task 4, 29/09/2026).
from tests.test_knowledge_tools import (  # noqa: F401 -- fixture di pytest
    _semina_casa,
    archivio_casa,
    dispatcher,
    memoria,
)
from tests.test_mind_actuator_guards import _attributi, porte_home_assistant

_PERSONA_MARTA = {"specie": "persona", "id": "u-marta"}


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


# -- Il cancello del peso sul dettaglio VERO (review finale, C2, 30/09/2026) --
#
# Il cancello di `test_house_query.py` usa un dettaglio finto di una riga: non
# poteva vedere che il dettaglio vero di un'area elencava ogni entita'. Qui la
# casa e' costruita come quella misurata il 29/09 -- Telecamere 287 entita',
# 120 disabilitate; 145 senza area; un dispositivo da 60; un'integrazione con
# 60 mute -- e la risposta passa dalla `search` vera, `queries.view` compreso.

_CAMERAS = ("garage", "ingresso", "giardino", "retro", "cancello", "terrazzo")
_KINDS = (("switch", "config", None), ("binary_sensor", None, "motion"),
          ("sensor", "diagnostic", "signal_strength"), ("number", "config", None),
          ("select", "config", None), ("camera", None, None), ("button", "config", None))


def _big_entity(i: int, area_id, *, disabled=False, hidden=False,
                device_id=None, platform="reolink") -> dict:
    domain, category, device_class = _KINDS[i % len(_KINDS)]
    camera = _CAMERAS[i % len(_CAMERAS)]
    return {"id": f"{domain}.telecamera_{camera}_funzione_numero_{i}", "nome": "",
            "area_id": area_id, "dispositivo_id": device_id, "piattaforma": platform,
            "categoria": category, "classe": device_class, "unita": None,
            "disabilitata": int(disabled), "nascosta": int(hidden)}


def _big_home() -> dict:
    entita = [_big_entity(i, "telecamere", disabled=i < 120, hidden=120 <= i < 150)
              for i in range(287)]
    entita += [_big_entity(1000 + i, None, platform="tuya") for i in range(145)]
    entita += [_big_entity(2000 + i, None, device_id="dev_nvr", platform="hydrawise")
               for i in range(60)]
    return {
        "piani": [{"id": "terra", "nome": "Piano terra", "livello": 0}],
        "aree": [{"id": "telecamere", "nome": "Telecamere", "piano_id": "terra",
                  "alias": [], "etichette": []}],
        "dispositivi": [{"id": "dev_nvr", "nome": "NVR", "nome_utente": None,
                         "produttore": "Reolink", "modello": "RLN16-410",
                         "area_id": "telecamere", "disabilitato": 0, "etichette": []}],
        "entita": entita, "etichette": [], "categorie": [], "integrazioni": [],
    }


class _BigMirror:
    """Lo specchio vero (`_to_minimal`): nomi lunghi, stati, istanti, e le
    capacita' che fanno uscire `capacita`."""
    loaded = True

    def __init__(self, home: dict):
        self._rows = [_to_minimal({
            "entity_id": e["id"],
            "state": "unavailable" if e["piattaforma"] == "hydrawise" else "on",
            "last_changed": "2026-09-29T07:11:00.123456+00:00",
            "attributes": {"friendly_name": e["id"].split(".")[1].replace("_", " ").title(),
                           "supported_features": 31, "device_class": e["classe"]}})
            for e in home["entita"] if not e["disabilitata"]]

    def all_states(self):
        return self._rows


@pytest.fixture
def big_door(tmp_path):
    home = _big_home()
    casa = _semina_casa(tmp_path, casa=home, comportamento=[])
    memoria = MemoryStore(str(tmp_path / "memoria.db"))
    yield ToolDispatcher(casa, memoria, cache=_BigMirror(home))
    memoria.close()
    casa.close()


def _size(answer: dict) -> int:
    return len(json.dumps(answer, ensure_ascii=False))


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [
    {"genere": "area", "riferimento": "telecamere"},
    {"genere": "dispositivo", "riferimento": "dev_nvr"},
    {"genere": "integrazione", "riferimento": "hydrawise"},
])
async def test_il_dettaglio_vero_di_una_cosa_grande_sta_sotto_la_soglia_del_ponte(
        big_door, arguments):
    """Mutazione ESEGUITA: `_within_ceiling` che restituisce il dettaglio
    intatto -- rossa su tutti e tre i casi (l'area a ~94.000 caratteri)."""
    r = await big_door.dispatch("search", arguments)
    voce, = r["voci"]
    assert voce["esiste"] is True
    assert _size(r) < BRIDGE_CEILING_CHARS, (arguments, _size(r))
    righe = len(voce["entita"]) + len(voce.get("entita_nascoste", []))
    assert righe == 50
    # Cio' che resta si dichiara, col modo di chiederlo: mai un taglio muto.
    assert sum(v for k, v in voce["oltre"].items() if k != "suggerimento") > 0
    assert "search" in voce["oltre"]["suggerimento"]


@pytest.mark.asyncio
async def test_le_disabilitate_di_un_area_grande_si_contano(big_door):
    """Le 120 disabilitate di Telecamere, stato vuoto: contate, non elencate.

    Mutazione ESEGUITA: rimetterle in `entita` in `_view_area` -- rossa."""
    r = await big_door.dispatch("search", {"genere": "area", "riferimento": "telecamere"})
    voce, = r["voci"]
    assert voce["entita_disabilitate"] == 120
    assert not any(e.get("disabilitata") for e in voce["entita"])
    # 137 visibili dell'area + 60 del NVR, che ne eredita l'area, e 30
    # nascoste: 50 righe, il resto in `oltre`.
    assert voce["oltre"]["entita"] == 147
    assert voce["oltre"]["entita_nascoste"] == 30


def test_il_dettaglio_vero_senza_area_sta_sotto_la_soglia_del_ponte(big_door):
    """«senza area» misurava ~126.000 caratteri sulla casa vera.

    Mutazione ESEGUITA: la stessa di sopra -- rossa."""
    from hiris.app.home_space.privacy import redact_row
    voce = redact_row(big_door._full_detail_sync(
        "area", "__senza_area__", mirror=big_door._mirror(),
        translations={"lette": False, "motivo": "prova"}))
    assert voce["esiste"] is True
    assert len(voce["entita"]) == 50 and voce["oltre"]["entita"] > 0
    assert 'area=\\"senza area\\"' in json.dumps(voce, ensure_ascii=False)
    assert _size(voce) < BRIDGE_CEILING_CHARS
