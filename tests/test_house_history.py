"""La storia della casa, pura (spec `docs/design/2026-09-30-la-storia.md`).

La finestra, la scelta, la profondita' e le righe, senza rete: le risposte
di Home Assistant si passano gia' lette, nella forma vera di
`HAClient.history`, `hourly_statistics`, `traces` e `system_log`."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from hiris.app.home_space import house_history as hh
from hiris.app.home_space import house_query as hq

ROMA = "Europe/Rome"
T0 = 1_790_700_000.0  # 29/09/2026 16:40 UTC, 18:40 a Roma


def _q(**argomenti):
    query = hh.parse_query(argomenti, now=T0, timezone=ROMA)
    assert not isinstance(query, dict), query
    return query


def test_senza_quando_la_finestra_e_di_ventiquattro_ore_e_il_genere_e_stati():
    """Spec §2: default `genere` stati, default `ore` 24.

    Mutazione ESEGUITA: `DEFAULT_HOURS = 12.0` -- rossa."""
    query = _q()
    assert query.kind == "stati"
    assert query.end.timestamp() == T0
    assert query.end - query.start == timedelta(hours=24)
    assert query.start.utcoffset() == timedelta(hours=2)


@pytest.mark.parametrize("quando,ore", [
    (datetime(2026, 10, 25, 12, 0, tzinfo=ZoneInfo(ROMA)), 12),
    (datetime(2026, 10, 25, 12, 0, tzinfo=ZoneInfo(ROMA)), 24),
    (datetime(2026, 3, 29, 12, 0, tzinfo=ZoneInfo(ROMA)), 12),
    (datetime(2026, 3, 29, 12, 0, tzinfo=ZoneInfo(ROMA)), 24),
    (datetime(2026, 10, 25, 2, 30, tzinfo=ZoneInfo(ROMA), fold=1), 1),
    (datetime(2026, 10, 25, 2, 30, tzinfo=ZoneInfo(ROMA), fold=0), 1),
])
def test_ore_sono_ore_vere_anche_nel_giorno_del_cambio_d_ora(quando, ore):
    """`ore=N` dura N ore VERE: la finestra si costruisce dall'epoch. In ora
    del muro `ore=24` il 25/10 (25 ore) o `ore=12` erano 25 e 13 ore vere.

    Mutazione ESEGUITA: `start = now_local - timedelta(hours=hours)` --
    rossa."""
    ora = quando.timestamp()
    query = hh.parse_query({"ore": ore}, now=ora, timezone=ROMA)
    assert query.end.timestamp() - query.start.timestamp() == ore * 3600
    assert query.hours == ore
    assert query.end.timestamp() == ora


@pytest.mark.parametrize("ore", [True, False, "nan", "inf", float("nan"), float("inf")])
def test_ore_non_numeriche_o_non_finite_sono_rifiutate(ore):
    """`True` non e' un'ora e `nan`/`inf` non sono un numero di ore.

    Mutazione ESEGUITA: togliere il controllo `isinstance(raw_hours, bool)`
    -- rossa su True/False; togliere `math.isfinite` -- rossa su nan/inf."""
    risposta = hh.parse_query({"ore": ore}, now=T0, timezone=ROMA)
    assert isinstance(risposta, dict) and "ore vuole un numero" in risposta["errore"]


def test_oggi_e_la_mezzanotte_della_casa_non_quella_di_greenwich():
    """Alle 00:30 di Roma in UTC e' ancora ieri.

    Mutazione ESEGUITA: il giorno di «oggi» preso da
    `datetime.fromtimestamp(now, UTC).date()` -- rossa."""
    passata = datetime(2026, 9, 30, 0, 30, tzinfo=ZoneInfo(ROMA)).timestamp()
    query = hh.parse_query({"da": "oggi"}, now=passata, timezone=ROMA)
    assert query.start.isoformat() == "2026-09-30T00:00:00+02:00"
    assert query.end.timestamp() == passata


def test_ieri_da_mezzanotte_a_mezzanotte_anche_col_cambio_d_ora():
    """Spec §9: «oggi» / «ieri» anche a cavallo del cambio d'ora. Il
    25/10/2026 a Roma dura 25 ore.

    Mutazione ESEGUITA: `a="ieri"` come `da` + 86.400 secondi -- rossa;
    `hours` come `(end - start).total_seconds()` (due `datetime` dello stesso
    `ZoneInfo` si sottraggono in ora del muro: 24 invece di 25) -- rossa."""
    lunedi = datetime(2026, 10, 26, 10, 0, tzinfo=ZoneInfo(ROMA)).timestamp()
    query = hh.parse_query({"da": "ieri", "a": "ieri"}, now=lunedi, timezone=ROMA)
    assert query.start.isoformat() == "2026-10-25T00:00:00+02:00"
    assert query.end.isoformat() == "2026-10-26T00:00:00+01:00"
    assert query.hours == 25


def test_la_quattordici_diventa_una_chiamata_sola():
    """La #14 della batteria, «consumo di oggi contro ieri» (spec §2).

    Mutazione ESEGUITA: pretendere `a` quando c'e' `da` -- rossa."""
    query = _q(genere="valori", nome="energia consumata oggi", da="ieri")
    assert query.kind == "valori"
    assert query.who.name == "energia consumata oggi"
    assert query.start.isoformat() == "2026-09-28T00:00:00+02:00"
    assert query.end.timestamp() == T0


def test_i_filtri_di_chi_sono_quelli_di_search():
    """Stessi nomi, stessa lettura: `parse_filters` di `house_query`.

    Mutazione ESEGUITA: leggere `area` a mano in `parse_query` e non
    passarla a `parse_filters` -- rossa."""
    argomenti = {"area": "Cucina", "tipo": "light", "includi_nascoste": True,
                 "limite": 10, "salta": 5}
    assert _q(**argomenti).who == hq.parse_filters(argomenti)


@pytest.mark.parametrize("argomenti,parole", [
    ({"ore": 2, "da": "oggi"}, "una finestra si dice in un modo solo"),
    ({"a": "oggi"}, "a vuole anche da"),
    ({"da": "domani"}, "vuole «oggi», «ieri» o un istante ISO"),
    ({"da": "2026-09-29T08:00:00"}, "col fuso"),
    ({"da": "2026-09-29T08:00:00+02:00", "a": "2026-09-30T08:00:00+02:00"},
     "nel futuro"),
    ({"da": "2026-09-29T20:00:00+02:00"}, "da deve venire prima di a"),
    ({"da": "2026-01-01T00:00:00+01:00"}, "supera i 90 giorni"),
    ({"ore": 0}, "ore va da piu' di 0"),
    ({"ore": 3000}, "ore va da piu' di 0"),
    ({"ore": "tante"}, "ore vuole un numero"),
    ({"genere": "giorni"}, "genere «giorni» sconosciuto"),
    ({"livello": "ERROR"}, "livello vale solo con genere=errori"),
    ({"esecuzione": "r1"}, "esecuzione vale solo con genere=esecuzioni"),
    ({"genere": "errori", "area": "Cucina"}, "area: non vale per genere=errori"),
    ({"genere": "errori", "livello": "DEBUG"}, "livello accetta"),
    ({"genere": "esecuzioni", "riferimento": "light.cucina_1"},
     "non e' un'automazione ne' uno script"),
    ({"genere": "esecuzioni", "tipo": "light"}, "tipo accetta automation o script"),
    ({"genere": "esecuzioni", "classe": "door"}, "classe non vale"),
    ({"genere": "esecuzioni", "esecuzione": "   "}, "un testo non vuoto"),
    ({"limite": 51}, "limite va da 0 a 50"),
])
def test_un_argomento_sbagliato_e_un_errore_mai_un_altra_domanda(argomenti, parole):
    """Spec §2 (e §2.4 della porta): un filtro che non vale si dice, non si
    ignora; una finestra si dice in un modo solo.

    Mutazione ESEGUITA: togliere il controllo `ore` con `da`/`a` -- rossa
    sul primo caso; togliere il controllo dei filtri di `errori` -- rossa sul
    caso `area`."""
    risposta = hh.parse_query(argomenti, now=T0, timezone=ROMA)
    assert isinstance(risposta, dict) and parole in risposta["errore"], risposta


def test_gli_errori_accettano_integrazione_e_livello():
    """Spec §2: per `errori` valgono solo `integrazione` e `livello`, e il
    livello si porta in maiuscolo.

    Mutazione ESEGUITA: `level = str(a["livello"]).strip()` senza `.upper()`
    -- rossa."""
    query = _q(genere="errori", integrazione="zha", livello="error")
    assert (query.kind, query.who.platform, query.level) == ("errori", "zha", "ERROR")


def test_la_storia_non_ha_una_sua_scelta_di_chi():
    """Spec §2: «un solo punto che decide di chi, non due». Questo modulo non
    confronta nomi e non scende l'albero della casa: lo fa
    `house_query.select_subjects`.

    Mutazione ESEGUITA: importare `name_matches` in house_history.py -- rossa."""
    import inspect
    sorgente = inspect.getsource(hh)
    for vietato in ("name_matches", "hierarchy(", "_entity_matches",
                    "_any_name_matches"):
        assert vietato not in sorgente, vietato
