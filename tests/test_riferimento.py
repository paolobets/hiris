"""RIFERIMENTO (Tappa 3, Task 9; B-18, B-20, B-51; decisione D5).

Un riferimento scritto da una persona o dal modello -- un'area, un piano,
un'integrazione -- trova le stesse righe del nome esatto quando differisce
solo per maiuscole, accenti o spazi. Gli articoli no (D5: «senza articoli»).

Misurato sulla cattura del 01/10/2026 sera (piano della Tappa 3, D5): 118
casi in cui `search` dava zero perche' il confronto era esatto, 117 dei quali
sono le 39 integrazioni scritte con la maiuscola.
"""
import ast
from pathlib import Path

from hiris.app.home_space import house_history as hh
from hiris.app.home_space import house_query as hq
from hiris.app.home_space.house import House
from tests.test_house_history import _REGISTRO, _q
from tests.test_house_query import STATI, T0, _casa, _dettaglio, _specchio

APP = Path(__file__).resolve().parents[1] / "hiris" / "app"


def _ids(home_space=None, behavior=(), mirror=None, **argomenti):
    filtri = hq.parse_filters(argomenti)
    assert not isinstance(filtri, dict), filtri
    risposta = hq.query_house(House(home_space or _casa(), mirror or _specchio(STATI)),
                              list(behavior), filtri,
                              detail=_dettaglio, now=T0)
    return sorted(v["id"] for v in risposta["voci"])


def _casa_accentata():
    casa = _casa()
    casa["piani"] = [{"id": "primo", "nome": "Primo piano", "livello": 1}]
    casa["aree"][0] = {**casa["aree"][0], "nome": "Città", "piano_id": "primo"}
    return casa


def test_l_integrazione_scritta_con_la_maiuscola_trova_le_stesse_righe():
    """Il caso misurato: «Hydrawise» dava zero righe, «hydrawise» le dava.

    Mutazione ESEGUITA: `_place_matches` torna al confronto esatto
    dell'integrazione -- rossa."""
    esatto = _ids(tipo="light", integrazione="ave")
    assert esatto, "la casa di prova deve avere luci di «ave»"
    assert _ids(tipo="light", integrazione="AVE") == esatto
    assert _ids(tipo="light", integrazione=" Ave ") == esatto


def test_l_area_e_il_piano_ignorano_accenti_maiuscole_e_spazi():
    """Mutazione ESEGUITA: area e piano tornano a `.strip().lower()` -- rossa
    (l'accento e lo spazio doppio non si piegano)."""
    casa = _casa_accentata()
    esatto = _ids(casa, tipo="light", area="Città")
    assert esatto
    assert _ids(casa, tipo="light", area="CITTA ") == esatto
    piano = _ids(casa, tipo="light", piano="Primo piano")
    assert piano == esatto
    assert _ids(casa, tipo="light", piano="  primo   PIANO") == piano


def test_le_aree_si_filtrano_per_piano_con_la_stessa_regola():
    casa = _casa_accentata()
    filtri = hq.parse_filters({"genere": "area", "piano": "PRIMO  piano"})
    voci = hq.query_house(House(casa, _specchio(STATI)), [], filtri,
                          detail=_dettaglio, now=T0)["voci"]
    assert [v["id"] for v in voci] == ["soggiorno"]


def test_i_dispositivi_si_filtrano_per_integrazione_con_la_stessa_regola():
    """`_device_rows` confrontava l'integrazione da se', esatta."""
    casa = _casa()
    casa["entita"][0] = {**casa["entita"][0], "dispositivo_id": "dev_lavatrice"}

    def dispositivi(integrazione):
        filtri = hq.parse_filters({"genere": "dispositivo", "integrazione": integrazione})
        return [v["id"] for v in hq.query_house(House(casa, _specchio(STATI)), [], filtri,
                                                detail=_dettaglio, now=T0)["voci"]]
    assert dispositivi("ave") == ["dev_lavatrice"]
    assert dispositivi("AVE") == ["dev_lavatrice"]


def test_gli_articoli_non_si_tolgono():
    """D5, «senza articoli»: «la cucina» non e' «cucina». La regola resta
    quella che tutte le copie avevano gia'."""
    casa = _casa_accentata()
    assert _ids(casa, tipo="light", area="la città") == []


def test_gli_errori_della_storia_trovano_l_integrazione_con_la_maiuscola():
    """`house_history.error_rows` confrontava l'integrazione esatta.

    Mutazione ESEGUITA: il confronto torna esatto -- rossa."""
    esatto = hh.error_rows(_q(cosa="errori", integrazione="zha"), _REGISTRO)["voci"]
    assert esatto
    assert hh.error_rows(_q(cosa="errori", integrazione="ZHA"), _REGISTRO)["voci"] == esatto


def _unicodedata_normalize_calls(albero) -> int:
    return sum(1 for nodo in ast.walk(albero)
               if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
               and nodo.func.attr == "normalize"
               and isinstance(nodo.func.value, ast.Name)
               and nodo.func.value.id == "unicodedata")


def test_gli_accenti_si_piegano_in_un_posto_solo():
    """B-20: la piegatura degli accenti stava in tre posti (il normalizzatore
    dei nomi e i due slug). Il cancello chiede i file alla cartella, non a un
    elenco: un `unicodedata.normalize` nuovo, ovunque nel prodotto, lo
    arrossisce.

    Mutazione ESEGUITA: rimettere `unicodedata.normalize("NFKD", ...)` in
    `keeper/recipient._slugify` -- rossa."""
    trovate = {p.relative_to(APP).as_posix(): n for p in sorted(APP.rglob("*.py"))
               if (n := _unicodedata_normalize_calls(
                   ast.parse(p.read_text(encoding="utf-8"))))}
    assert trovate == {"home_space/reference.py": 1}


def test_gli_slug_tengono_il_proprio_filtro_ascii():
    """Gli slug usano la piegatura comune e tengono il loro filtro: le due
    forme misurate restano le stesse."""
    from hiris.app.action.construction.composer import available_slug
    from hiris.app.keeper.recipient import _slugify
    assert available_slug("Perché  la Città?", set()) == "perche_la_citta"
    assert _slugify("Telefono di Andrè") == "telefono_di_andre"
    assert _slugify("日本") == "unknown"


def test_i_tipi_di_ancora_si_scrivono_una_volta():
    """B-51: i tipi di ancora erano scritti a mano in `memory/resolver._ARCHIVI`
    e in `memory/interpretation.VOCABULARY["ancore"]`. Il vocabolario li chiede
    all'anagrafe.

    Mutazione ESEGUITA: aggiungere un tipo a `_ARCHIVI` -- entra nel
    vocabolario senza toccare `interpretation.py`."""
    from hiris.app.memory.interpretation import VOCABULARY
    from hiris.app.memory.resolver import STORE_KEY_PER_TYPE
    assert VOCABULARY["ancore"] == frozenset(STORE_KEY_PER_TYPE)
    sorgente = ast.parse((APP / "memory" / "interpretation.py").read_text(encoding="utf-8"))
    scritti = [nodo for nodo in ast.walk(sorgente)
               if isinstance(nodo, ast.Set)
               and {"area", "dispositivo"} <= {getattr(e, "value", None) for e in nodo.elts}]
    assert scritti == []


def test_il_normalizzatore_e_pubblico_in_home_space():
    from hiris.app.home_space.reference import normalize
    assert normalize("  La   CITTÀ ") == "la citta"
    assert normalize("") == ""
