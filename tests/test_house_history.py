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
    chosen = hh.choose(query, casa or _casa(), list(comportamento),
                       _specchio(stati or STATI), now=T0)
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


def _atto(ident, entita, ritardo, quando="2026-09-29T10:00:00+00:00"):
    base = datetime.fromisoformat(quando).timestamp()
    return {"id": ident, "entita": [entita], "quando_ts": base + ritardo,
            "origine": "chat", "servizio": "light.turn_on"}


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
    risposta = hh.choose(query, _casa(), comportamento, specchio, now=T0)
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
