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


def test_i_token_di_una_domanda_sono_quelli_dei_turni_di_chat_nella_sua_finestra():
    """La batteria sa quando una domanda e' finita (`ts`) e quanto e' durata
    (`secondi`); il registro dei turni sa i token. Si uniscono per finestra.

    Mutazione ESEGUITA: tolto il filtro `species == "chat"` -- rossa (il turno
    dell'analista caduto nella stessa finestra entra nel conto: `nuovi` 5010)."""
    giro = {"input_tokens": 10, "cache_read_tokens": 90, "cache_write_tokens": 0}
    dentro = dict(_turno(canale="catena"), ts=1000.0)
    fuori = dict(_turno(canale="catena"), ts=2000.0)
    altro = dict(_turno(specie="analista", canale="catena"), ts=1001.0)
    dati = [(dentro, [giro, giro]), (fuori, [giro]),
            (altro, [{"input_tokens": 5000, "cache_read_tokens": 0,
                      "cache_write_tokens": 0}])]
    esiti = [{"n": 7, "ts": 1001.0, "secondi": 12.0, "stato": "ok"},
             {"n": 8, "ts": 5000.0, "secondi": 3.0, "stato": "ok"}]
    righe = _m().question_tokens(dati, esiti)
    assert righe[7] == {"turni": 1, "giri": 2, "nuovi": 20, "letti": 180,
                        "scritti": 0, "uscita": 50, "secondi": 12.0}
    assert righe[8]["turni"] == 0, "una domanda senza turno trovato si dichiara, non si inventa"


def test_due_domande_una_dopo_l_altra_non_si_contano_lo_stesso_turno():
    """La batteria aspetta mezzo secondo fra due domande: il turno della prima
    cade anche nella finestra della seconda. Va contato una volta.

    Mutazione ESEGUITA: assegnato il turno all'ULTIMA domanda la cui finestra lo
    contiene -- rossa (`(0, 2)`: la seconda si prende anche il turno della prima)."""
    giro = {"input_tokens": 100, "cache_read_tokens": 0, "cache_write_tokens": 0}
    primo = dict(_turno(canale="catena"), ts=1010.0)
    secondo = dict(_turno(canale="catena"), ts=1020.6)
    esiti = [{"n": 1, "ts": 1010.1, "secondi": 10.0, "stato": "ok"},
             {"n": 2, "ts": 1020.7, "secondi": 10.0, "stato": "ok"}]
    righe = _m().question_tokens([(primo, [giro]), (secondo, [giro])], esiti)
    assert (righe[1]["turni"], righe[2]["turni"]) == (1, 1)
    assert righe[1]["nuovi"] == righe[2]["nuovi"] == 100

