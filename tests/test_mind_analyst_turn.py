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
        _osservazione(quale=1), _osservazione(quale=2)]))

    assert esito["problemi"] == []
    chiavi = [o["chiave"] for o in esito["analisi"]["osservazioni"]]
    assert chiavi == ["massimo", "media"], chiavi


def test_un_INNESCO_che_la_riga_NON_HA_si_rifiuta():
    """D3 e Task 3.5: gli inneschi li marca il codice sulla riga, e il modello
    sceglie fra quelli. La riga [0] e' candidata al solo innesco 1: un 3 -- che
    esiste nella spec, ma non su questa riga -- si rifiuta, come uno che non
    esiste affatto.

    Mutazione ESEGUITA (06/10/2026): `_trigger` che accetta qualunque innesco
    dei tre -- rossa (il 2 e il 3 passano).

    `True` e `1.0` valgono 1 per Python, e si rifiutano lo stesso (G21-1 del
    revisore, giro 21): finivano nell'impronta con un'altra forma, e la
    ripetizione non si toglieva piu'. Mutazione ESEGUITA (06/10/2026): togliere
    il controllo sul tipo -- rossa (`True` passa)."""
    for innesco in (0, 2, 3, 4, "uno", True, 1.0):
        esito = at.apply_analysis(_serie(), _risposta([_osservazione(innesco=innesco)]))
        assert any("innesco" in p for p in esito["problemi"]), innesco


def test_l_INNESCO_lo_attacca_il_codice_quando_la_riga_ne_ha_uno():
    """Mutazione ESEGUITA (06/10/2026): `_trigger` che pretende l'innesco
    scritto -- rossa."""
    riga = _osservazione()
    del riga["innesco"]
    esito = at.apply_analysis(_serie(), _risposta([riga]))
    assert esito["problemi"] == []
    assert esito["analisi"]["osservazioni"][0]["innesco"] == 1


def test_con_PIU_inneschi_sulla_riga_il_modello_SCEGLIE():
    serie = _serie()
    serie["serie"][0]["coperture"] = [1.0, 1.0, 0.4]
    riga = _osservazione()
    del riga["innesco"]
    esito = at.apply_analysis(serie, _risposta([riga]))
    assert any("scegline uno" in p for p in esito["problemi"]), esito["problemi"]

    esito = at.apply_analysis(serie, _risposta([_osservazione(innesco=3)]))
    assert esito["analisi"]["osservazioni"][0]["innesco"] == 3


def test_una_riga_SENZA_inneschi_non_e_candidata():
    serie = _serie()
    serie["serie"][0]["scostamento"] = {"ultimo": 0.74, "mediana": 0.3, "scarto": None,
                                        "quanti_scarti": None, "base": 1,
                                        "non_calcolabile": "storia corta"}
    esito = at.apply_analysis(serie, _risposta([_osservazione()]))
    assert any("nessun" in p for p in esito["problemi"]), esito["problemi"]


def test_COSA_CAMBIEREBBE_e_facoltativo():
    """Task 3.5: obbligatorio contraddiceva «il silenzio e' un esito
    legittimo» -- spingeva a inventare un'azione per ogni constatazione
    (audit del 01/10/2026).

    Mutazione ESEGUITA (06/10/2026): rimetterlo obbligatorio in `_enrich`
    -- rossa."""
    esito = at.apply_analysis(_serie(), _risposta([_osservazione(cosa_cambierebbe="  ")]))
    assert esito["problemi"] == []
    vista = esito["analisi"]["osservazioni"][0]
    assert vista["cosa_cambierebbe"] is None
    assert vista["da_riverificare"] is None

    riga = _osservazione()
    riga["da_riverificare"] = "se il contatore e' ripartito"
    esito = at.apply_analysis(_serie(), _risposta([riga]))
    assert esito["analisi"]["osservazioni"][0]["da_riverificare"] == \
        "se il contatore e' ripartito"


def test_il_RIMETTI_si_valida_e_si_archivia_con_l_analisi():
    """D9: l'analista chiede nella risposta di far rientrare un'entita'; lo
    scrive il Task 3.7. Qui la forma: `id` e `perche`, tutti e due."""
    import json
    buona = json.dumps({"osservazioni": [], "rimetti": [
        {"id": "sensor.batteria", "perche": "spiega il prelievo serale"}]})
    esito = at.apply_analysis(_serie(), buona)
    assert esito["analisi"]["rimetti"] == [
        {"id": "sensor.batteria", "perche": "spiega il prelievo serale"}]

    storta = json.dumps({"osservazioni": [], "rimetti": [{"id": "sensor.x"}]})
    assert at.apply_analysis(_serie(), storta)["analisi"] is None


def test_il_RIMETTI_vuole_un_ENTITY_ID():
    """G21-2 del revisore (giro 21): «camera da letto» passava. Mutazione
    ESEGUITA (06/10/2026): controllare solo che l'id non sia vuoto -- rossa."""
    import json
    for ident in ("camera da letto", "batteria", "Sensor.x"):
        storta = json.dumps({"osservazioni": [], "rimetti": [
            {"id": ident, "perche": "spiega il prelievo serale"}]})
        assert at.apply_analysis(_serie(), storta)["analisi"] is None, ident


def test_le_LETTURE_del_turno_vengono_dal_registro_delle_chiamate():
    """Task 3.5, Passo 3: dal runner (`last_tool_calls`), non dal testo."""
    chiamate = [{"tool": "history", "input": {"riferimento": "sensor.prelievo"}}]
    esito = at.apply_analysis(_serie(), _risposta([]), tool_calls=chiamate)
    assert esito["analisi"]["letture"] == chiamate
    assert "letture" not in at.apply_analysis(_serie(), _risposta([]))["analisi"]


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
        _osservazione(quale=99, cosa="", valore=3.0)]))

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


def test_la_copertura_PIENA_si_dice_una_volta():
    """**La stessa regola della pagina**, misurata anche qui: le coperture
    erano il 18% del prompt, e «100%» accanto a ogni numero e' rumore su cui
    l'attenzione smette di fermarsi -- del modello quanto dell'occhio.

    Mutazione: scrivere l'elenco delle coperture -- rossa.
    """
    q = at.build_question(_serie())
    assert q.count("1.0, 1.0, 1.0") == 0, q[:400]
    assert "piena" in q


def test_una_copertura_che_CROLLA_si_vede_nell_indice():
    """Il terzo innesco: se la copertura cambia, la riga dice la minima e
    l'ultima, e il fatto dell'innesco lo marca il codice.
    """
    serie = _serie()
    serie["serie"][0]["coperture"] = [1.0, 1.0, 0.4]
    q = at.build_question(serie)
    assert "0.4" in q
    assert "la copertura e' passata da 1.0 a 0.4" in q


# ── l'indice (D2 e D3 del piano degli attori, 06/10/2026) ───────────────────

def _riga(soggetto, valori, coperture=None, perche=()):
    from hiris.app.mind import analyst
    serie = {"soggetto": soggetto, "nome": soggetto.title(), "misura": "m",
             "chiave": None, "operazione": "somma_periodo", "unita": "kWh",
             "valori": valori,
             "coperture": coperture or [1.0 if v is not None else None for v in valori],
             "perche": list(perche)}
    return analyst.with_deviation({"serie": [serie]})["serie"][0]


def _trenta():
    """Trenta giorni, cinque misure: una che si scosta molto, una poco, una
    che non varia mai, una che oggi non si calcola, una con due giorni."""
    giorni = [f"2026-09-{d:02d}" for d in range(1, 31)]
    storia = [10.0 + (d % 3) for d in range(29)]
    righe = [
        _riga("poco", storia + [12.5]),
        _riga("piatta", [5.0] * 30),
        _riga("ferma", storia + [None], perche=[
            {"dal": giorni[-1], "al": giorni[-1], "ragione": "l'entita' e' sparita",
             "causa": "sparita"}]),
        _riga("molto", storia + [40.0]),
        _riga("giovane", [None] * 28 + [3.0, 4.0]),
    ]
    return {"giorni": giorni, "serie": righe,
            "obiettivi": [{"dal": giorni[0], "al": giorni[-1],
                           "testo": "spendere meno", "scritto_ts": 1.0}]}


def _index_lines(domanda):
    import json
    return [(int(riga[1:riga.index("]")]), json.loads(riga[riga.index("]") + 2:]))
            for riga in domanda.splitlines() if riga.startswith("[")]


def test_l_INDICE_ha_una_riga_per_misura_e_nessun_valore_della_serie():
    """D2: una riga per misura coi numeri di `with_deviation`, e **nessun**
    valore della serie. Il conto delle righe si chiede alle serie.

    Mutazione ESEGUITA (06/10/2026): in `analyst.index` saltare le righe senza
    fatti d'innesco -- rossa (4 righe su 5: «giovane» non c'e')."""
    serie = _trenta()
    righe = _index_lines(at.build_question(serie))

    assert sorted(n for n, _ in righe) == list(range(len(serie["serie"])))
    for _, riga in righe:
        assert "valori" not in riga and "coperture" not in riga
        assert {"ultimo", "mediana", "scarto", "base", "quanti_scarti",
                "copertura", "inneschi"} <= set(riga)
    # Nessun tratto della storia arriva al modello: la sequenza dei giorni
    # 10, 11, 12 c'e' solo nelle serie.
    assert "10.0, 11.0, 12.0" not in at.build_question(serie)


def test_l_INDICE_e_in_ORDINE_di_scostamento_e_marca_i_tre_inneschi():
    """D3: il codice marca i candidati e ordina, il modello sceglie. Prima chi
    si scosta di piu', poi chi non ha scostamento, nell'ordine della serie."""
    serie = _trenta()
    righe = _index_lines(at.build_question(serie))
    nomi = [riga["nome"] for _, riga in righe]

    assert nomi[:2] == ["Molto", "Poco"]
    assert sorted(nomi[2:]) == ["Ferma", "Giovane", "Piatta"]
    per_nome = {riga["nome"]: riga for _, riga in righe}
    assert [f["innesco"] for f in per_nome["Molto"]["inneschi"]] == [1]
    assert [f["innesco"] for f in per_nome["Piatta"]["inneschi"]] == [2]
    assert [f["innesco"] for f in per_nome["Ferma"]["inneschi"]] == [3]
    assert per_nome["Giovane"]["inneschi"] == []
    # Il numero resta la chiave della serie: «Molto» e' la quarta misura.
    assert {riga["nome"]: n for n, riga in righe}["Molto"] == 3


def test_una_misura_che_OGGI_non_si_calcola_porta_la_sua_CAUSA():
    """Mutazione ESEGUITA (06/10/2026): `cause_today` che torna sempre `None`
    -- rossa (`KeyError: 'causa_oggi'`)."""
    righe = dict(_index_lines(at.build_question(_trenta())))

    ferma = righe[2]
    assert ferma["causa_oggi"]["causa"] == "sparita"
    assert ferma["causa_oggi"]["dal"] == "2026-09-30"
    assert "non_calcolabile" in ferma


def test_l_obiettivo_e_IN_VIGORE_e_ha_una_fine_solo_se_e_cambiato():
    """D2: «dal ... al ...» sull'obiettivo corrente si leggeva come una
    scadenza (audit del 01/10/2026)."""
    serie = _trenta()
    q = at.build_question(serie)
    assert "in vigore dal 2026-09-01: spendere meno" in q
    assert "fino al" not in q

    serie["obiettivi"] = [
        {"dal": "2026-09-01", "al": "2026-09-10", "testo": "prima", "scritto_ts": 1.0},
        {"dal": "2026-09-11", "al": "2026-09-30", "testo": "dopo", "scritto_ts": 2.0}]
    q = at.build_question(serie)
    assert "dal 2026-09-01 fino al 2026-09-10: prima" in q
    assert "in vigore dal 2026-09-11: dopo" in q


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
