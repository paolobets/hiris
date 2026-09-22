"""Il turno dell'analista (spec §10): il modello sceglie, il codice calcola.

**La scelta che regge tutto**: il modello indica QUALE misura, e non scrive il
numero. Valore, copertura, scostamento e base ce li attacca il codice, dalla
serie. Cosi' un numero inventato dentro un rapporto che sembra autorevole e'
**impossibile** -- ed e' «il codice calcola, il modello sceglie» preso alla
lettera, non come slogan.
"""
from hiris.app.mind import analyst_turn as at


def _serie():
    return {
        "giorni": ["2026-09-12", "2026-09-13", "2026-09-14"],
        "obiettivi": [{"dal": "2026-09-12", "al": "2026-09-14",
                       "testo": "spendere meno", "scritto_ts": 1.0}],
        "serie": [
            {"soggetto": "dev1", "nome": "Inverter", "misura": "prelievo",
             "chiave": None, "operazione": "somma_periodo", "unita": "kWh",
             "valori": [0.3, 0.3, 0.74], "coperture": [1.0, 1.0, 1.0],
             "perche": [],
             "scostamento": {"ultimo": 0.74, "mediana": 0.3, "scarto": 0.0,
                             "quanti_scarti": 2.75, "base": 2}},
            {"soggetto": "dev2", "nome": "Sala", "misura": "co2",
             "chiave": "massimo", "operazione": "media_min_max", "unita": "ppm",
             "valori": [700.0, 710.0, 705.0], "coperture": [1.0, 1.0, 1.0],
             "perche": [],
             "scostamento": {"ultimo": 705.0, "mediana": 705.0, "scarto": 5.0,
                             "quanti_scarti": 0.0, "base": 2}},
        ],
    }


def _risposta(osservazioni):
    import json
    return json.dumps({"osservazioni": osservazioni}, ensure_ascii=False)


def _osservazione(**extra):
    base = {"quale": 0,
            "innesco": 1, "cosa": "il prelievo dalla rete e' salito",
            "spiegato": None,
            "cosa_cambierebbe": "meno prelievo vuol dire meno spesa"}
    base.update(extra)
    return base


# ── quello che il modello DEVE dire, e quello che non deve ──────────────────

def test_un_osservazione_prende_il_NUMERO_dalla_serie_non_dalla_risposta():
    """**La regola che rende impossibile il numero inventato.** Il modello dice
    QUALE misura e PERCHE'; valore, copertura, scostamento e base li attacca il
    codice, letti dalla serie.

    Mutazione: copiare un `numero` dalla risposta -- rossa.
    """
    esito = at.apply_analysis(_serie(), _risposta([_osservazione()]))
    assert esito["problemi"] == []
    vista = esito["analisi"]["osservazioni"][0]
    assert vista["valore"] == 0.74
    assert vista["copertura"] == 1.0
    assert vista["quanti_scarti"] == 2.75
    assert vista["base"] == 2
    assert vista["unita"] == "kWh"
    assert vista["nome"] == "Inverter"


def test_un_osservazione_che_SCRIVE_un_numero_si_rifiuta():
    """Si rifiuta, non si corregge. Ignorarlo in silenzio nasconderebbe che il
    modello ha letto male; scriverlo al posto del nostro sarebbe peggio.

    Mutazione: ignorare il campo invece di rifiutare -- rossa.
    """
    esito = at.apply_analysis(_serie(), _risposta([_osservazione(valore=99.0)]))
    assert any("numero" in p for p in esito["problemi"]), esito["problemi"]


def test_un_osservazione_su_una_misura_che_NON_ESISTE_si_rifiuta():
    """Il modello non puo' parlare di una misura che la serie non contiene:
    sarebbe un'affermazione su una casa che non abbiamo guardato.

    La proprieta' non e' cambiata col contratto numerato; e' cambiata la chiave
    con cui si sbaglia, e adesso e' l'unica possibile.

    Mutazione: accettare qualunque numero -- rossa.
    """
    esito = at.apply_analysis(_serie(), _risposta([_osservazione(quale=7)]))

    assert esito["analisi"] is None
    assert any("7" in p for p in esito["problemi"]), esito["problemi"]


def test_la_CHIAVE_resta_parte_dell_identita_della_misura():
    """`co2.massimo` e `co2.media` sono due serie diverse, e un'osservazione
    che parla dell'una non parla dell'altra.

    Col contratto numerato questa proprieta' non si difende piu' confrontando
    campi: e' garantita **alla fonte**, perche' due serie diverse hanno due
    numeri diversi e non esiste un modo di indicarne una intendendo l'altra.
    Qui si verifica che il numero porti davvero la chiave giusta fino
    all'osservazione arricchita -- che e' cio' che la pagina poi legge.

    Mutazione ESEGUITA: far uscire la chiave della prima riga per tutte --
    rossa."""
    serie = _serie()
    serie["serie"].append({**serie["serie"][1], "chiave": "media"})

    esito = at.apply_analysis(serie, _risposta([
        _osservazione(quale=1, innesco=2), _osservazione(quale=2, innesco=2)]))

    assert esito["problemi"] == []
    chiavi = [o["chiave"] for o in esito["analisi"]["osservazioni"]]
    assert chiavi == ["massimo", "media"], chiavi


def test_un_INNESCO_fuori_dai_tre_si_rifiuta():
    """Gli inneschi sono tre e sono dichiarati nella spec: un'osservazione che
    non dice quale dei tre non e' dell'analista, e' un commento.

    Mutazione: accettare qualunque numero -- rossa.
    """
    for innesco in (0, 4, "uno", None):
        esito = at.apply_analysis(_serie(), _risposta([_osservazione(innesco=innesco)]))
        assert any("innesco" in p for p in esito["problemi"]), innesco


def test_senza_COSA_CAMBIEREBBE_si_rifiuta():
    """La spec lo elenca fra le quattro cose che ogni osservazione deve avere:
    senza, e' una constatazione, non qualcosa che si potrebbe fare -- e
    l'analista esiste per dire cosa si potrebbe fare.

    Mutazione: renderlo facoltativo -- rossa.
    """
    esito = at.apply_analysis(_serie(), _risposta([_osservazione(cosa_cambierebbe="  ")]))
    assert any("cambierebbe" in p for p in esito["problemi"]), esito["problemi"]


def test_il_SILENZIO_e_un_esito_legittimo_e_non_e_un_rifiuto():
    """*\u00abIl silenzio e' un esito legittimo\u00bb* (§10). Zero osservazioni non e' un
    errore e non e' un giro sprecato: e' una risposta, e si archivia.

    Mutazione: trattare l'elenco vuoto come un problema -- rossa.
    """
    esito = at.apply_analysis(_serie(), _risposta([]))
    assert esito["problemi"] == []
    assert esito["analisi"]["osservazioni"] == []


def test_TUTTI_i_problemi_si_dicono_insieme():
    """Stessa legge delle ricette: dirne uno per giro costringerebbe a
    rieseguire la notte per scoprirne un altro.

    Mutazione: tornare al primo problema -- rossa.
    """
    esito = at.apply_analysis(_serie(), _risposta([
        _osservazione(quale=99, innesco=9, cosa_cambierebbe="")]))

    assert len(esito["problemi"]) >= 3, esito["problemi"]


def test_una_risposta_che_non_e_JSON_lo_dice_e_non_solleva():
    """Mutazione: lasciar propagare l'eccezione -- rossa."""
    esito = at.apply_analysis(_serie(), "non sono JSON")
    assert esito["problemi"], "un guasto di forma e' un problema, non un crollo"
    assert esito["analisi"] is None


def test_una_risposta_VUOTA_non_si_scrive_affatto():
    """Il difetto gia' pagato dalle ricette il 13/09/2026: una decisione vuota
    -- il ponte che non sa ragionare quella specie di turno -- veniva scritta
    come se il modello avesse risposto. Una risposta che non c'e' non e'
    silenzio: e' un giro da rifare.

    Mutazione: trattare la risposta vuota come silenzio -- rossa.
    """
    esito = at.apply_analysis(_serie(), "   ")
    assert esito["analisi"] is None
    assert esito["risposta"] is False

# ── la domanda ──────────────────────────────────────────────────────────────

def test_la_domanda_porta_l_obiettivo_le_serie_e_il_contratto():
    """Mutazione: togliere l'obiettivo dalla domanda -- rossa."""
    q = at.build_question(_serie())
    assert "spendere meno" in q
    assert "prelievo" in q and "co2" in q
    assert "innesco" in q.lower()


def test_la_domanda_dice_QUANDO_la_domanda_e_cambiata():
    """\u00a711: senza, il modello leggerebbe una tendenza dove c'\u00e8 un cambio di
    domanda.

    Mutazione: non scrivere i tratti degli obiettivi -- rossa.
    """
    serie = _serie()
    serie["obiettivi"] = [
        {"dal": "2026-09-12", "al": "2026-09-12", "testo": "prima", "scritto_ts": 1.0},
        {"dal": "2026-09-13", "al": "2026-09-14", "testo": "dopo", "scritto_ts": 2.0},
    ]
    q = at.build_question(serie)
    assert "prima" in q and "dopo" in q
    assert "2026-09-13" in q


def test_la_copertura_PIENA_non_si_ripete_trenta_volte():
    """**La stessa regola della pagina**, misurata anche qui: le coperture sono
    il 18% del prompt, e \u00ab100%\u00bb accanto a ogni numero e' rumore su cui
    l'attenzione smette di fermarsi -- del modello quanto dell'occhio. Si dice
    che e' piena, una volta.

    Mutazione: scrivere sempre l'elenco -- rossa.
    """
    q = at.build_question(_serie())
    assert q.count("1.0, 1.0, 1.0") == 0, q[:400]
    assert "piena" in q


def test_una_copertura_che_CROLLA_si_scrive_per_intero():
    """Il terzo innesco: se la copertura cambia, i numeri vanno visti tutti.
    Comprimere si fa solo quando non c'e' niente da vedere.

    Mutazione: comprimere sempre -- rossa.
    """
    serie = _serie()
    serie["serie"][0]["coperture"] = [1.0, 0.4, 1.0]
    q = at.build_question(serie)
    assert "0.4" in q


def test_il_turno_per_il_ponte_ha_la_stessa_forma_degli_altri():
    """Il ponte gira altrove e non ha gli archivi; `istruzione` serve perche'
    l'istruzione di chiusura della chat gli vieterebbe il JSON.

    Mutazione: togliere `istruzione` -- rossa.
    """
    turno = at.bridge_turn(_serie())
    assert set(turno) == {"history", "system_prompt", "istruzione"}
    assert turno["history"][0]["role"] == "user"
    assert "spendere meno" in turno["history"][0]["content"]
    assert turno["istruzione"]


def test_senza_NESSUNA_serie_non_si_chiede_niente():
    """Una casa che non ha ancora misure non ha niente da analizzare, e la
    domanda costerebbe un giro per una risposta che non puo' esistere. Stessa
    regola di `build_device_question` con un dispositivo senza entita'.

    Mutazione: costruire la domanda lo stesso -- rossa.
    """
    assert at.build_question({"giorni": [], "obiettivi": [], "serie": []}) is None
    assert at.bridge_turn({"giorni": [], "obiettivi": [], "serie": []}) is None

def test_il_ponte_sa_ragionare_il_turno_dell_ANALISTA():
    """**Il difetto del 13/09/2026 non deve ripetersi.** Quel giorno il turno
    delle ricette fu accodato a un ponte che non sapeva ragionare quella
    specie: «job non-chat in coda: nessun ramo lo ragiona piu'», e la decisione
    vuota che ne usci' fu scritta come «non capito» di un modello mai
    interpellato.

    Una specie nuova che non entra qui e' una domanda che nessuno risponde.

    Mutazione: togliere `_ANALYSIS_KIND` da `RAGIONABILI` -- rossa.
    """
    from hiris.app.agent import runner
    from hiris.app.mind.analyst_turn import ANALYSIS_TURN_KIND

    assert ANALYSIS_TURN_KIND in runner.RAGIONABILI


def test_il_turno_dell_analista_NON_riceve_gli_strumenti():
    """**E' di sicurezza, non di eleganza.** Senza questa riga il turno
    girerebbe col catalogo della chat, `execute` compreso -- la porta con cui
    HIRIS accende, spegne e chiama un servizio -- e un turno che deve solo
    leggere dei numeri e scrivere delle frasi potrebbe agire sulla casa senza
    che nessun si' lo autorizzi. E' il rilievo chiuso per lo scope l'11/09 e
    ripreso per le ricette.

    Mutazione: togliere `_ANALYSIS_KIND` da `_SELF_CONTAINED_KINDS` -- rossa.
    """
    from hiris.app.agent import runner
    from hiris.app.mind.analyst_turn import ANALYSIS_TURN_KIND

    assert ANALYSIS_TURN_KIND in runner._SELF_CONTAINED_KINDS


# ---------------------------------------------------------------------------
# **Il contratto numerato, e perche' e' costato sei giorni di silenzio.**
#
# Misurato sulla casa vera il 22/09/2026, dal registro dell'add-on:
#
#   analista: risposta rifiutata per 2026-09-17 -- l'osservazione 1 parla di
#   «Presa Smart · potenza_media_min_max», che non e' fra le misure consegnate
#   · l'osservazione 3 parla di «Alexa · illuminamento_ambiente · media», ...
#
# Cinque osservazioni su cinque, sempre. Non era il modello che sbagliava: ogni
# riga della serie gli arriva con DUE identificatori --
#
#   {"soggetto": "061b20e991aafba5f4994ba574a7df8a", "nome": "Corridoio T", ...}
#
# -- e il contratto gli chiedeva `soggetto`, cioe' quello che a un modello
# linguistico somiglia meno a un identificatore. Rispondeva col nome.
#
# **La soluzione era gia' scritta in questo progetto, il giorno prima**, nel
# turno dell'attuatore: «Le osservazioni si consegnano NUMERATE, e il modello
# si riferisce a una col suo numero: ricopiarne il testo vorrebbe dire poterlo
# sbagliare». La lezione non era mai tornata indietro all'analista.
# ---------------------------------------------------------------------------

def test_la_domanda_consegna_le_misure_NUMERATE():
    """Senza un numero VISIBILE accanto a ogni riga, chiedere «il numero» e'
    chiedere al modello di contare -- e contare in un JSON di 162 righe e' il
    modo piu' facile di sbagliare di uno.

    Mutazione ESEGUITA: togliere la numerazione dalla domanda -- rossa."""
    domanda = at.build_question(_serie())

    assert "[0]" in domanda and "[1]" in domanda
    assert "Inverter" in domanda, "il nome resta: serve al modello per capire"


def test_un_NUMERO_FUORI_elenco_si_rifiuta():
    """Il numero e' l'unica chiave: se non e' nell'elenco non c'e' niente da
    arricchire, e inventare la riga piu' vicina sarebbe attaccare
    un'osservazione a una misura che nessuno ha scelto.

    Mutazione: accettare qualunque intero -- rossa."""
    esito = at.apply_analysis(_serie(), _risposta([_osservazione(quale=99)]))

    assert esito["analisi"] is None
    assert any("99" in p for p in esito["problemi"])


def test_il_NOME_UMANO_non_e_piu_una_chiave_e_il_rifiuto_lo_dice():
    """Il difetto del 17-22/09 preso alla radice: col contratto numerato un
    nome non e' piu' una risposta possibile, e il rifiuto dice cosa serve
    invece di dire che quella misura «non e' fra le consegnate» -- che era
    vero e inutile.

    Mutazione: accettare una stringa come numero -- rossa."""
    risposta = _risposta([{"soggetto": "Corridoio T", "misura": "temperatura",
                           "innesco": 1, "cosa": "x", "cosa_cambierebbe": "y"}])

    esito = at.apply_analysis(_serie(), risposta)

    assert esito["analisi"] is None
    assert any("numero" in p.lower() for p in esito["problemi"]), esito["problemi"]


def test_l_osservazione_arricchita_porta_ANCORA_soggetto_misura_e_chiave():
    """Cambia cio' che il modello DICE, non cio' che l'archivio riceve: la
    pagina, l'attuatore e il verificatore leggono `soggetto`/`misura`/`chiave`
    e non devono accorgersi di niente.

    Mutazione ESEGUITA: far uscire il numero invece dei tre campi -- rossa (la
    scheda «Cosa fare» non saprebbe piu' di cosa parla un'osservazione)."""
    esito = at.apply_analysis(_serie(), _risposta([_osservazione(quale=1)]))

    vista = esito["analisi"]["osservazioni"][0]
    assert vista["soggetto"] == "dev2"
    assert vista["misura"] == "co2"
    assert vista["chiave"] == "massimo"
    assert vista["nome"] == "Sala"
    assert "quale" not in vista, "il numero e' un dettaglio del turno, non un dato"
