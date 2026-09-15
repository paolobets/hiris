"""Il resoconto giornaliero: due parti, e la separazione e' funzionale.

Spec `docs/design/2026-09-10-i-tre-attori.md` §9, e la forma decisa col
proprietario il 13/09/2026.

**A cosa serve, e da li' viene la struttura.** Il resoconto non e' fatto per un
umano: serve **all'analista** (§10), che ha tre inneschi e tutti e tre sono
confronti o letture di NUMERI:

1. *«qualcosa e' cambiato e non e' spiegato»* -- la stessa misura su molti giorni;
2. *«qualcosa e' stabile e costa»* -- il VALORE, non lo scostamento: la batteria
   satura al 90% dalle 13 alle 16 non varia mai, ed e' il costo piu' alto della
   prova;
3. *«qualcosa non c'e' piu'»* -- la **copertura** e il «non calcolabile, e
   perche'» devono essere visibili come i numeri, o una misura che sparisce e'
   indistinguibile da una a zero. E' il caso vero: `bilancio` a zero per cinque
   giorni su cinque, e nessuno se n'e' accorto.

Da qui le due parti: **le misure** si leggono in serie, molti giorni insieme;
**la cronaca** e' un INDICE -- quando, chi, cosa -- che l'analista scorre e da
cui poi scava, in Home Assistant o nel nostro grezzo.

**Perche' la cronaca e' un indice e non l'episodio intero**, misurato sui 200
oggetti veri della casa il 13/09/2026: l'episodio intero pesa 622 byte, l'indice
109. Su trenta giorni sono **521 KB contro 92**: con la cronaca della spec
l'analista puo' guardare solo il giorno che ha gia' deciso di guardare, e per
sapere quale dovrebbe averlo gia' guardato.

**Ma l'indice porta un'ancora**, ed e' l'unico difetto irreversibile che la
forma nuda avrebbe: cio' che dopo non si recupera piu' perche' dipende da
com'era la casa allora -- il **nome** che l'entita' aveva, la sua **classe**,
gli **attributi** raccolti. Home Assistant, richiesto domani, risponde con
quelli di domani: e' la lezione gia' pagata da `friendly_name`.
"""

from hiris.app.mind import report as rep

EPISODI = [
    {"genere": "funzionamento", "protagonista": "climate.soggiorno",
     "inizio": 1789219800.0, "fine": 1789223400.0,
     "corpo_base": {"stato": "heat", "nome": "Termostato Soggiorno",
                    "classe": None,
                    "attributi": [{"quando_ts": 1789223400.0,
                                   "valori": {"hvac_action": "idle"}}]}},
    {"genere": "presenza", "protagonista": "person.paolo",
     "inizio": 1789200000.0, "fine": None,
     "corpo_base": {"stato": "not_home", "nome": "Paolo"}},
]

RICETTA = {
    "why": "l'inverter pesa sul risparmio energetico",
    "steps": [
        {"name": "prodotta", "operation": "somma_periodo",
         "inputs": ["@sensor.prodotta"],
         "params": {"unit": "kWh", "expected_parts": 24}},
        {"name": "consumata", "operation": "somma_periodo",
         "inputs": ["@sensor.consumata"],
         "params": {"unit": "kWh", "expected_parts": 24}},
        {"name": "quota_coperta", "operation": "quota",
         "inputs": ["$prodotta", "$consumata"]},
    ],
}


def _serie(valori):
    return [{"valore": v} for v in valori]


SERIE = {"sensor.prodotta": _serie([1.0] * 24),
         "sensor.consumata": _serie([2.0] * 24)}


# -- le misure --------------------------------------------------------------

def test_ogni_misura_porta_valore_unita_e_COPERTURA():
    """Senza la copertura una misura non si puo' paragonare a quella di ieri:
    il primo innesco dell'analista non si potrebbe nemmeno porre.

    Mutazione ESEGUITA: non copiare `copertura` nella misura -- rossa.
    """
    r = rep.build_report(day="2026-09-13", episodes=[], series=SERIE,
                         recipes={"dev1": RICETTA}, names={"dev1": "Inverter"})

    prodotta = next(m for m in r["misure"] if m["misura"] == "prodotta")
    assert prodotta["valore"] == 24.0
    assert prodotta["unita"] == "kWh"
    assert prodotta["copertura"] == 1.0
    assert prodotta["operazione"] == "somma_periodo"
    assert prodotta["soggetto"] == "dev1"
    assert prodotta["nome"] == "Inverter"


def test_il_resoconto_dice_quali_entita_NON_AVRANNO_MAI_una_serie():
    """Il primo dei due «rifiuta se» della spec §6, fino in fondo al
    resoconto.

    Misurato sulla casa vera il 15/09/2026: **18 rifiuti su 28** nel resoconto
    del 14 erano su entita' per cui Home Assistant non tiene statistiche
    affatto, e dicevano «la serie e' vuota» -- vero, e inutile: chi legge va a
    cercare un buco nei dati, e il modello riscrive la stessa ricetta.

    Mutazione ESEGUITA: non passare l'insieme alla ricetta -- rossa.
    """
    r = rep.build_report(day="2026-09-13", episodes=[], series=SERIE,
                         recipes={"dev1": RICETTA}, names={},
                         without_statistics={"sensor.prodotta"})

    prodotta = next(m for m in r["misure"] if m["misura"] == "prodotta")
    assert "valore" not in prodotta
    assert "non ha statistiche" in prodotta["non_calcolabile"]
    # E le altre misure dello stesso dispositivo restano calcolate.
    consumata = next(m for m in r["misure"] if m["misura"] == "consumata")
    assert "valore" in consumata


def test_senza_l_insieme_il_resoconto_non_afferma_niente_sulle_statistiche():
    """Chi non ha potuto chiedere a Home Assistant quali entita' abbiano
    statistiche non deve dire che non ne hanno: direbbe una cosa che non sa, e
    **ogni misura della casa rifiuterebbe**.

    Mutazione ESEGUITA: trattare l'assenza come insieme vuoto — verde (non
    cambia niente: un insieme vuoto non muta nessuna entita'). La prova vale
    contro l'altro verso, cioe' contro chi in futuro facesse dell'assenza un
    «nessuna entita' ha statistiche»: e' il verso che romperebbe la casa.
    """
    r = rep.build_report(day="2026-09-13", episodes=[], series=SERIE,
                         recipes={"dev1": RICETTA}, names={})

    prodotta = next(m for m in r["misure"] if m["misura"] == "prodotta")
    assert "valore" in prodotta


def test_una_misura_NON_CALCOLABILE_dice_perche_e_resta_nel_resoconto():
    """**E' il terzo innesco dell'analista, e il caso vero che l'ha fatto
    nascere**: `bilancio` a zero per cinque giorni su cinque, e nessuno se n'e'
    accorto. Una misura che sparisce dal resoconto e' indistinguibile da una
    che non e' mai esistita; una che resta col suo «non calcolabile, e perche'»
    si vede.

    Mutazione ESEGUITA: saltare le misure non calcolabili -- rossa.
    """
    magra = {"sensor.prodotta": _serie([1.0] + [None] * 23),
             "sensor.consumata": _serie([2.0] * 24)}

    r = rep.build_report(day="2026-09-13", episodes=[], series=magra,
                         recipes={"dev1": RICETTA}, names={})

    prodotta = next(m for m in r["misure"] if m["misura"] == "prodotta")
    assert "valore" not in prodotta
    assert "copertura" in prodotta["non_calcolabile"]


def test_le_misure_di_PIU_DISPOSITIVI_stanno_insieme():
    r = rep.build_report(day="2026-09-13", episodes=[], series=SERIE,
                         recipes={"dev1": RICETTA, "dev2": RICETTA}, names={})

    assert {m["soggetto"] for m in r["misure"]} == {"dev1", "dev2"}


def test_una_ricetta_NON_VALIDA_non_ferma_il_resoconto():
    """Una ricetta storta -- corretta a mano male, o scritta da un modello che
    ha sbagliato -- non deve far perdere il giorno intero: si dichiara fra le
    misure non calcolabili, e le altre restano.

    Mutazione che la uccide: lasciar sollevare `Recipe.run`.
    """
    storta = {"why": "x", "steps": [
        {"name": "p", "operation": "inventata", "inputs": ["@sensor.prodotta"]}]}

    r = rep.build_report(day="2026-09-13", episodes=[], series=SERIE,
                         recipes={"dev1": RICETTA, "dev2": storta}, names={})

    assert any(m["soggetto"] == "dev1" and m.get("valore") for m in r["misure"])
    rotta = next(m for m in r["misure"] if m["soggetto"] == "dev2")
    assert "inventata" in rotta["non_calcolabile"]


# -- la cronaca: un indice, con l'ancora ------------------------------------

def test_la_cronaca_e_un_INDICE_quando_chi_cosa():
    r = rep.build_report(day="2026-09-13", episodes=EPISODI, series={},
                         recipes={}, names={})

    primo = r["cronaca"][0]
    assert primo["quando_ts"] == 1789219800.0
    assert primo["fine_ts"] == 1789223400.0
    assert primo["chi"] == "climate.soggiorno"
    assert primo["cosa"] == "heat"


def test_la_cronaca_porta_l_ANCORA_cio_che_dopo_non_si_recupera():
    """**L'unico difetto irreversibile che l'indice nudo avrebbe.** Home
    Assistant, richiesto domani, risponde col nome e la classe di DOMANI: e' la
    lezione gia' pagata da `friendly_name`, che si salva nel grezzo invece di
    risolverlo dopo. E gli attributi HA non li tiene in nessun caso.

    Mutazione ESEGUITA: togliere `nome`/`attributi` dalla voce -- rossa.
    """
    r = rep.build_report(day="2026-09-13", episodes=EPISODI, series={},
                         recipes={}, names={})

    primo = r["cronaca"][0]
    assert primo["nome"] == "Termostato Soggiorno"
    assert primo["attributi"][0]["valori"] == {"hvac_action": "idle"}


def test_la_cronaca_NON_porta_il_contesto_attorno():
    """E' la meta' che si va a prendere quando serve: i comprimari, il clima
    mentre durava, il resto. Tenerli qui costerebbe cinque volte tanto --
    misurato: 622 byte a fatto contro 109 -- e trenta giorni di cronaca non
    starebbero in un prompt.

    Mutazione che la uccide: copiare `corpo_base` intero nella voce.
    """
    episodio_ricco = [{**EPISODI[0], "corpo_base": {
        **EPISODI[0]["corpo_base"], "comprimari": ["sensor.temperatura"],
        "misure": {"sensor.temperatura": {"da": 18.2, "a": 21.0}}}}]

    r = rep.build_report(day="2026-09-13", episodes=episodio_ricco, series={},
                         recipes={}, names={})

    assert "comprimari" not in r["cronaca"][0]
    assert "misure" not in r["cronaca"][0]


def test_una_chiave_che_non_ha_niente_da_dire_TACE():
    """Mai un `nome: null` -- e' la regola che tutto il corpo degli oggetti
    segue gia'."""
    r = rep.build_report(day="2026-09-13", episodes=EPISODI, series={},
                         recipes={}, names={})

    secondo = r["cronaca"][1]
    assert "classe" not in secondo
    assert "attributi" not in secondo
    assert secondo["fine_ts"] is None, "«ancora in corso» e' un fatto, non un buco"


# -- il resoconto intero ----------------------------------------------------

def test_il_resoconto_porta_il_suo_giorno_la_domanda_e_le_tre_parti():
    r = rep.build_report(day="2026-09-13", episodes=EPISODI, series=SERIE,
                         recipes={"dev1": RICETTA}, names={})

    assert r["giorno"] == "2026-09-13"
    assert set(r) == {"giorno", "obiettivo", "misure", "forme", "cronaca"}


def test_un_giorno_SENZA_NIENTE_e_un_resoconto_vuoto_non_un_errore():
    """Una casa spenta produce un resoconto vuoto, e va scritto lo stesso: «quel
    giorno non e' successo niente» e «quel giorno non l'abbiamo guardato» sono
    due cose diverse, e l'analista deve poterle distinguere."""
    r = rep.build_report(day="2026-09-13", episodes=[], series={},
                         recipes={}, names={})

    assert r == {"giorno": "2026-09-13", "obiettivo": None, "misure": [],
                 "forme": [], "cronaca": []}


# -- il documento: DERIVATO, mai scritto ------------------------------------

def test_il_documento_ha_una_sezione_per_parte():
    """Le sezioni sono l'indice: si consegna solo `## Le misure` di trenta
    giorni, poi solo `## La cronaca` del giorno che e' saltato fuori."""
    r = rep.build_report(day="2026-09-13", episodes=EPISODI, series=SERIE,
                         recipes={"dev1": RICETTA}, names={"dev1": "Inverter"})

    doc = rep.as_document(r)

    assert doc.startswith("# Resoconto del 2026-09-13")
    assert "## Le misure" in doc
    assert "## La cronaca" in doc


def test_il_documento_costa_un_TERZO_del_JSON():
    """Misurato il 13/09/2026 sui 200 oggetti veri: la stessa cronaca pesa 146
    KB in JSON e 46 in markdown su trenta giorni. Un terzo, e si paga a ogni
    giro dell'analista.

    Non e' un'ottimizzazione prematura: e' la ragione per cui il documento
    esiste come resa invece che il JSON essere consegnato cosi' com'e'.
    """
    import json

    r = rep.build_report(day="2026-09-13", episodes=EPISODI * 20, series=SERIE,
                         recipes={"dev1": RICETTA}, names={})

    doc = rep.as_document(r)
    assert len(doc) < len(json.dumps(r, ensure_ascii=False)) * 0.6


def test_cio_che_NON_si_sa_ha_una_sezione_SUA():
    """Il terzo innesco dell'analista deve saltare all'occhio, non stare in
    fondo a una tabella di numeri buoni.

    Mutazione che la uccide: rendere le non calcolabili dentro «Le misure».
    """
    magra = {"sensor.prodotta": _serie([1.0] + [None] * 23),
             "sensor.consumata": _serie([2.0] * 24)}
    r = rep.build_report(day="2026-09-13", episodes=[], series=magra,
                         recipes={"dev1": RICETTA}, names={})

    doc = rep.as_document(r)

    assert "## Cosa non si sa" in doc
    assert "copertura" in doc.split("## Cosa non si sa", 1)[1]


def test_una_sezione_si_puo_prendere_da_sola():
    """E' il meccanismo delle porzioni: l'analista scorre le misure di trenta
    giorni, trova il giorno, e chiede solo la cronaca di quello."""
    r = rep.build_report(day="2026-09-13", episodes=EPISODI, series=SERIE,
                         recipes={"dev1": RICETTA}, names={})

    solo_misure = rep.section(rep.as_document(r), "Le misure")

    assert "prodotta" in solo_misure
    assert "climate.soggiorno" not in solo_misure


def test_una_sezione_che_non_esiste_torna_VUOTO_non_un_errore():
    r = rep.build_report(day="2026-09-13", episodes=[], series={},
                         recipes={}, names={})

    assert rep.section(rep.as_document(r), "Le ricette") == ""

def test_una_ricetta_che_il_registro_rifiuta_NON_fa_morire_il_giorno():
    """**Il difetto del 14/09/2026, dalla parte del resoconto.**

    Il resoconto eseguiva le ricette **senza validarle**: una ricetta scritta
    contro un registro piu' vecchio, o corretta male a mano, arrivava dritta a
    `run()`. La prima che il modello abbia scritto nominava `episodio`, e il
    `TypeError` che ne e' uscito non lo catturava nessuno: e' morta l'intera
    riaggregazione di due giorni, oggetti e resoconti, a ogni riavvio.

    Si valida prima, e il rifiuto diventa una riga di «cosa non si sa» col suo
    perche' -- che e' il posto dove l'analista guarda cio' che manca.

    Mutazione ESEGUITA: togliere la validazione da `_measurements` -- rossa
    con `TypeError`, che il test non cattura.
    """
    resoconto = rep.build_report(
        day="2026-09-13", episodes=[],
        series={"climate.x": []},
        recipes={"dev1": {"why": "quanto e' stato acceso", "steps": [
            {"name": "acceso", "operation": "episodio",
             "inputs": ["@climate.x"]}]}},
        names={"dev1": "Termostato"})

    righe = resoconto["misure"]
    assert len(righe) == 1
    assert "valore" not in righe[0]
    assert righe[0]["nome"] == "Termostato"
    assert "episodio" in righe[0]["non_calcolabile"]


def test_il_rifiuto_di_una_ricetta_dice_TUTTI_i_problemi_insieme():
    """Legge delle ricette (spec §7): «tutti i problemi si dicono insieme».
    Dirne uno per giro costringerebbe il proprietario a correggere, rieseguire
    la notte, e scoprirne un altro.

    Mutazione: tenere solo il primo problema -- rossa.
    """
    resoconto = rep.build_report(
        day="2026-09-13", episodes=[], series={},
        recipes={"dev1": {"why": "", "steps": [
            {"name": "totale", "operation": "somma_periodo",
             "inputs": ["@sensor.mai_vista"]}]}},
        names={})

    perche = resoconto["misure"][0]["non_calcolabile"]
    # Due problemi diversi, tutti e due nella stessa riga: il `why` mancante
    # E il parametro obbligatorio mancante.
    assert "PERCHE' esiste" in perche, perche
    assert "unit" in perche, perche

def test_una_misura_che_non_e_un_NUMERO_non_sta_fra_le_misure():
    """**Misurato sulla casa vera il 14/09/2026**: le misure del giorno
    pesavano 17.399 byte, e **13.055 -- il 75% -- erano otto serie orarie**
    finite dentro `valore` (`forma_produzione`, `illuminamento_profilo_orario`,
    ...). La spec §9 dice che le misure si leggono **in serie, molti giorni
    insieme**, e che trenta giorni stanno in un prompt: con quei numeri erano
    522 KB, e non erano piu' decine di numeri -- erano quattro numeri e otto
    serie.

    Una forma oraria non e' una misura da leggere in serie: e' un **dettaglio
    del giorno**, come la cronaca. Sta in `forme`, e si consegna a richiesta.

    Mutazione: rimettere le liste fra le misure -- rossa.
    """
    resoconto = rep.build_report(
        day="2026-09-13", episodes=[],
        series={"sensor.p": [{"inizio": 0.0, "fine": 3600.0, "valore": 2.0},
                             {"inizio": 3600.0, "fine": 7200.0, "valore": 3.0}]},
        recipes={"dev1": {"why": "la produzione", "steps": [
            {"name": "totale", "operation": "somma_periodo",
             "inputs": ["@sensor.p"], "params": {"unit": "kWh"}},
            {"name": "forma", "operation": "per_ora",
             "inputs": ["@sensor.p"], "params": {"unit": "kWh"}}]}},
        names={"dev1": "Inverter"})

    misure = [m["misura"] for m in resoconto["misure"]]
    forme = [f["misura"] for f in resoconto["forme"]]
    assert misure == ["totale"], misure
    assert forme == ["forma"], forme
    assert isinstance(resoconto["forme"][0]["valore"], list)


def test_una_forma_porta_il_suo_nome_e_la_sua_unita_come_una_misura():
    """Non e' un ripostiglio: una forma resta una riga completa -- soggetto,
    nome, operazione, unita', copertura -- perche' chi la chiede deve poterla
    leggere senza tornare a chiedere altro.

    Mutazione: scrivere in `forme` solo il valore -- rossa.
    """
    resoconto = rep.build_report(
        day="2026-09-13", episodes=[],
        series={"sensor.p": [{"inizio": 0.0, "fine": 3600.0, "valore": 2.0}]},
        recipes={"dev1": {"why": "la forma", "steps": [
            {"name": "forma", "operation": "per_ora",
             "inputs": ["@sensor.p"], "params": {"unit": "kWh"}}]}},
        names={"dev1": "Inverter"})

    riga = resoconto["forme"][0]
    assert riga["nome"] == "Inverter"
    assert riga["operazione"] == "per_ora"
    assert riga["unita"] == "kWh"
    assert riga["copertura"] == 1.0


def test_cio_che_non_si_e_potuto_calcolare_resta_fra_le_MISURE():
    """Un rifiuto non ha una forma: sta dove l'analista guarda cio' che manca,
    cioe' fra le misure -- da cui `as_document` costruisce «cosa non si sa».
    Spostarlo in `forme` lo nasconderebbe.

    Mutazione: mandare in `forme` tutto cio' che non ha un valore numerico,
    rifiuti compresi -- rossa.
    """
    resoconto = rep.build_report(
        day="2026-09-13", episodes=[], series={"sensor.vuoto": []},
        recipes={"dev1": {"why": "il totale", "steps": [
            {"name": "totale", "operation": "somma_periodo",
             "inputs": ["@sensor.vuoto"], "params": {"unit": "kWh"}}]}},
        names={})

    assert resoconto["forme"] == []
    assert "non_calcolabile" in resoconto["misure"][0]

def test_media_min_max_e_una_MISURA_non_una_forma():
    """**Difetto trovato prima che facesse danno, il 14/09/2026.**

    Il criterio della 3.36.0 era «non e' un numero -> e' una forma», e
    `media_min_max` torna un DIZIONARIO -- `{media, minimo, massimo}`. Con quel
    criterio finiva fra le forme, cioe' **fuori dalle misure che l'analista
    legge in serie**: e' esattamente l'operazione che risponde a «com'e' stata
    la temperatura», il primo innesco. Stessa sorte per `tendenza` e
    `confronto_periodi`.

    Non aveva ancora fatto danno solo perche' tutte e tre rifiutavano: sarebbero
    diventate sbagliate nel momento esatto in cui le misure istantanee si
    sbloccano.

    Il criterio vero e' quello che la misura diceva dall'inizio: **una LISTA e'
    una forma** -- venticinque punti orari, il 75% dei byte -- e tutto il resto
    e' una misura, anche quando e' fatto di tre numeri invece che di uno.

    Mutazione: tornare a `isinstance(valore, (int, float))` -- rossa.
    """
    serie = [{"inizio": float(h * 3600), "fine": float((h + 1) * 3600),
              "valore": 20.0 + h} for h in range(4)]
    resoconto = rep.build_report(
        day="2026-09-13", episodes=[], series={"sensor.t": serie},
        recipes={"dev1": {"why": "com'e' stata la stanza", "steps": [
            {"name": "temperatura", "operation": "media_min_max",
             "inputs": ["@sensor.t"], "params": {"unit": "\u00b0C"}},
            {"name": "profilo", "operation": "per_ora",
             "inputs": ["@sensor.t"], "params": {"unit": "\u00b0C"}}]}},
        names={"dev1": "Soggiorno"})

    assert [m["misura"] for m in resoconto["misure"]] == ["temperatura"]
    assert [f["misura"] for f in resoconto["forme"]] == ["profilo"]
    assert resoconto["misure"][0]["valore"] == {
        "media": 21.5, "minimo": 20.0, "massimo": 23.0}

def test_il_resoconto_porta_l_OBIETTIVO_che_valeva_quel_giorno():
    """**Spec §11**: chi legge trenta giorni di misure in serie deve sapere se
    in mezzo la domanda e' cambiata, o legge una tendenza dove c'e' un cambio
    d'obiettivo. E' l'analista a leggerle cosi', quindi la riga deve esserci
    prima di lui.

    La funzione che serve esiste da giorni -- `store.objective_at(ts)`, il cui
    docstring dice *«la domanda che il resoconto porra' a ogni giornata che
    rilegge»* -- e **nessun codice di produzione la chiamava**: una motivazione
    scritta accanto al codice che il codice smentiva.

    Mutazione: togliere `obiettivo` dal resoconto -- rossa.
    """
    r = rep.build_report(day="2026-09-13", episodes=[], series={}, recipes={},
                         names={}, objective={"testo": "spendere meno di sera",
                                              "scritto_ts": 1787000000.0})
    assert r["obiettivo"] == {"testo": "spendere meno di sera",
                              "scritto_ts": 1787000000.0}


def test_un_resoconto_senza_obiettivo_dichiarato_non_ne_inventa_uno():
    """`None` resta `None`: un resoconto vecchio, scritto prima che questa riga
    esistesse, non deve spacciare l'obiettivo di **oggi** per quello di allora
    -- e' la stessa legge gia' pagata da `friendly_name` e dall'ancora della
    cronaca.

    Mutazione: mettere l'obiettivo di fabbrica come valore di ripiego -- rossa.
    """
    r = rep.build_report(day="2026-09-13", episodes=[], series={}, recipes={},
                         names={})
    assert r["obiettivo"] is None


def test_il_documento_scrive_l_obiettivo_sotto_il_titolo():
    """E' la domanda a cui quel giorno risponde: sta in cima, dove chi legge la
    incontra prima dei numeri.

    Mutazione: non scriverlo nel documento -- rossa.
    """
    documento = rep.as_document(rep.build_report(
        day="2026-09-13", episodes=[], series={}, recipes={}, names={},
        objective={"testo": "spendere meno di sera", "scritto_ts": 1.0}))
    righe = documento.split("\n")
    assert righe[0].startswith("# Resoconto del")
    assert "spendere meno di sera" in "\n".join(righe[:4]), documento[:200]

# ── Le misure in SERIE: la forma in cui l'analista le legge (§10) ───────────
#
# Misurato sulla casa vera il 15/09/2026, sui venti giorni archiviati:
# i resoconti come sono, trenta giorni, pesano ~47.600 token -- quattro volte
# il giro dell'osservatore, ogni giorno. Pivotati per misura: ~6.700. Sette
# volte meno, e non e' un'ottimizzazione: e' la frase della spec presa alla
# lettera, «le misure si leggono in serie, molti giorni insieme», ed e' l'unica
# forma su cui si puo' calcolare lo scostamento contro la storia di quel dato.


def _giorno(giorno, misure):
    return {"giorno": giorno, "obiettivo": None, "misure": misure,
            "forme": [], "cronaca": []}


def test_le_misure_si_leggono_in_serie_una_riga_per_misura():
    """Una riga per (soggetto, misura), coi suoi valori nell'ordine dei giorni.
    Il soggetto, l'operazione e l'unita' si scrivono **una volta**, non trenta.

    Mutazione: tornare una riga per giorno -- rossa.
    """
    serie = rep.series_of_measures([
        _giorno("2026-09-13", [{"soggetto": "dev1", "nome": "Inverter",
                                "misura": "produzione", "operazione": "somma_periodo",
                                "valore": 23.31, "unita": "kWh", "copertura": 1.0}]),
        _giorno("2026-09-12", [{"soggetto": "dev1", "nome": "Inverter",
                                "misura": "produzione", "operazione": "somma_periodo",
                                "valore": 21.47, "unita": "kWh", "copertura": 1.0}]),
    ])

    assert serie["giorni"] == ["2026-09-12", "2026-09-13"], "dal piu' vecchio"
    assert len(serie["serie"]) == 1
    riga = serie["serie"][0]
    assert riga["soggetto"] == "dev1"
    assert riga["nome"] == "Inverter"
    assert riga["misura"] == "produzione"
    assert riga["unita"] == "kWh"
    assert riga["valori"] == [21.47, 23.31]
    assert riga["coperture"] == [1.0, 1.0]


def test_un_valore_composto_diventa_TRE_serie_non_una_scelta_nascosta():
    """`media_min_max` torna `{media, minimo, massimo}`. Mettere in serie \u00abla
    media\u00bb sarebbe una regola che nessuno ha dichiarato -- e sarebbe sbagliata:
    media, minimo e massimo sono **tre storie diverse**, e \u00abil massimo di
    rumore e' salito\u00bb vale quanto \u00abla media e' salita\u00bb.

    Mutazione: prendere solo `media` -- rossa.
    """
    serie = rep.series_of_measures([
        _giorno("2026-09-13", [{"soggetto": "dev1", "misura": "rumore",
                                "operazione": "media_min_max", "unita": "dB",
                                "valore": {"media": 44.8, "minimo": 39.0,
                                           "massimo": 71.0}, "copertura": 1.0}]),
    ])

    chiavi = [r["chiave"] for r in serie["serie"]]
    assert chiavi == ["media", "minimo", "massimo"]
    assert [r["misura"] for r in serie["serie"]] == ["rumore"] * 3
    assert [r["valori"][0] for r in serie["serie"]] == [44.8, 39.0, 71.0]


def test_un_giorno_in_cui_la_misura_NON_c_era_resta_un_buco_col_suo_perche():
    """**Il terzo innesco.** Saltare i giorni senza valore renderebbe invisibile
    proprio cio' che l'analista deve vedere: «la copertura crolla», «una misura
    smette di essere calcolabile». Il caso vero e' `bilancio` a zero per cinque
    giorni su cinque, e nessuno se n'e' accorto.

    Il posto nella serie resta, col suo `None`, e il perche' si conserva.

    Mutazione: saltare i giorni senza valore -- rossa su `[None, 2.0]`.
    """
    serie = rep.series_of_measures([
        _giorno("2026-09-13", [{"soggetto": "dev1", "misura": "consumo",
                                "operazione": "somma_periodo", "valore": 2.0,
                                "unita": "kWh", "copertura": 1.0}]),
        _giorno("2026-09-12", [{"soggetto": "dev1", "misura": "consumo",
                                "operazione": "somma_periodo",
                                "non_calcolabile": "la serie e' vuota"}]),
    ])

    riga = serie["serie"][0]
    assert riga["valori"] == [None, 2.0]
    assert riga["coperture"] == [None, 1.0]
    assert riga["perche"] == [{"dal": "2026-09-12", "al": "2026-09-12",
                              "ragione": "la serie e' vuota"}]


def test_una_misura_che_esiste_solo_da_IERI_non_finge_una_storia():
    """Una ricetta scritta ieri non ha trenta giorni alle spalle, e la sua
    serie deve dirlo: i giorni prima sono `None`, non assenti. \u00abLa base e'
    sottile\u00bb e' un vincolo della spec, e si vede da qui.

    Mutazione: allineare la serie solo ai giorni in cui la misura c'era --
    rossa.
    """
    serie = rep.series_of_measures([
        _giorno("2026-09-13", [{"soggetto": "dev1", "misura": "nuova",
                                "operazione": "somma_periodo", "valore": 1.0,
                                "unita": "kWh", "copertura": 1.0}]),
        _giorno("2026-09-12", []),
        _giorno("2026-09-11", []),
    ])

    riga = serie["serie"][0]
    assert riga["valori"] == [None, None, 1.0]
    assert riga["perche"] == [], "un giorno in cui non c'era proprio non ha un perche'"


def test_le_serie_tornano_in_ordine_STABILE():
    """Due letture della stessa storia devono dare lo stesso ordine, o un
    modello che le rilegge vedrebbe un cambiamento dove non c'e'.

    Mutazione: iterare su un `set` -- rossa (a volte).
    """
    giorni = [_giorno("2026-09-13", [
        {"soggetto": "b", "misura": "x", "operazione": "somma_periodo",
         "valore": 1.0, "unita": "kWh", "copertura": 1.0},
        {"soggetto": "a", "misura": "y", "operazione": "somma_periodo",
         "valore": 2.0, "unita": "kWh", "copertura": 1.0}])]
    prima = [(r["soggetto"], r["misura"]) for r in rep.series_of_measures(giorni)["serie"]]
    dopo = [(r["soggetto"], r["misura"]) for r in rep.series_of_measures(giorni)["serie"]]
    assert prima == dopo == [("a", "y"), ("b", "x")]

def test_una_misura_composta_che_un_giorno_RIFIUTA_resta_tre_serie_non_quattro():
    """Il caso vero: `co2_tendenza` si calcola il 13 e rifiuta il 12. Il valore
    e' composto, quindi il giorno buono produce tre serie -- e il giorno del
    rifiuto non ne deve produrre una quarta, senza chiave, con il perche'
    staccato dai valori.

    Il perche' va su **tutte e tre**: quel giorno mancano tutte e tre, e chi
    guarda la storia del massimo deve vedere il buco nella SUA serie.

    Mutazione: attaccare il rifiuto a una riga senza chiave -- rossa (quattro
    serie invece di tre).
    """
    serie = rep.series_of_measures([
        _giorno("2026-09-13", [{"soggetto": "dev1", "misura": "co2",
                                "operazione": "media_min_max", "unita": "ppm",
                                "valore": {"media": 700.0, "minimo": 638.0,
                                           "massimo": 750.0}, "copertura": 1.0}]),
        _giorno("2026-09-12", [{"soggetto": "dev1", "misura": "co2",
                                "operazione": "media_min_max",
                                "non_calcolabile": "la serie e' vuota"}]),
    ])

    assert len(serie["serie"]) == 3, [r["chiave"] for r in serie["serie"]]
    for riga in serie["serie"]:
        assert riga["valori"][0] is None, riga["chiave"]
        assert riga["perche"] == [{"dal": "2026-09-12", "al": "2026-09-12",
                                   "ragione": "la serie e' vuota"}], riga["chiave"]
    assert [r["valori"][1] for r in serie["serie"]] == [700.0, 638.0, 750.0]


def test_una_misura_che_rifiuta_SEMPRE_ha_comunque_la_sua_riga():
    """`bilancio` a zero per cinque giorni su cinque, e nessuno se n'e'
    accorto: e' il caso che ha fatto nascere il terzo innesco. Una misura che
    non si calcola **mai** deve avere la sua riga, tutta vuota, coi suoi
    perche' -- sparire sarebbe il modo esatto in cui quel difetto e' rimasto
    invisibile.

    Mutazione: creare la riga solo quando c'e' almeno un valore -- rossa.
    """
    serie = rep.series_of_measures([
        _giorno("2026-09-13", [{"soggetto": "dev1", "misura": "bilancio",
                                "operazione": "somma_periodo",
                                "non_calcolabile": "statistiche non lette"}]),
        _giorno("2026-09-12", [{"soggetto": "dev1", "misura": "bilancio",
                                "operazione": "somma_periodo",
                                "non_calcolabile": "statistiche non lette"}]),
    ])

    assert len(serie["serie"]) == 1
    riga = serie["serie"][0]
    assert riga["valori"] == [None, None]
    assert len(riga["perche"]) == 1, riga["perche"]

def test_i_perche_uguali_di_giorni_contigui_diventano_UN_tratto():
    """**Misurato il 15/09/2026 sui venti giorni veri**: i `perche` erano il
    **66%** del peso della serie, ed erano ripetizioni -- 36 serie ripetevano
    la stessa frase 17 volte, tre la ripetevano 20. Raggruppando i tratti
    contigui: 18.150 token per trenta giorni invece di 44.163.

    E non e' solo il peso. \u00abNon si calcola dal 26/08 all'11/09, per questa
    ragione\u00bb e' il terzo innesco detto bene; diciassette righe identiche lo
    seppelliscono.

    Mutazione: tornare a una voce per giorno -- rossa.
    """
    giorni = [_giorno(g, [{"soggetto": "dev1", "misura": "co2",
                           "operazione": "media_min_max",
                           "non_calcolabile": "la serie e' vuota"}])
              for g in ("2026-09-10", "2026-09-11", "2026-09-12")]
    giorni.append(_giorno("2026-09-13", [
        {"soggetto": "dev1", "misura": "co2", "operazione": "media_min_max",
         "valore": 700.0, "unita": "ppm", "copertura": 1.0}]))

    riga = rep.series_of_measures(giorni)["serie"][0]
    assert riga["perche"] == [{"dal": "2026-09-10", "al": "2026-09-12",
                               "ragione": "la serie e' vuota"}]
    assert riga["valori"] == [None, None, None, 700.0]


def test_due_ragioni_DIVERSE_restano_due_tratti():
    """Raggruppare e' comprimere, non appiattire: due ragioni diverse sono due
    fatti diversi, e fonderli direbbe il falso su uno dei due.

    Mutazione: raggruppare per contiguita' ignorando la ragione -- rossa.
    """
    giorni = [
        _giorno("2026-09-11", [{"soggetto": "d", "misura": "x",
                                "operazione": "somma_periodo",
                                "non_calcolabile": "la serie e' vuota"}]),
        _giorno("2026-09-12", [{"soggetto": "d", "misura": "x",
                                "operazione": "somma_periodo",
                                "non_calcolabile": "copertura 8%"}]),
    ]
    assert rep.series_of_measures(giorni)["serie"][0]["perche"] == [
        {"dal": "2026-09-11", "al": "2026-09-11", "ragione": "la serie e' vuota"},
        {"dal": "2026-09-12", "al": "2026-09-12", "ragione": "copertura 8%"},
    ]


def test_un_buco_che_si_riapre_dopo_un_giorno_buono_e_un_tratto_NUOVO():
    """Se in mezzo la misura si e' calcolata, sono due assenze distinte -- e
    l'analista deve vedere che era tornata e se n'e' andata di nuovo, non un
    unico buco lungo che non c'e' mai stato.

    Mutazione: chiudere il tratto solo al cambio di ragione -- rossa (un
    tratto invece di due).
    """
    giorni = [
        _giorno("2026-09-11", [{"soggetto": "d", "misura": "x",
                                "operazione": "somma_periodo",
                                "non_calcolabile": "vuota"}]),
        _giorno("2026-09-12", [{"soggetto": "d", "misura": "x",
                                "operazione": "somma_periodo", "valore": 1.0,
                                "unita": "kWh", "copertura": 1.0}]),
        _giorno("2026-09-13", [{"soggetto": "d", "misura": "x",
                                "operazione": "somma_periodo",
                                "non_calcolabile": "vuota"}]),
    ]
    tratti = rep.series_of_measures(giorni)["serie"][0]["perche"]
    assert len(tratti) == 2, tratti
    assert tratti[0]["al"] == "2026-09-11"
    assert tratti[1]["dal"] == "2026-09-13"

def test_la_serie_dice_QUANDO_la_domanda_e_cambiata():
    """**Il vincolo della spec §11, nella forma che l'analista legge.** Senza,
    leggerebbe una tendenza dove invece \u00e8 cambiata la domanda: trenta giorni
    di \u00abautosufficienza in calo\u00bb possono essere un impianto che peggiora o un
    obiettivo riscritto a met\u00e0.

    Si raggruppa come i buchi -- un tratto per ogni obiettivo -- perch\u00e9
    l'obiettivo cambia qualche volta all'anno, non ogni giorno: ripeterlo
    trenta volte sarebbe la stessa ripetizione che i `perche` hanno gi\u00e0
    pagato.

    Mutazione: non mettere `obiettivi` nella serie -- rossa.
    """
    serie = rep.series_of_measures([
        {"giorno": "2026-09-11", "obiettivo": {"testo": "prima", "scritto_ts": 1.0},
         "misure": [], "forme": [], "cronaca": []},
        {"giorno": "2026-09-12", "obiettivo": {"testo": "prima", "scritto_ts": 1.0},
         "misure": [], "forme": [], "cronaca": []},
        {"giorno": "2026-09-13", "obiettivo": {"testo": "dopo", "scritto_ts": 2.0},
         "misure": [], "forme": [], "cronaca": []},
    ])

    assert serie["obiettivi"] == [
        {"dal": "2026-09-11", "al": "2026-09-12", "testo": "prima", "scritto_ts": 1.0},
        {"dal": "2026-09-13", "al": "2026-09-13", "testo": "dopo", "scritto_ts": 2.0},
    ]


def test_i_giorni_senza_obiettivo_dichiarato_non_ne_inventano_uno():
    """Un resoconto nato prima che la riga esistesse porta `None`, e resta
    `None`: attribuirgli l'obiettivo del giorno dopo sarebbe dire che quel
    giorno rispondeva a una domanda che non era la sua.

    Mutazione: far proseguire il tratto sopra i giorni senza obiettivo --
    rossa.
    """
    serie = rep.series_of_measures([
        {"giorno": "2026-09-11", "obiettivo": {"testo": "x", "scritto_ts": 1.0},
         "misure": [], "forme": [], "cronaca": []},
        {"giorno": "2026-09-12", "obiettivo": None,
         "misure": [], "forme": [], "cronaca": []},
        {"giorno": "2026-09-13", "obiettivo": {"testo": "x", "scritto_ts": 1.0},
         "misure": [], "forme": [], "cronaca": []},
    ])

    assert [t["dal"] for t in serie["obiettivi"]] == ["2026-09-11", "2026-09-13"]

def test_la_serie_risolve_i_nomi_che_il_resoconto_non_aveva():
    """**L'archivio dice cio' che sapeva; il lettore risolve cio' che puo'
    oggi.** I venti giorni archiviati sulla casa vera prima del 15/09/2026 non
    portano il nome del dispositivo -- lo cancellava un difetto -- e riscriverli
    sarebbe inventare cosa sapevamo allora.

    La serie invece e' una **vista**, non un archivio: risolvere il nome qui
    non afferma niente sul passato, e all'analista arriva «SOLARE · prelievo»
    invece di «513a6661 · prelievo» su tutti i giorni insieme.

    Mutazione: ignorare `names` -- rossa.
    """
    serie = rep.series_of_measures([
        {"giorno": "2026-09-13", "obiettivo": None, "forme": [], "cronaca": [],
         "misure": [{"soggetto": "dev1", "misura": "prelievo",
                     "operazione": "somma_periodo", "valore": 1.0,
                     "unita": "kWh", "copertura": 1.0}]},
    ], names={"dev1": "SOLARE"})

    assert serie["serie"][0]["nome"] == "SOLARE"


def test_il_nome_ARCHIVIATO_vince_su_quello_di_oggi():
    """Se il resoconto un nome ce l'ha, quello e' il nome che il dispositivo
    aveva **allora**, ed e' piu' vero di quello di adesso: un dispositivo si
    puo' rinominare, e la serie non deve riscrivere il passato col presente.

    Mutazione: far vincere `names` -- rossa.
    """
    serie = rep.series_of_measures([
        {"giorno": "2026-09-13", "obiettivo": None, "forme": [], "cronaca": [],
         "misure": [{"soggetto": "dev1", "nome": "come si chiamava allora",
                     "misura": "prelievo", "operazione": "somma_periodo",
                     "valore": 1.0, "unita": "kWh", "copertura": 1.0}]},
    ], names={"dev1": "come si chiama adesso"})

    assert serie["serie"][0]["nome"] == "come si chiamava allora"


def test_senza_nomi_la_serie_non_ne_inventa():
    """Un dispositivo di cui **non sappiamo** il nome resta senza: chi legge
    vede l'identificatore, che e' la verita', non un buco.

    **La prima stesura passava `names=None`, e il ramo non girava mai**: la
    mutazione «metti il soggetto come nome di ripiego» sopravviveva. Si passa
    una mappa che c'e' e che quel soggetto non ce l'ha -- e' la condizione
    vera, e la casa vera la produce ogni volta che un dispositivo esce dal
    registro e i suoi resoconti restano.

    Mutazione: mettere il soggetto come nome di ripiego -- rossa.
    """
    serie = rep.series_of_measures([
        {"giorno": "2026-09-13", "obiettivo": None, "forme": [], "cronaca": [],
         "misure": [{"soggetto": "dev1", "misura": "prelievo",
                     "operazione": "somma_periodo", "valore": 1.0,
                     "unita": "kWh", "copertura": 1.0}]},
    ], names={"un_altro_dispositivo": "SOLARE"})
    assert serie["serie"][0]["nome"] is None
