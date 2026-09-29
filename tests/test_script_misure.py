"""Lo script dei verdetti: i due difetti trovati il 28/09 e la sezione token."""
import importlib.util
import pathlib

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "misure.py"


def _m():
    spec = importlib.util.spec_from_file_location("misure", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _turno(specie="chat", canale="ponte", strumenti=()):
    return {"species": specie, "channel": canale, "tools": list(strumenti),
            "iterations": 1, "duration_ms": 1000, "subject": None,
            "output_tokens": 50}


def test_ToolSearch_e_i_prefissi_non_sono_strumenti_del_catalogo():
    """Il «-3 mai chiamati» del 28/09.

    Mutazione ESEGUITA: non togliere ToolSearch -- rossa."""
    assert _m().strumenti_catalogo(
        ["ToolSearch", "mcp__hiris__view", "view", "search"]) == ["view", "view", "search"]


def test_i_canali_si_leggono_dai_TURNI_non_dai_carichi():
    """Il «un canale solo» del 28/09: la chat girava su entrambi.

    Mutazione ESEGUITA: leggere i canali solo dai turni con carichi -- rossa."""
    dati = [(_turno(canale="catena"), [{"tools_chars": 1}]),
            (_turno(canale="ponte"), [])]
    assert _m().canali_per_specie(dati)["chat"] == {"catena", "ponte"}


def test_i_token_si_sommano_per_attore_e_canale_con_i_NULL_contati_a_parte():
    """Mutazione ESEGUITA: sommare i None come zero senza contarli -- rossa."""
    giro = {"input_tokens": 10, "cache_read_tokens": 90,
            "cache_write_tokens": 100, "cache_ttl": "1h"}
    dati = [(_turno(specie="analista"), [giro]),
            (_turno(specie="analista"), [{"input_tokens": None,
                                          "cache_read_tokens": None,
                                          "cache_write_tokens": None,
                                          "cache_ttl": None}])]
    t = _m().token_per_attore(dati)[("analista", "ponte")]
    assert t["turni"] == 2
    assert t["nuovi"] == 10 and t["letti"] == 90 and t["scritti"] == 100
    assert t["scritti_1h"] == 100
    assert t["giri_senza_token"] == 1
    assert t["quota_cache"] == 90 / 200
