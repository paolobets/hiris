"""La storia della casa, pura (spec `docs/design/2026-09-30-la-storia.md`).

La finestra, la scelta, la profondita' e le righe, senza rete: le risposte
di Home Assistant si passano gia' lette, nella forma vera di
`HAClient.history`, `hourly_statistics`, `traces` e `system_log`."""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from hiris.app.home_space import house_history as hh
from hiris.app.home_space import house_query as hq
from hiris.app.home_space.house import House
from tests.test_briefing import _casa_grande
from tests.test_house_query import (
    BRIDGE_CEILING_CHARS,
    STATI,
    T_IERI,
    _automazioni,
    _casa,
    _luce,
    _specchio,
)

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


@pytest.mark.parametrize("argomenti", [{}, {"da": "oggi"}, {"da": "ieri", "a": "oggi"}])
def test_adesso_col_suo_orologio_vero_non_e_nel_futuro(argomenti):
    """`time.time()` ha piu' cifre dei microsecondi di un `datetime`: la
    finestra che finisce adesso non e' «nel futuro» per l'arrotondamento
    (trovato eseguendo il gestore del Task 7, 30/09/2026).

    Mutazione ESEGUITA: `end.timestamp() > now` in `_window` -- rossa."""
    adesso = T0 + 0.1234567
    # il caso c'e' davvero: l'arrotondamento porta «adesso» dopo `adesso`
    assert datetime.fromtimestamp(adesso, tz=ZoneInfo(ROMA)).timestamp() > adesso
    query = hh.parse_query(argomenti, now=adesso, timezone=ROMA)
    assert not isinstance(query, dict), query


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


_NESSUNA = {"nascoste": 0, "servizio": 0, "disabilitate": 0}


def _scegli(query, casa=None, comportamento=(), stati=None):
    chosen = hh.choose(query, House(casa or _casa(), _specchio(stati or STATI)),
                       list(comportamento), now=T0)
    assert not isinstance(chosen, dict), chosen
    return chosen


def _punto(quando, valore):
    return {"quando": quando, "valore": valore}


_INIZIO = "2026-09-28T16:40:00+00:00"   # l'inizio della finestra di 24 ore
_LUCE_1 = [_punto(_INIZIO, "off"), _punto("2026-09-29T10:00:00+00:00", "on"),
           _punto("2026-09-29T12:00:00+00:00", "off"),
           _punto("2026-09-29T12:30:00+00:00", "off")]


def test_una_cosa_sola_da_ogni_cambio_dal_piu_recente():
    """Profondita' completa: ogni cambio vero, con l'ora nel fuso della casa.
    Il primo punto e' lo stato all'inizio della finestra, e un punto uguale
    al precedente non e' un cambio.

    Mutazione ESEGUITA: contare il primo punto anche quando sta
    all'inizio della finestra -- rossa (tre righe)."""
    query = _q(riferimento="light.soggiorno_1")
    chosen = _scegli(query)
    assert chosen.depth == "completa" and chosen.found == 1
    uscita = hh.state_rows(query, chosen, {"light.soggiorno_1": _LUCE_1},
                           truncated=False, acts=[], current=STATI)
    assert uscita["voci"] == [
        {"quando": "2026-09-29T14:00:00+02:00", "stato": "off"},
        {"quando": "2026-09-29T12:00:00+02:00", "stato": "on"}]
    assert uscita["soggetto"]["id"] == "light.soggiorno_1"
    assert uscita["finestra"] == {"da": "2026-09-28T18:40:00+02:00",
                                  "a": "2026-09-29T18:40:00+02:00"}
    assert "cronaca_non_letta" not in uscita


def _atto(ident, entita, ritardo, quando="2026-09-29T10:00:00+00:00", eseguito=True):
    base = datetime.fromisoformat(quando).timestamp()
    return {"id": ident, "entita": [entita], "quando_ts": base + ritardo,
            "origine": "chat", "servizio": "light.turn_on", "eseguito": eseguito}


def test_per_mano_di_hiris_e_probabile_e_il_piu_vicino():
    """Home Assistant non firma i cambi: l'aggancio e' entita' + istante
    (60 secondi), e fra due atti vince il piu' vicino.

    Mutazione ESEGUITA: `MATCH_TOLERANCE_S = 600` -- rossa (l'atto a 180
    secondi dal cambio delle 12:00 diventerebbe suo); prendere il primo atto
    che passa invece del piu' vicino -- rossa sull'id."""
    query = _q(riferimento="light.soggiorno_1")
    atti = [_atto(1, "light.soggiorno_1", 50), _atto(2, "light.soggiorno_1", 5),
            _atto(3, "light.soggiorno_2", 1),
            _atto(4, "light.soggiorno_1", 180, quando="2026-09-29T12:00:00+00:00")]
    uscita = hh.state_rows(query, _scegli(query), {"light.soggiorno_1": _LUCE_1},
                           truncated=False, acts=atti, current=STATI)
    mezzogiorno, mattina = uscita["voci"]
    assert "per_mano_di" not in mezzogiorno
    assert mattina["per_mano_di"] == "HIRIS"
    assert mattina["abbinamento"] == "probabile"
    assert mattina["atto"]["id"] == 2


def test_un_atto_non_eseguito_non_e_per_mano_di_hiris():
    """S-03: la cronaca scrive anche gli atti rifiutati (`eseguito` falso:
    Home Assistant ha detto no, o il freno ha fermato la chiamata). Un atto
    che non e' avvenuto non ha cambiato niente: il cambio a 10 secondi da
    lui NON e' per mano di HIRIS -- e fra un rifiutato piu' vicino e un
    eseguito entro la tolleranza vince l'eseguito."""
    query = _q(riferimento="light.soggiorno_1")
    rifiutato = [_atto(1, "light.soggiorno_1", 10, eseguito=False)]
    uscita = hh.state_rows(query, _scegli(query), {"light.soggiorno_1": _LUCE_1},
                           truncated=False, acts=rifiutato, current=STATI)
    assert all("per_mano_di" not in voce for voce in uscita["voci"])

    entrambi = rifiutato + [_atto(2, "light.soggiorno_1", 40)]
    uscita = hh.state_rows(query, _scegli(query), {"light.soggiorno_1": _LUCE_1},
                           truncated=False, acts=entrambi, current=STATI)
    _mezzogiorno, mattina = uscita["voci"]
    assert mattina["atto"]["id"] == 2


def test_una_cronaca_che_non_risponde_si_dichiara():
    """«Non l'ha fatto HIRIS» e «non ho potuto guardare» hanno due facce.

    Mutazione ESEGUITA: non scrivere `cronaca_non_letta` -- rossa."""
    query = _q(riferimento="light.soggiorno_1")
    uscita = hh.state_rows(query, _scegli(query), {"light.soggiorno_1": _LUCE_1},
                           truncated=False, acts=None, current=STATI)
    assert "cronaca_non_letta" in uscita


def test_un_entita_rumorosa_si_ferma_a_cinquanta_righe_dal_piu_recente():
    """Review Focus 3: 200 cambi in una notte accanto a una luce tranquilla.

    Mutazione ESEGUITA: non scrivere `oltre` -- rossa; ordinare dal piu'
    vecchio -- rossa sulla prima riga."""
    query = _q(tipo="light")
    chosen = _scegli(query)
    assert chosen.depth == "media" and chosen.found == 2
    notte = [_punto((datetime(2026, 9, 29, 0, 0, tzinfo=ZoneInfo("UTC"))
                     + timedelta(minutes=i)).isoformat(), "on" if i % 2 else "off")
             for i in range(200)]
    sera = [_punto(_INIZIO, "off"), _punto("2026-09-28T20:00:00+00:00", "on")]
    uscita = hh.state_rows(query, chosen, {"light.soggiorno_2": notte,
                                           "light.soggiorno_1": sera},
                           truncated=False, acts=[], current=STATI)
    assert len(uscita["voci"]) == 50
    assert uscita["voci"][0] == {"id": "light.soggiorno_2",
                                 "quando": "2026-09-29T05:19:00+02:00", "stato": "on"}
    assert uscita["oltre"]["restano"] == 151 and uscita["oltre"]["salta"] == 50
    assert "restringi" in uscita["oltre"]["consiglio"]
    assert set(uscita["soggetti"]) == {"light.soggiorno_1", "light.soggiorno_2"}
    assert uscita["escluse"]["nascoste"] == 2 and "nota" in uscita


def test_su_una_casa_grande_una_riga_per_soggetto_e_sotto_la_soglia_del_ponte():
    """Spec §9: una casa grande come quella vera. 300 entita', nessun filtro:
    corta, 50 righe, e la risposta resta sotto la soglia del ponte.

    Mutazione ESEGUITA: nella corta, una riga per cambio invece che per
    soggetto -- rossa sulle chiavi."""
    casa = _casa_grande()
    stati = {e["id"]: "on" for e in casa["entita"]}
    query = _q()
    chosen = _scegli(query, casa=casa, stati=stati)
    assert chosen.depth == "corta" and chosen.found == 300
    assert len(chosen.subjects) == 300   # si legge tutto, si impagina dopo
    serie = {s.ident: [_punto(_INIZIO, "off")] + [
        _punto(f"2026-09-29T0{i}:00:00+00:00", "on" if i % 2 else "off")
        for i in range(1, 6)] for s in chosen.subjects}
    uscita = hh.state_rows(query, chosen, serie, truncated=False, acts=[],
                           current=stati)
    assert len(uscita["voci"]) == 50 and uscita["oltre"]["restano"] == 250
    assert set(uscita["voci"][0]) == {"id", "nome", "cambi", "ultimo_cambio", "stato"}
    assert uscita["voci"][0]["cambi"] == 5
    assert len(json.dumps(uscita, ensure_ascii=False)) < BRIDGE_CEILING_CHARS


def test_chi_si_sposta_e_solo_in_casa_o_fuori_in_ogni_profondita():
    """Review Focus 1, spec §5: «Lavoro» -> «Palestra» sono due `not_home`,
    e non sono un cambio da raccontare.

    Mutazione ESEGUITA: applicare `redact_state` DOPO il confronto fra
    punti -- rossa (tre cambi invece di due)."""
    casa = _casa()
    casa["entita"].append(_luce("device_tracker.iphone", None))
    viaggio = [_punto(_INIZIO, "home"), _punto("2026-09-29T08:00:00+00:00", "Lavoro"),
               _punto("2026-09-29T12:00:00+00:00", "Palestra"),
               _punto("2026-09-29T15:00:00+00:00", "home")]
    serie = {"person.marta": viaggio, "device_tracker.iphone": viaggio}
    stati = {**STATI, "device_tracker.iphone": "Palestra"}
    for argomenti in ({"riferimento": "person.marta"},
                      {"area": "senza area", "includi_nascoste": True}):
        query = _q(**argomenti)
        uscita = hh.state_rows(query, _scegli(query, casa=casa, stati=stati), serie,
                               truncated=False, acts=[], current=stati)
        testo = json.dumps(uscita, ensure_ascii=False)
        assert "Lavoro" not in testo and "Palestra" not in testo, argomenti
        suoi = [v for v in uscita["voci"] if v.get("id", "person.marta") == "person.marta"]
        assert [v["stato"] for v in suoi] == ["home", "not_home"], argomenti
    corta = hh.Chosen(12, dict(_NESSUNA), "corta", [hh.Subject("person.marta", "Marta")])
    uscita = hh.state_rows(_q(), corta, serie, truncated=False, acts=[], current=stati)
    assert uscita["voci"][0]["stato"] == "not_home"
    assert "Lavoro" not in json.dumps(uscita, ensure_ascii=False)


def test_senza_registrazioni_non_e_mai_cambiato_non_si_dice():
    """Mutazione ESEGUITA: non scrivere `nessuna_registrazione` -- rossa."""
    query = _q(riferimento="light.soggiorno_1")
    uscita = hh.state_rows(query, _scegli(query), {}, truncated=False, acts=[],
                           current=STATI)
    assert uscita["voci"] == []
    assert uscita["nessuna_registrazione"]["soggetti"] == ["light.soggiorno_1"]


def test_un_elenco_tagliato_da_home_assistant_si_dichiara_nella_finestra():
    """Home Assistant legge al piu' un tetto di cambi e tiene i recenti:
    senza la dichiarazione, la finestra sembrerebbe cominciare piu' tardi
    di quanto si e' chiesto.

    Mutazione ESEGUITA: in `_declare_gaps`, non scrivere `troncata` quando
    `truncated` e' vero -- rossa (KeyError)."""
    query = _q(riferimento="light.soggiorno_1")
    uscita = hh.state_rows(query, _scegli(query), {"light.soggiorno_1": _LUCE_1},
                           truncated=True, acts=[], current=STATI)
    assert "i piu' vecchi della finestra mancano" in uscita["finestra"]["troncata"]


def test_nessun_soggetto_suggerisce_search_ma_non_se_ci_sono_escluse():
    """Mutazione ESEGUITA: scrivere `suggerimento` anche con le escluse -- rossa."""
    vuota = _q(riferimento="light.inesistente")
    uscita = hh.empty_answer(vuota, _scegli(vuota))
    assert uscita["trovate"] == 0 and "search" in uscita["suggerimento"]
    nascosta = _q(riferimento="light.servizio_sala")
    uscita = hh.empty_answer(nascosta, _scegli(nascosta))
    assert uscita["escluse"]["nascoste"] == 1 and "nota" in uscita
    assert "suggerimento" not in uscita


def test_limite_zero_non_legge_nessuno_e_conta():
    """`limite=0` chiede solo il conto: nessun soggetto da leggere a Home
    Assistant, ma `found` resta quello vero.

    Mutazione ESEGUITA: in `choose`, restituire `subjects` anche con
    `limit` 0 nella completa e nella media -- rossa (due soggetti)."""
    chosen = _scegli(_q(tipo="light", limite=0))
    assert chosen.found == 2 and chosen.subjects == []


def test_una_esecuzione_vale_per_una_sola_automazione():
    """Un `run_id` e' di UNA automazione: con due scelte, quale traccia
    leggere non si sa, e si dice invece di sceglierne una a caso.

    Mutazione ESEGUITA: togliere il controllo `len(subjects) != 1` con
    `run_id` -- rossa (ritorna un `Chosen`, non l'errore)."""
    comportamento, specchio = _automazioni(("carta", T_IERI), ("vetro", T_IERI))
    query = _q(genere="esecuzioni", esecuzione="r1")
    risposta = hh.choose(query, House(_casa(), specchio), comportamento, now=T0)
    assert "esecuzione vale per UNA sola automazione" in risposta["errore"]


@pytest.mark.parametrize("quante,profondita", [(1, "completa"), (2, "media"),
                                               (10, "media"), (11, "corta")])
def test_la_profondita_la_decide_lo_strumento(quante, profondita):
    """Spec §3: 1 -> completa, 2-10 -> media, oltre 10 -> corta.

    Mutazione ESEGUITA: `DETAIL_MEDIUM_MAX` letto come 9 -- rossa sul 10."""
    assert hh.depth_for(quante) == profondita


# -- Revisione del Task 3 (30/09/2026) ----------------------------------------


def _sedici_luci():
    """16 luci in soggiorno, nella casa in ordine INVERSO di id: cosi' un
    ordine che seguisse la casa (o lo specchio) si vede."""
    casa = _casa()
    casa["entita"] = [_luce(f"light.l{i:02}", "soggiorno") for i in reversed(range(16))]
    stati = {f"light.l{i:02}": "off" for i in range(16)}
    serie = {f"light.l{i:02}": [_punto(_INIZIO, "off")] for i in range(16)}
    serie["light.l15"] += [_punto(f"2026-09-29T1{i}:00:00+00:00", "on" if i % 2 else "off")
                           for i in range(5, 0, -1)][::-1]
    serie["light.l03"].append(_punto("2026-09-29T09:00:00+00:00", "on"))
    del serie["light.l14"]
    return casa, stati, serie


def test_nella_corta_chi_e_cambiato_nella_finestra_viene_prima():
    """Review Task 3 (#1): 16 luci, `limite=5`, una sola cambiata 5 volte.
    Nella prima forma la pagina si tagliava in `choose` dall'ultimo cambio
    dello specchio, e le 5 mostrate avevano tutte `cambi: 0`.

    Mutazione ESEGUITA: in `state_rows` non ordinare `ranked` (resta
    l'ordine della casa) -- rossa; tagliare la pagina in `choose` sui
    soggetti come prima -- rossa (`subjects` sono 5, non 16)."""
    casa, stati, serie = _sedici_luci()
    query = _q(tipo="light", limite=5)
    chosen = _scegli(query, casa=casa, stati=stati)
    assert chosen.depth == "corta" and len(chosen.subjects) == 16
    uscita = hh.state_rows(query, chosen, serie, truncated=False, acts=[],
                           current=stati)
    assert [v["id"] for v in uscita["voci"]] == [
        "light.l15", "light.l03", "light.l00", "light.l01", "light.l02"]
    assert [v["cambi"] for v in uscita["voci"]] == [5, 1, 0, 0, 0]
    assert uscita["oltre"]["restano"] == 11 and uscita["oltre"]["salta"] == 5


def test_nella_corta_salta_su_una_finestra_fissa_non_salta_ne_ripete():
    """Review Task 3 (#1): scorrendo con `salta` sulla stessa finestra ogni
    soggetto compare una volta sola; a parita' (nessun cambio) decide l'id,
    non l'ordine della casa. E `nessuna_registrazione` nomina solo i
    soggetti della pagina.

    Mutazione ESEGUITA: togliere l'id dalla chiave di `_activity` -- rossa
    (a parita' vince l'ordine inverso della casa); `_declare_gaps` su tutti
    i soggetti invece che sulla pagina -- rossa sulla prima pagina."""
    casa, stati, serie = _sedici_luci()
    visti, pagine = [], []
    for salta in (0, 5, 10, 15):
        query = _q(tipo="light", limite=5, salta=salta)
        uscita = hh.state_rows(query, _scegli(query, casa=casa, stati=stati), serie,
                               truncated=False, acts=[], current=stati)
        visti += [v["id"] for v in uscita["voci"]]
        pagine.append(uscita)
    assert visti == ["light.l15", "light.l03"] + sorted(
        f"light.l{i:02}" for i in range(16) if i not in (3, 15))
    assert "nessuna_registrazione" not in pagine[0]
    assert pagine[3]["nessuna_registrazione"]["soggetti"] == ["light.l14"]


def test_una_finestra_tagliata_dice_da_quando_i_dati_ci_sono_davvero():
    """Review Task 3 (#2), spec §3: `finestra` e' il periodo DAVVERO coperto.
    Home Assistant tiene la coda: se la serie comincia alle 10:00 UTC, prima
    non si sa, e `da` lo dice; la domanda resta in `chiesta_da`.

    Mutazione ESEGUITA: in `_declare_gaps` lasciare `da` alla finestra
    chiesta -- rossa."""
    query = _q(riferimento="light.soggiorno_1")
    coda = _LUCE_1[1:]
    uscita = hh.state_rows(query, _scegli(query), {"light.soggiorno_1": coda},
                           truncated=True, acts=[], current=STATI)
    assert uscita["finestra"]["da"] == "2026-09-29T12:00:00+02:00"
    assert uscita["finestra"]["chiesta_da"] == "2026-09-28T18:40:00+02:00"
    assert "troncata" in uscita["finestra"]
    intera = hh.state_rows(query, _scegli(query), {"light.soggiorno_1": _LUCE_1},
                           truncated=False, acts=[], current=STATI)
    assert "chiesta_da" not in intera["finestra"]


def test_nella_corta_scelta_davvero_chi_si_sposta_resta_in_casa_o_fuori():
    """Review Task 3 (#4): la corta per la strada vera di `choose`, con una
    persona e un device_tracker fra piu' di 10 soggetti, «casa -> Lavoro ->
    Palestra -> casa»: due cambi, nessun nome di zona, nessuna coordinata.

    Mutazione ESEGUITA: `redact_state` DOPO il confronto in `_changes` --
    rossa (tre cambi); nella corta `stato` senza `redact_state` -- rossa
    («Lavoro» nel testo)."""
    casa = _casa()
    casa["entita"] += [_luce("device_tracker.iphone", None)] + [
        _luce(f"light.corridoio_{i}", None) for i in range(10)]
    viaggio = [_punto(_INIZIO, "home"), _punto("2026-09-29T08:00:00+00:00", "Lavoro"),
               _punto("2026-09-29T12:00:00+00:00", "Palestra"),
               _punto("2026-09-29T15:00:00+00:00", "home")]
    stati = {**STATI, "device_tracker.iphone": "Palestra",
             **{f"light.corridoio_{i}": "off" for i in range(10)}}
    query = _q(area="senza area", includi_nascoste=True)
    chosen = _scegli(query, casa=casa, stati=stati)
    assert chosen.depth == "corta"
    uscita = hh.state_rows(query, chosen, {"person.marta": viaggio,
                                           "device_tracker.iphone": viaggio},
                           truncated=False, acts=[], current=stati)
    testo = json.dumps(uscita, ensure_ascii=False)
    for vietato in ("Lavoro", "Palestra", "latitude", "longitude", "45.0"):
        assert vietato not in testo, vietato
    suoi = {v["id"]: v for v in uscita["voci"]
            if v["id"] in ("person.marta", "device_tracker.iphone")}
    assert len(suoi) == 2
    for riga in suoi.values():
        assert riga["cambi"] == 2 and riga["stato"] == "not_home", riga


# --- I valori (Task 4) ---------------------------------------------------

def _valori(query, soggetti, *, dettaglio=None, fasce=None, superfici=None,
            classi=None, unita=None, troncato=False, attributi=None):
    chosen = hh.Chosen(len(soggetti), dict(_NESSUNA), hh.depth_for(len(soggetti)),
                       [hh.Subject(i, i) for i in soggetti])
    return hh.value_rows(query, chosen, detail=dettaglio or {}, bands=fasce or {},
                         truncated=troncato,
                         surfaces=superfici or {i: "dettaglio" for i in soggetti},
                         units=unita or {}, state_classes=classi or {},
                         attributes=attributi or {})


def test_entro_un_giorno_i_cambi_veri_oltre_le_fasce_per_chi_le_ha():
    """Da `historian.choose_surface` (24/08/2026). La soglia e' inclusiva.

    Mutazione ESEGUITA: `<` al posto di `<=` -- rossa sulle 24 ore;
    `bool(state_class)` al posto di `produces_statistics` -- rossa sulla
    banderuola."""
    assert hh.value_surface(_q(genere="valori", ore=24), "measurement") == "dettaglio"
    assert hh.value_surface(_q(genere="valori", ore=48), "measurement") == "oraria"
    assert hh.value_surface(_q(genere="valori", ore=48), None) == "dettaglio"
    assert hh.value_surface(_q(genere="valori", ore=48), "measurement_angle") == "dettaglio"


_TEMPERATURA = {"sensor.temperatura": [
    _punto(_INIZIO, "20.0"), _punto("2026-09-28T22:40:00+00:00", "22.0"),
    _punto("2026-09-29T10:40:00+00:00", "18.0")]}


def test_i_conti_di_una_serie_sono_di_hiris_e_la_media_pesa_il_tempo():
    """Decisione 2: primo, ultimo, minimo, massimo, media, dichiarati. Il 20
    vale 6 ore, il 22 dodici, il 18 sei: la media e' 20,5, non 20.

    Mutazione ESEGUITA: media aritmetica dei punti -- rossa (20,0)."""
    riga = _valori(_q(genere="valori", tipo="sensor"), ["sensor.temperatura"],
                   dettaglio=_TEMPERATURA,
                   classi={"sensor.temperatura": "measurement"},
                   unita={"sensor.temperatura": "°C"})["voci"][0]
    assert (riga["primo"], riga["ultimo"], riga["minimo"], riga["massimo"]) == (
        20.0, 18.0, 18.0, 22.0)
    assert riga["media"] == 20.5
    assert riga["conti"] == "calcolati da HIRIS sulla finestra"
    assert riga["unita"] == "°C"
    assert "consumato" not in riga


def test_un_contatore_che_si_azzera_a_mezzanotte_somma_i_due_giorni():
    """Review Focus 2, la #14: «energia consumata oggi» da ieri. A
    mezzanotte il contatore torna a zero: 5 + 4 + 4,5 = 13,5 -- mai un
    numero negativo, mai il solo ultimo giorno.

    Mutazione ESEGUITA: consumato = ultimo - primo anche per
    `total_increasing` -- rossa (4,5)."""
    energia = {"sensor.energia": [
        _punto("2026-09-27T22:00:00+00:00", "0.0"), _punto("2026-09-28T10:00:00+00:00", "5.0"),
        _punto("2026-09-28T21:59:00+00:00", "9.0"), _punto("2026-09-28T22:00:00+00:00", "0.0"),
        _punto("2026-09-29T12:00:00+00:00", "4.5")]}
    riga = _valori(_q(genere="valori", da="ieri"), ["sensor.energia"], dettaglio=energia,
                   classi={"sensor.energia": "total_increasing"})["voci"][0]
    assert riga["consumato"] == 13.5


def test_le_fasce_di_un_contatore_sommano_il_cambio_di_home_assistant():
    """Il `cambio` di ogni ora e' gia' corretto da Home Assistant per gli
    azzeramenti (misurato il 27/08/2026): si somma, non si ricalcola.

    Mutazione ESEGUITA: consumato = ultimo stato - primo stato -- rossa."""
    fasce = {"sensor.energia": [
        {"inizio": "2026-09-28T22:00:00+00:00", "fine": "2026-09-28T23:00:00+00:00",
         "minimo": None, "massimo": None, "media": None, "stato": 0.4, "cambio": 0.4},
        {"inizio": "2026-09-28T23:00:00+00:00", "fine": "2026-09-29T00:00:00+00:00",
         "minimo": None, "massimo": None, "media": None, "stato": 0.9, "cambio": 0.5},
        {"inizio": "2026-09-29T00:00:00+00:00", "fine": "2026-09-29T01:00:00+00:00",
         "minimo": None, "massimo": None, "media": None, "stato": 0.2, "cambio": 0.2}]}
    uscita = _valori(_q(genere="valori", ore=48), ["sensor.energia"], fasce=fasce,
                     superfici={"sensor.energia": "oraria"},
                     classi={"sensor.energia": "total_increasing"})
    assert uscita["grana"] == "oraria"
    assert uscita["voci"][0]["consumato"] == 1.1
    assert uscita["voci"][0]["punti"][0]["inizio"] == "2026-09-29T00:00:00+02:00"


def test_le_fasce_di_un_contatore_non_hanno_media():
    """Revisione del Task 4 (#5): la media delle letture di fine ora di un
    contatore non dice niente. Primo, ultimo, minimo, massimo e consumato
    si'; la media no.

    Mutazione ESEGUITA: rimettere `media` fra i conti delle fasce di un
    contatore -- rossa."""
    fasce = {"sensor.energia": [
        {"inizio": "2026-09-28T22:00:00+00:00", "stato": 0.4, "cambio": 0.4},
        {"inizio": "2026-09-28T23:00:00+00:00", "stato": 0.9, "cambio": 0.5}]}
    riga = _valori(_q(genere="valori", ore=48), ["sensor.energia"], fasce=fasce,
                   superfici={"sensor.energia": "oraria"},
                   classi={"sensor.energia": "total_increasing"})["voci"][0]
    assert "media" not in riga
    assert (riga["primo"], riga["ultimo"], riga["consumato"]) == (0.4, 0.9, 0.9)
    assert riga["conti"] == hh.COUNTED


@pytest.mark.parametrize("letture,consumato", [
    (["100", "101", "100.5", "102"], 2.0),
    (["5", "-1", "6"], 1.0),
    (["9", "-1", "4.5"], 4.5),
    (["100", "95"], -5.0),
])
def test_il_consumato_di_un_total_increasing_e_quello_di_home_assistant(letture, consumato):
    """Revisione del Task 4 (#1), sul sorgente di Home Assistant
    (`components/sensor/recorder.py`, tag 2026.9.0): azzeramento SOLO sotto
    il 90% del valore di prima (`reset_detected`, 475-493); un calo piu'
    piccolo entra nella somma col suo segno, anche se la fa negativa (818);
    un valore negativo si salta (795-796), non vale zero.

    Mutazione ESEGUITA: ogni calo e' un azzeramento (la prima forma) --
    rossa (103 invece di 2); togliere il salto dei negativi -- rossa
    ([5, -1, 6] da' 6); il negativo portato a zero (`max(0.0, value)`) --
    rossa ([5, -1, 6] da' 6)."""
    ore = [f"2026-09-29T0{i}:00:00+00:00" for i in range(len(letture))]
    serie = {"sensor.energia": [_punto(q, v) for q, v in zip(ore, letture, strict=True)]}
    riga = _valori(_q(genere="valori"), ["sensor.energia"], dettaglio=serie,
                   classi={"sensor.energia": "total_increasing"})["voci"][0]
    assert riga["consumato"] == consumato


def test_un_total_con_last_reset_non_si_conta_dai_punti():
    """Revisione del Task 4 (#2): lo storico e' chiesto senza attributi, e i
    cicli di `last_reset` nei punti non si vedono. Con `last_reset` negli
    attributi di ADESSO il consumato non si calcola e si dice perche'; senza,
    resta ultimo meno primo.

    Mutazione ESEGUITA: ignorare `attributes` (mai `cycles_unseen`) --
    rossa (consumato -6,0 su un ciclo che non si vede)."""
    serie = {"sensor.gas": [_punto(_INIZIO, "8.0"),
                            _punto("2026-09-28T22:00:00+00:00", "0.5"),
                            _punto("2026-09-29T12:00:00+00:00", "2.0")]}
    ciclica = _valori(_q(genere="valori"), ["sensor.gas"], dettaglio=serie,
                      classi={"sensor.gas": "total"},
                      attributi={"sensor.gas": {"values": {
                          "last_reset": "2026-09-28T22:00:00+00:00"}}})["voci"][0]
    assert "consumato" not in ciclica
    assert "24 ore" in ciclica["consumato_non_calcolato"]
    netta = _valori(_q(genere="valori"), ["sensor.gas"], dettaglio=serie,
                    classi={"sensor.gas": "total"})["voci"][0]
    assert netta["consumato"] == -6.0 and "consumato_non_calcolato" not in netta


def test_il_tempo_senza_un_numero_non_pesa_e_si_dice():
    """Revisione del Task 4 (#4): 10 all'inizio, `unavailable` dopo due ore,
    20 dopo ventidue. Ogni punto vale fino al punto dopo, di qualunque stato:
    la media e' (10*2 + 20*2) / 4 = 15, e le 20 ore senza valore si dicono.
    Nella prima forma valevano per il 10: 10,833.

    Mutazione ESEGUITA: togliere dalla linea del tempo i punti non numerici
    -- rossa (10,833)."""
    serie = {"sensor.temperatura": [
        _punto(_INIZIO, "10.0"), _punto("2026-09-28T18:40:00+00:00", "unavailable"),
        _punto("2026-09-29T14:40:00+00:00", "20.0")]}
    riga = _valori(_q(genere="valori"), ["sensor.temperatura"],
                   dettaglio=serie)["voci"][0]
    assert riga["media"] == 15.0
    assert riga["ore_senza_valore"] == 20.0
    intera = _valori(_q(genere="valori"), ["sensor.temperatura"],
                     dettaglio=_TEMPERATURA)["voci"][0]
    assert "ore_senza_valore" not in intera


def test_una_serie_nata_dopo_lo_dice_sulla_sua_riga():
    """Revisione del Task 4 (#3): spostare la finestra di TUTTE per una serie
    nata dopo contraddiceva i conti delle altre, calcolati dall'inizio. Solo
    il taglio di Home Assistant sposta `finestra`; la serie nata dopo porta
    `dal`, e la sua media parte da li': 5 per quattro ore, 7 per due -- 5,667.

    Mutazione ESEGUITA: spostare `finestra` anche senza taglio -- rossa;
    non scrivere `dal` -- rossa."""
    nata = {**_TEMPERATURA, "sensor.energia": [
        _punto("2026-09-29T10:40:00+00:00", "5.0"),
        _punto("2026-09-29T14:40:00+00:00", "7.0")]}
    uscita = _valori(_q(genere="valori"), ["sensor.temperatura", "sensor.energia"],
                     dettaglio=nata)
    assert uscita["finestra"] == {"da": "2026-09-28T18:40:00+02:00",
                                  "a": "2026-09-29T18:40:00+02:00"}
    righe = {v["id"]: v for v in uscita["voci"]}
    assert righe["sensor.energia"]["dal"] == "2026-09-29T12:40:00+02:00"
    assert righe["sensor.energia"]["media"] == 5.667
    assert "dal" not in righe["sensor.temperatura"]
    assert righe["sensor.temperatura"]["media"] == 20.5


def _fascia(inizio: str, fine: str | None, stato: float, cambio: float) -> dict:
    fascia = {"inizio": inizio, "minimo": None, "massimo": None, "media": None,
              "stato": stato, "cambio": cambio}
    if fine is not None:
        fascia["fine"] = fine
    return fascia


def test_le_fasce_orarie_che_finiscono_prima_di_adesso_lo_dicono_con_al():
    """Revisione finale della fetta (I-1, 30/09/2026): Home Assistant legge
    le fasce orarie solo dalle ore gia' COMPILATE (`Statistics`, tag
    2026.9.0), e l'ora in corso non c'e' mai. La #14, «oggi contro ieri»
    (`da="ieri"`), finisce alle 16:00 UTC mentre `finestra.a` dice 16:40: la
    riga porta `al` e il consumato e' quello fino a li'. Una fascia senza
    `fine` vale un'ora dal suo inizio.

    Mutazione ESEGUITA: non scrivere `al` sulla riga -- rossa.
    Mutazione ESEGUITA: `<=` al posto di `<` in `_bands_until` -- rossa
    (la finestra che finisce all'ora piena porta `al` falso)."""
    fasce = {"sensor.energia": [
        _fascia("2026-09-29T14:00:00+00:00", "2026-09-29T15:00:00+00:00", 1.0, 0.5),
        _fascia("2026-09-29T15:00:00+00:00", "2026-09-29T16:00:00+00:00", 1.4, 0.4)]}
    uscita = _valori(_q(genere="valori", da="ieri"), ["sensor.energia"], fasce=fasce,
                     superfici={"sensor.energia": "oraria"},
                     classi={"sensor.energia": "total_increasing"})
    riga = uscita["voci"][0]
    assert uscita["finestra"]["a"] == "2026-09-29T18:40:00+02:00"
    assert riga["al"] == "2026-09-29T18:00:00+02:00"
    assert riga["consumato"] == 0.9
    fasce_mute = {"sensor.energia": [
        _fascia("2026-09-29T15:00:00+00:00", None, 1.4, 0.4)]}
    riga = _valori(_q(genere="valori", da="ieri"), ["sensor.energia"], fasce=fasce_mute,
                   superfici={"sensor.energia": "oraria"},
                   classi={"sensor.energia": "total_increasing"})["voci"][0]
    assert riga["al"] == "2026-09-29T18:00:00+02:00"
    ora_piena = _q(genere="valori", da="2026-09-27T16:00:00+00:00",
                   a="2026-09-29T16:00:00+00:00")
    riga = _valori(ora_piena, ["sensor.energia"], fasce=fasce,
                   superfici={"sensor.energia": "oraria"},
                   classi={"sensor.energia": "total_increasing"})["voci"][0]
    assert "al" not in riga


def _lunga():
    return [_punto(datetime.fromtimestamp(T0 - 86_000 + i * 280, ZoneInfo("UTC"))
                   .isoformat(), str(i)) for i in range(300)]


def test_una_serie_lunga_si_campiona_a_cinquanta_punti_col_primo_e_l_ultimo():
    """Mutazione ESEGUITA: dare tutti i punti -- rossa (300)."""
    riga = _valori(_q(genere="valori"), ["sensor.temperatura"],
                   dettaglio={"sensor.temperatura": _lunga()})["voci"][0]
    assert len(riga["punti"]) == 50
    assert riga["punti"][0]["valore"] == "0" and riga["punti"][-1]["valore"] == "299"
    assert "300 punti" in riga["campione"]
    assert riga["massimo"] == 299.0


def test_la_completa_campiona_ma_i_conti_sono_della_serie_intera():
    """Ruling P3 (30/09/2026): il campione puo' saltare il picco, i conti no.
    Il picco sta all'indice 1, e il campione di 50 su 300 va a passi di 6,1:
    lo salta.

    Mutazione ESEGUITA: conti calcolati sul campione invece che sulla serie
    -- rossa (massimo 299)."""
    lunga = _lunga()
    lunga[1] = _punto(lunga[1]["quando"], "1000")
    riga = _valori(_q(genere="valori"), ["sensor.temperatura"],
                   dettaglio={"sensor.temperatura": lunga})["voci"][0]
    assert "1000" not in [p["valore"] for p in riga["punti"]]
    assert riga["massimo"] == 1000.0
    assert riga["conti"] == hh.COUNTED


def test_una_serie_vuota_non_ha_conti_e_si_dichiara():
    """Spec §9: una serie vuota. Senza registrazioni non c'e' riga (i conti
    di niente sarebbero inventati) e si dice in `nessuna_registrazione`; una
    serie di soli `unavailable` ha la riga ma nessun conto.

    Mutazione ESEGUITA: tenere la riga anche senza punti -- rossa (due id in
    `voci`); `conti` scritto anche senza numeri -- rossa sull'umidita'."""
    uscita = _valori(_q(genere="valori"),
                     ["sensor.temperatura", "sensor.energia", "sensor.umidita"],
                     dettaglio={**_TEMPERATURA,
                                "sensor.umidita": [_punto(_INIZIO, "unavailable")]})
    assert [v["id"] for v in uscita["voci"]] == ["sensor.temperatura", "sensor.umidita"]
    assert uscita["nessuna_registrazione"]["soggetti"] == ["sensor.energia"]
    umidita = uscita["voci"][1]
    assert "conti" not in umidita and "media" not in umidita


def test_superfici_diverse_si_dichiarano_serie_per_serie():
    """Due grane nella stessa risposta: `grana` in cima dice «per serie», e
    ogni riga la sua.

    Mutazione ESEGUITA: la grana solo in cima, dalla prima serie -- rossa."""
    fasce = {"sensor.energia": [{"inizio": "2026-09-28T22:00:00+00:00",
                                 "fine": "2026-09-28T23:00:00+00:00", "minimo": 1.0,
                                 "massimo": 2.0, "media": 1.5}]}
    uscita = _valori(_q(genere="valori", ore=48), ["sensor.temperatura", "sensor.energia"],
                     dettaglio=_TEMPERATURA, fasce=fasce,
                     superfici={"sensor.temperatura": "dettaglio",
                                "sensor.energia": "oraria"})
    assert uscita["grana"] == "per serie"
    assert {v["id"]: v["grana"] for v in uscita["voci"]} == {
        "sensor.temperatura": "dettaglio", "sensor.energia": "oraria"}


def test_una_fascia_con_un_inizio_illeggibile_e_un_guasto_non_un_vuoto():
    """Da F1 dell'onda finale di `trend` (25/08/2026).

    Mutazione ESEGUITA: togliere il controllo degli inizi illeggibili --
    rossa (la riga ha i conti e nessun `errore`)."""
    fasce = {"sensor.energia": [{"inizio": {"non": "un istante"}, "media": 1.0}]}
    riga = _valori(_q(genere="valori", ore=48), ["sensor.energia"], fasce=fasce,
                   superfici={"sensor.energia": "oraria"})["voci"][0]
    assert "non le leggo" in riga["errore"]


@pytest.mark.parametrize("ident", ["person.marta", "device_tracker.iphone"])
def test_i_valori_di_chi_si_sposta_non_dicono_la_zona(ident):
    """Review Focus 1 sui valori: la serie di una persona e' fatta di zone.

    Mutazione ESEGUITA: non passare i punti da `redact_state` -- rossa."""
    viaggio = {ident: [_punto(_INIZIO, "home"),
                       _punto("2026-09-29T08:00:00+00:00", "Lavoro")]}
    uscita = _valori(_q(genere="valori"), [ident], dettaglio=viaggio)
    assert "Lavoro" not in json.dumps(uscita, ensure_ascii=False)
    assert uscita["voci"][0]["punti"][1]["valore"] == "not_home"


def _dodici_sensori():
    """12 sensori, nella chiamata in ordine INVERSO di id: s07 cambia per
    ultimo, s02 prima, gli altri mai, s11 non ha registrazioni."""
    soggetti = [f"sensor.s{i:02}" for i in reversed(range(12))]
    serie = {f"sensor.s{i:02}": [_punto(_INIZIO, "1.0")] for i in range(11)}
    serie["sensor.s07"].append(_punto("2026-09-29T15:00:00+00:00", "2.0"))
    serie["sensor.s02"].append(_punto("2026-09-29T09:00:00+00:00", "3.0"))
    return soggetti, serie


def test_i_valori_si_impaginano_dopo_la_lettura_dal_piu_attivo():
    """Il contratto del Task 3 anche per i valori: si leggono tutte le serie,
    si ordinano per cio' che e' successo NELLA finestra, poi si impagina; chi
    non ha registrazioni si nomina nella sua pagina.

    Mutazione ESEGUITA: non ordinare le righe (resta l'ordine della
    chiamata) -- rossa; `nessuna_registrazione` su tutte le serie invece che
    sulla pagina -- rossa sulla prima pagina."""
    soggetti, serie = _dodici_sensori()
    prima = _valori(_q(genere="valori", limite=3), soggetti, dettaglio=serie)
    assert prima["profondita"] == "corta"
    assert [v["id"] for v in prima["voci"]] == ["sensor.s07", "sensor.s02", "sensor.s00"]
    assert prima["oltre"]["restano"] == 9 and prima["oltre"]["salta"] == 3
    assert "nessuna_registrazione" not in prima
    ultima = _valori(_q(genere="valori", limite=3, salta=9), soggetti, dettaglio=serie)
    assert [v["id"] for v in ultima["voci"]] == ["sensor.s09", "sensor.s10"]
    assert ultima["nessuna_registrazione"]["soggetti"] == ["sensor.s11"]
    assert "oltre" not in ultima
    media = _valori(_q(genere="valori"), ["sensor.s00", "sensor.s07"], dettaglio=serie)
    assert [v["id"] for v in media["voci"]] == ["sensor.s07", "sensor.s00"]


def test_una_serie_tagliata_dice_da_quando_la_risposta_e_intera():
    """`finestra` coi dati tagliati da Home Assistant (`_covered_since`, la
    stessa degli stati): `da` e' dove TUTTE le serie mostrate hanno i loro
    dati -- il piu' tardo dei primi punti --, la domanda in `chiesta_da`.

    Mutazione ESEGUITA: il piu' presto dei primi punti invece del piu'
    tardo -- rossa; non spostare `da` quando e' troncata -- rossa."""
    tagliata = {**_TEMPERATURA,
                "sensor.energia": [_punto("2026-09-29T10:40:00+00:00", "1.0")]}
    uscita = _valori(_q(genere="valori"), ["sensor.temperatura", "sensor.energia"],
                     dettaglio=tagliata, troncato=True)
    assert uscita["finestra"]["da"] == "2026-09-29T12:40:00+02:00"
    assert uscita["finestra"]["chiesta_da"] == "2026-09-28T18:40:00+02:00"
    assert "troncata" in uscita["finestra"]
    # Tagliata di mezz'ora: dentro lo scarto di un'ora, ma il taglio si dice.
    poco = {"sensor.temperatura": [_punto("2026-09-28T17:10:00+00:00", "20.0")]}
    mezz_ora = _valori(_q(genere="valori"), ["sensor.temperatura"], dettaglio=poco,
                       troncato=True)
    assert mezz_ora["finestra"]["da"] == "2026-09-28T19:10:00+02:00"
    intera = _valori(_q(genere="valori"), ["sensor.temperatura"], dettaglio=_TEMPERATURA)
    assert intera["finestra"] == {"da": "2026-09-28T18:40:00+02:00",
                                  "a": "2026-09-29T18:40:00+02:00"}


def _fa(ore):
    return datetime.fromtimestamp(T0 - ore * 3600, ZoneInfo("UTC")).isoformat()


def _traccia(run_id, ore, esito="finished", **altro):
    """Una riga di `trace/list`, nella forma di Home Assistant."""
    return {"run_id": run_id, "timestamp": {"start": _fa(ore)},
            "script_execution": esito, "last_step": "action/0", **altro}


def _esecuzioni(soggetti, query=None, **argomenti):
    chosen = hh.Chosen(len(soggetti), dict(_NESSUNA), hh.depth_for(len(soggetti)),
                       [hh.Subject(i, i.split(".")[1], _fa(1)) for i in soggetti])
    return hh.run_rows(query or _q(genere="esecuzioni"), chosen, **argomenti)


def test_una_automazione_da_le_sue_esecuzioni_nella_finestra():
    """Spec §3, completa: com'e' finita, l'ultimo passo, il guasto. Il guasto
    dell'esecuzione si chiama `guasto`: `errore` e' la chiave con cui lo
    strumento dice che non ha potuto rispondere.

    Mutazione ESEGUITA: non filtrare per finestra -- rossa (tre righe);
    `row["errore"]` al posto di `row["guasto"]` -- rossa."""
    tracce = {"automation.1001": [_traccia("r3", 1), _traccia("r2", 5, "error",
                                                              error="timeout"),
                                  _traccia("r1", 30)]}
    uscita = _esecuzioni(["automation.carta"], traces=tracce,
                         keys={"automation.carta": "automation.1001"}, unread={})
    assert uscita["profondita"] == "completa"
    assert uscita["voci"] == [
        {"esecuzione": "r3", "inizio": "2026-09-29T17:40:00+02:00",
         "esito": "finished", "ultimo_passo": "action/0"},
        {"esecuzione": "r2", "inizio": "2026-09-29T13:40:00+02:00",
         "esito": "error", "ultimo_passo": "action/0", "guasto": "timeout"}]
    assert uscita["soggetto"] == {"id": "automation.carta", "nome": "carta",
                                  "ultima_esecuzione": "2026-09-29T17:40:00+02:00"}
    assert "non_letti" not in uscita and "oltre" not in uscita


def test_cinque_automazioni_danno_le_ultime_tre_ciascuna():
    """La #26: «perche' sono partite le automazioni dei rifiuti». Per
    automazione le ultime tre, raggruppate, dall'automazione partita piu' di
    recente nella finestra. Tutte le tracce sono dentro la finestra: prima
    della piu' vecchia Home Assistant puo' averne scartate, e `dal` lo dice.

    Mutazione ESEGUITA: `RECENT_RUNS = 5` -- rossa (25 righe); ordinare le
    righe per istante invece che per automazione -- rossa (si mescolano);
    `dal` mai dichiarato -- rossa."""
    nomi = [f"automation.rifiuto_{n}" for n in range(5)]
    tracce = {f"automation.10{n}": [_traccia(f"r{n}{k}", 5 - n + k) for k in range(5)]
              for n in range(5)}
    uscita = _esecuzioni(nomi, traces=tracce,
                         keys={f"automation.rifiuto_{n}": f"automation.10{n}"
                               for n in range(5)}, unread={})
    assert uscita["profondita"] == "media" and len(uscita["voci"]) == 15
    assert set(uscita["soggetti"]) == set(nomi)
    assert [v["id"] for v in uscita["voci"]] == [
        f"automation.rifiuto_{n}" for n in (4, 3, 2, 1, 0) for _ in range(3)]
    assert [v["esecuzione"] for v in uscita["voci"][:3]] == ["r40", "r41", "r42"]
    assert uscita["dal"]["automation.rifiuto_4"] == datetime.fromtimestamp(
        T0 - 5 * 3600, ZoneInfo(ROMA)).isoformat()
    assert "conservate" in uscita


def test_molte_automazioni_una_riga_ciascuna_con_le_partenze_conservate():
    """Mutazione ESEGUITA: `partenze_conservate` contate fuori finestra -- rossa."""
    nomi = [f"automation.a{n}" for n in range(12)]
    tracce = {f"automation.{n}": [_traccia("x", 2), _traccia("y", 40)] for n in range(12)}
    uscita = _esecuzioni(nomi, traces=tracce,
                         keys={f"automation.a{n}": f"automation.{n}" for n in range(12)},
                         unread={})
    assert uscita["profondita"] == "corta" and len(uscita["voci"]) == 12
    assert uscita["voci"][0]["partenze_conservate"] == 1
    assert uscita["voci"][0]["esito_ultima"] == "finished"
    assert "dal" not in uscita["voci"][0] and "conservate" not in uscita


def _dodici_automazioni():
    nomi = [f"automation.a{n:02}" for n in range(12)]
    tracce = {f"automation.k{n:02}": [_traccia("r", 10), _traccia("v", 30)]
              for n in range(12)}
    tracce["automation.k05"] = [_traccia("r", 1), _traccia("v", 30)]
    tracce["automation.k02"] = [_traccia("r", 3)]
    tracce["automation.k07"] = [_traccia("r", 3), _traccia("v", 50)]
    tracce["automation.k09"] = [_traccia("v", 40)]
    chiavi = {n: f"automation.k{n[-2:]}" for n in nomi}
    chiavi["automation.a11"] = None
    return nomi, tracce, chiavi


def test_nella_corta_le_automazioni_partite_di_recente_vengono_prima():
    """Il contratto degli stati (revisione del Task 3): si leggono tutte, si
    ordinano per l'ultima esecuzione NELLA finestra, a parita' l'id, e poi si
    impagina. Chi non e' partita nella finestra sta in fondo; chi non si e'
    potuta leggere si nomina in `non_letti` nella SUA pagina.

    Mutazione ESEGUITA: non ordinare le righe della corta -- rossa; nominare
    in `non_letti` tutte le non lette invece di quelle della pagina -- rossa
    sulla prima pagina; `dal` mai dichiarato -- rossa."""
    nomi, tracce, chiavi = _dodici_automazioni()
    pagine = [_esecuzioni(nomi, _q(genere="esecuzioni", limite=5, salta=salta),
                          traces=tracce, keys=chiavi, unread={})
              for salta in (0, 5, 10)]
    visti = [v["id"] for p in pagine for v in p["voci"]]
    assert visti == ["automation.a05", "automation.a02", "automation.a07",
                     "automation.a00", "automation.a01", "automation.a03",
                     "automation.a04", "automation.a06", "automation.a08",
                     "automation.a10", "automation.a09"]
    assert pagine[0]["oltre"]["restano"] == 7 and pagine[0]["oltre"]["salta"] == 5
    assert "non_letti" not in pagine[0]
    assert list(pagine[2]["non_letti"]) == ["automation.a11"]
    righe = {v["id"]: v for p in pagine for v in p["voci"]}
    assert righe["automation.a09"]["partenze_conservate"] == 0
    assert "esito_ultima" not in righe["automation.a09"]
    # a02 ha una sola traccia, dentro la finestra: prima, non si sa.
    assert righe["automation.a02"]["dal"] == datetime.fromtimestamp(
        T0 - 3 * 3600, ZoneInfo(ROMA)).isoformat()
    assert "dal" not in righe["automation.a07"] and "dal" not in righe["automation.a09"]


def test_chi_non_si_legge_e_nominato_e_gli_altri_rispondono():
    """Review Focus 4: fra cinque automazioni dei rifiuti, una scritta in
    YAML senza `id:` non spegne le altre quattro, e non e' «mai partita».
    Una che Home Assistant rifiuta porta il SUO motivo.

    Mutazione ESEGUITA: tornare `errore` alla prima chiave irrisolta --
    rossa; saltare in silenzio la chiave irrisolta -- rossa (`non_letti`)."""
    nomi = ["automation.carta", "automation.plastica", "automation.a_mano",
            "automation.umido", "automation.vetro"]
    chiavi = {"automation.carta": "automation.1", "automation.plastica": "automation.2",
              "automation.a_mano": None, "automation.umido": "automation.4",
              "automation.vetro": "automation.5"}
    tracce = {f"automation.{n}": [_traccia(f"r{n}", n)] for n in (1, 2, 4, 5)}
    uscita = _esecuzioni(nomi, traces=tracce, keys=chiavi, unread={})
    assert [v["id"] for v in uscita["voci"]] == [
        "automation.carta", "automation.plastica", "automation.umido",
        "automation.vetro"]
    assert list(uscita["non_letti"]) == ["automation.a_mano"]
    assert "Non vuol dire che non sia mai partita" in uscita["non_letti"]["automation.a_mano"]
    assert "errore" not in uscita
    rifiutata = _esecuzioni(nomi, traces=tracce, keys=chiavi,
                            unread={"automation.5": "non trovato"})
    assert rifiutata["non_letti"]["automation.vetro"] == "non trovato"
    assert "automation.vetro" not in [v["id"] for v in rifiutata["voci"]]


def test_l_innesco_di_chi_si_sposta_non_dice_dove_era_ne_dove_va():
    """Review Focus 1 sulle tracce: l'innesco di una persona che si sposta,
    ripetuto nei passi, perde zone e coordinate. (Nome corretto nella
    revisione del Task 5, M4: il «chi l'ha accesa» -- `context.user_id` --
    non e' una posizione, resta e questa prova non lo guarda.)

    Mutazione ESEGUITA: `run_detail` senza `redact_nested` -- rossa."""
    chosen = hh.Chosen(1, dict(_NESSUNA), "completa", [hh.Subject("automation.x", "X")])
    marta = {"entity_id": "person.marta", "state": "Palestra",
             "attributes": {"latitude": 45.1, "longitude": 9.2}}
    traccia = {"run_id": "r1", "trace": {"trigger/0": [{"changed_variables": {
        "trigger": {"from_state": {**marta, "state": "Lavoro"}, "to_state": marta}}}]}}
    uscita = hh.run_detail(_q(genere="esecuzioni", esecuzione="r1"), chosen, traccia)
    testo = json.dumps(uscita, ensure_ascii=False)
    for dove in ("Lavoro", "Palestra", "latitude", "longitude"):
        assert dove not in testo, dove
    assert uscita["soggetto"]["id"] == "automation.x"
    assert uscita["voci"][0]["run_id"] == "r1"


def _risultato(stato, voluto):
    """Un elemento di traccia di una condizione `state`, nella forma di Home
    Assistant 2026.9.0 (`condition_trace_set_result(is_state, state=value,
    wanted_state=state_value)`): NESSUN `entity_id`."""
    return [{"path": "x", "timestamp": _fa(1),
             "result": {"result": stato == voluto, "state": stato,
                        "wanted_state": voluto}}]


def _esecuzione_intera(traccia):
    chosen = hh.Chosen(1, dict(_NESSUNA), "completa", [hh.Subject("automation.x", "X")])
    return hh.run_detail(_q(genere="esecuzioni", esecuzione="r1"), chosen, traccia)


def test_una_condizione_su_chi_si_sposta_non_dice_la_zona():
    """Review Task 5, I1: una condizione `state` su `person.marta` registrava
    lo stato vivo, «Palestra», senza `entity_id`: `redact_nested` non lo
    vedeva. Di chi sia lo dice la configurazione allo stesso percorso --
    una condizione in cima (chiavi al plurale), dentro un `and` con un
    elenco di entita', dentro un `if` di un'azione. La luce resta com'e'.

    Mutazione ESEGUITA: `run_detail` senza `_redact_condition_results` --
    rossa; `_config_at` che non salta il nome ripetuto dell'elenco
    (`if/condition/0`) -- rossa sul ramo `if` della luce (il ripiego la
    riduce)."""
    traccia = {"run_id": "r1", "config": {
        "triggers": [{"trigger": "zone", "entity_id": "person.marta",
                      "zone": "zone.palestra", "event": "enter"}],
        "conditions": [
            {"condition": "state", "entity_id": "person.marta", "state": "Palestra"},
            {"condition": "and", "conditions": [
                {"condition": "state", "entity_id": ["light.sala", "person.luca"],
                 "state": "on"}]}],
        "actions": [{"if": [{"condition": "state", "entity_id": "device_tracker.iphone",
                             "state": "Lavoro"}], "then": []},
                    {"if": [{"condition": "state", "entity_id": "light.cucina",
                             "state": "on"}], "then": []}]},
        "trace": {
            "condition/0/entity_id/0": _risultato("Palestra", "Palestra"),
            "condition/1/conditions/0/entity_id/0": _risultato("on", "on"),
            "condition/1/conditions/0/entity_id/1": _risultato("Lavoro", "home"),
            "action/0/if/condition/0/entity_id/0": _risultato("Lavoro", "Lavoro"),
            "action/1/if/condition/0/entity_id/0": _risultato("on", "on")}}
    passi = _esecuzione_intera(traccia)["voci"][0]["trace"]

    def stati(percorso):
        risultato = passi[percorso][0]["result"]
        return risultato["state"], risultato["wanted_state"]
    assert stati("condition/0/entity_id/0") == ("not_home", "not_home")
    assert stati("condition/1/conditions/0/entity_id/0") == ("on", "on")
    assert stati("condition/1/conditions/0/entity_id/1") == ("not_home", "home")
    assert stati("action/0/if/condition/0/entity_id/0") == ("not_home", "not_home")
    # Ritrovata la luce, non il ripiego su chi si sposta nella configurazione.
    assert stati("action/1/if/condition/0/entity_id/0") == ("on", "on")
    # La zona configurata nell'innesco resta: e' configurazione.
    assert _esecuzione_intera(traccia)["voci"][0]["config"]["triggers"][0]["zone"] == \
        "zone.palestra"


def test_una_condizione_che_non_si_ritrova_nella_configurazione_si_riduce():
    """Un percorso che la configurazione non spiega non passa grezzo: se la
    configurazione nomina qualcuno che si sposta, lo stato si riduce.

    Mutazione ESEGUITA: senza il ripiego su `_moving_in` (`owners` vuoti ->
    nessuno) -- rossa."""
    traccia = {"run_id": "r1",
               "config": {"condition": [{"condition": "state",
                                         "entity_id": "person.marta", "state": "home"}]},
               "trace": {"condition/7/entity_id/0": _risultato("Lavoro", "home")}}
    risultato = _esecuzione_intera(traccia)["voci"][0]["trace"]["condition/7/entity_id/0"]
    assert risultato[0]["result"]["state"] == "not_home"
    senza = {"run_id": "r1", "config": {"condition": [{"condition": "state",
                                                        "entity_id": "light.sala"}]},
             "trace": {"condition/7/entity_id/0": _risultato("on", "on")}}
    assert _esecuzione_intera(senza)["voci"][0]["trace"]["condition/7/entity_id/0"][0][
        "result"]["state"] == "on"


def test_ogni_pagina_della_corta_conta_le_non_lette():
    """Review Task 5, I3: i nomi delle non lette stanno sulla loro pagina, e
    la prima si leggeva «lette tutte». Il conto esce su OGNI pagina.

    Mutazione ESEGUITA: contare le non lette della pagina invece di tutte --
    rossa."""
    nomi, tracce, chiavi = _dodici_automazioni()
    chiavi["automation.a04"] = None
    prima = _esecuzioni(nomi, _q(genere="esecuzioni", limite=5), traces=tracce,
                        keys=chiavi, unread={})
    assert prima["non_lette_in_tutto"] == 2 and "non_letti" not in prima
    # Chi non si legge sta in fondo coi mai partiti, per id: a04 sulla
    # seconda pagina, a11 sulla terza -- ognuna col suo nome e col conto.
    for salta, nominate in ((5, ["automation.a04"]), (10, ["automation.a11"])):
        pagina = _esecuzioni(nomi, _q(genere="esecuzioni", limite=5, salta=salta),
                             traces=tracce, keys=chiavi, unread={})
        assert pagina["non_lette_in_tutto"] == 2
        assert list(pagina["non_letti"]) == nominate


def test_il_dal_della_media_e_di_chi_ha_righe_nella_pagina():
    """Review Task 5, M1.

    Mutazione ESEGUITA: `dal` della media non filtrato sulla pagina -- rossa."""
    nomi = [f"automation.rifiuto_{n}" for n in range(5)]
    tracce = {f"automation.10{n}": [_traccia(f"r{n}{k}", 5 - n + k) for k in range(5)]
              for n in range(5)}
    uscita = _esecuzioni(nomi, _q(genere="esecuzioni", limite=3), traces=tracce,
                         keys={f"automation.rifiuto_{n}": f"automation.10{n}"
                               for n in range(5)}, unread={})
    assert {v["id"] for v in uscita["voci"]} == {"automation.rifiuto_4"}
    assert list(uscita["dal"]) == ["automation.rifiuto_4"]


def test_l_esito_dice_di_quando_se_non_e_l_ultima_esecuzione_dello_specchio():
    """Review Task 5, M3: `ultima_esecuzione` e' dello specchio, `esito_ultima`
    della traccia conservata piu' recente. Quando sono due esecuzioni, la
    riga dice di quando e' l'esito.

    Mutazione ESEGUITA: non scrivere mai `esito_ultima_del` -- rossa."""
    nomi, tracce, chiavi = _dodici_automazioni()
    righe = {v["id"]: v for v in _esecuzioni(nomi, traces=tracce, keys=chiavi,
                                             unread={})["voci"]}
    assert "esito_ultima_del" not in righe["automation.a05"]
    assert righe["automation.a02"]["esito_ultima_del"] == datetime.fromtimestamp(
        T0 - 3 * 3600, ZoneInfo(ROMA)).isoformat()


_REGISTRO = [
    {"name": "homeassistant.components.zha.core", "level": "ERROR",
     "message": ["prima", "zigbee giu'"], "source": ["homeassistant/components/zha/core.py", 10],
     "timestamp": T0 - 600, "first_occurred": T0 - 7200, "count": 12,
     "exception": "Traceback (most recent call last):\n  File x\nValueError: boom"},
    {"name": "custom_components.meteo.sensor", "level": "WARNING", "message": ["lento"],
     "source": ["custom_components/meteo/sensor.py", 3], "timestamp": T0 - 60,
     "first_occurred": T0 - 60, "count": 1},
    {"name": "homeassistant.components.zha.core", "level": "ERROR", "message": ["vecchio"],
     "source": ["x.py", 1], "timestamp": T0 - 3 * 86400, "first_occurred": T0 - 3 * 86400,
     "count": 1},
    {"name": "homeassistant.core", "level": "CRITICAL", "message": "senza istante"},
]


def test_gli_errori_una_riga_per_voce_nella_finestra_dalla_piu_recente():
    """Spec §3: livello, messaggio accorciato, fonte, count, prima e ultima.
    `count: 12` e' una voce, non dodici. Dall'ultima volta piu' recente; la
    voce senza istante leggibile non si scarta (non si sa se e' fuori) e sta
    in fondo.

    Mutazione ESEGUITA: non filtrare per finestra -- rossa (quattro voci);
    non ordinare per l'ultima volta -- rossa (zha prima di meteo)."""
    uscita = hh.error_rows(_q(genere="errori"), _REGISTRO)
    assert uscita["trovate"] == 3 and uscita["profondita"] == "corta"
    assert [v["messaggio"] for v in uscita["voci"]] == [
        "lento", "zigbee giu'", "senza istante"]
    assert uscita["voci"][1] == {"livello": "ERROR", "messaggio": "zigbee giu'",
                                 "fonte": "homeassistant/components/zha/core.py:10",
                                 "integrazione": "zha", "count": 12,
                                 "prima": "2026-09-29T16:40:00+02:00",
                                 "ultima": "2026-09-29T18:30:00+02:00",
                                 "eccezione": "ValueError: boom"}
    assert uscita["finestra"] == {"da": "2026-09-28T18:40:00+02:00",
                                  "a": "2026-09-29T18:40:00+02:00"}


def test_gli_errori_si_filtrano_per_livello_e_integrazione():
    """`integrazione` si legge dal nome del logger, anche di un componente
    di terze parti (`custom_components.<nome>`).

    Mutazione ESEGUITA: ignorare `livello` -- rossa; ignorare
    `integrazione` -- rossa; il nome leggibile di `integration_of` al posto
    dell'identificativo (`found[0]`) -- rossa (giro di correzioni: la
    lettura propria del logger e' uscita, era un doppione)."""
    assert [v["messaggio"] for v in hh.error_rows(
        _q(genere="errori", livello="WARNING"), _REGISTRO)["voci"]] == ["lento"]
    assert [v["messaggio"] for v in hh.error_rows(
        _q(genere="errori", integrazione="meteo"), _REGISTRO)["voci"]] == ["lento"]
    assert [v["messaggio"] for v in hh.error_rows(
        _q(genere="errori", integrazione="zha"), _REGISTRO)["voci"]] == ["zigbee giu'"]


def test_salta_su_un_registro_senza_voci_non_promette_voci():
    """Revisione finale della fetta (M-2, 30/09/2026): nessuna voce del
    filtro e `salta=5` davano «le righe si leggono da salta=0», e non ce
    n'e' nessuna. La pagina vuota dice il vero: niente `oltre`.

    Mutazione ESEGUITA: togliere la guardia `> 0` sulle righe in
    `house_query.page_rows` -- rossa (`oltre` con `disponibili: 0`)."""
    uscita = hh.error_rows(_q(genere="errori", integrazione="nessuna", salta=5), _REGISTRO)
    assert uscita["trovate"] == 0 and uscita["voci"] == []
    assert "oltre" not in uscita


def test_un_messaggio_lungo_si_accorcia_e_l_eccezione_e_la_sua_ultima_riga():
    """Spec §3, «messaggio accorciato»; l'eccezione e' l'ultima riga (il
    «cosa»), poi accorciata -- in quest'ordine.

    Mutazione ESEGUITA: `_short` che non taglia -- rossa; accorciare
    l'eccezione PRIMA di prenderne l'ultima riga -- rossa (299 caratteri
    diventano meno)."""
    lungo = [{"level": "ERROR", "message": "x" * 1000, "timestamp": T0 - 1,
              "exception": "Traceback\n  File y\nValueError: " + "z" * 1000}]
    riga = hh.error_rows(_q(genere="errori"), lungo)["voci"][0]
    assert len(riga["messaggio"]) == hh.MESSAGE_MAX and riga["messaggio"].endswith("…")
    assert len(riga["eccezione"]) == hh.MESSAGE_MAX
    assert riga["eccezione"].startswith("ValueError: zzz")


def test_gli_errori_si_impaginano_con_oltre():
    """La pagina e `oltre` di `search` (`_page`, `_oltre`), anche oltre la fine.

    Mutazione ESEGUITA: `voci` senza `_page` -- rossa."""
    prima = hh.error_rows(_q(genere="errori", limite=1), _REGISTRO)
    assert [v["messaggio"] for v in prima["voci"]] == ["lento"]
    assert prima["oltre"]["restano"] == 2 and prima["oltre"]["salta"] == 1
    assert "consiglio" in prima["oltre"]
    fuori = hh.error_rows(_q(genere="errori", salta=9), _REGISTRO)
    assert fuori["voci"] == [] and fuori["oltre"]["disponibili"] == 3


def test_un_registro_che_non_copre_la_finestra_lo_dice():
    """Review Task 5, I2: il registro e' una coda limitata. Se la voce piu'
    vecchia CONSERVATA -- prima dei filtri -- e' dentro la finestra, `da` si
    sposta li' con `troncata`. Se ce n'e' una di prima (come in `_REGISTRO`),
    la finestra e' intera.

    Mutazione ESEGUITA: non spostare `da` -- rossa; prendere la piu' vecchia
    DOPO il filtro del livello -- rossa (`da` diventa quella del WARNING)."""
    corto = [voce for voce in _REGISTRO if voce.get("timestamp") != T0 - 3 * 86400]
    uscita = hh.error_rows(_q(genere="errori", ore=168, livello="WARNING"), corto)
    assert uscita["finestra"]["da"] == datetime.fromtimestamp(
        T0 - 600, ZoneInfo(ROMA)).isoformat()
    assert uscita["finestra"]["chiesta_da"] == datetime.fromtimestamp(
        T0 - 168 * 3600, ZoneInfo(ROMA)).isoformat()
    assert "riavvio" in uscita["finestra"]["troncata"]
    intero = hh.error_rows(_q(genere="errori"), _REGISTRO)
    assert "troncata" not in intero["finestra"]


def test_a_parita_di_istante_decide_anche_il_livello():
    """Review Task 5, M2: due voci nello stesso istante, stessa fonte e stesso
    messaggio, livelli diversi: l'ordine non dipende da come arrivano.

    Mutazione ESEGUITA: togliere il livello dalla chiave di `_activity` --
    rossa."""
    gemelle = [{"level": livello, "message": "uguale", "source": ["a.py", 1],
                "timestamp": T0 - 5} for livello in ("WARNING", "ERROR")]
    assert [v["livello"] for v in hh.error_rows(_q(genere="errori"), gemelle)["voci"]] \
        == ["ERROR", "WARNING"]


def test_le_librerie_di_un_integrazione_si_dichiarano_col_filtro():
    """Review Task 5, M5: `zigpy` scrive per zha col suo nome. La lettura del
    logger e' quella del primo piano (`mind.report.integration_of`), che
    nessuna tabella libreria -> integrazione completa: il filtro non le vede,
    e la risposta lo dice.

    Mutazione ESEGUITA: non scrivere `nota_integrazione` -- rossa."""
    voci = [*_REGISTRO, {"name": "zigpy.application", "level": "ERROR",
                         "message": ["radio giu'"], "timestamp": T0 - 30}]
    tutte = hh.error_rows(_q(genere="errori"), voci)
    assert tutte["voci"][0]["integrazione"] == "zigpy"
    assert "nota_integrazione" not in tutte
    zha = hh.error_rows(_q(genere="errori", integrazione="zha"), voci)
    assert [v["messaggio"] for v in zha["voci"]] == ["zigbee giu'"]
    assert "zigpy" in zha["nota_integrazione"]
