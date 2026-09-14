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

def test_il_resoconto_porta_il_suo_giorno_e_le_due_parti():
    r = rep.build_report(day="2026-09-13", episodes=EPISODI, series=SERIE,
                         recipes={"dev1": RICETTA}, names={})

    assert r["giorno"] == "2026-09-13"
    assert set(r) == {"giorno", "misure", "cronaca"}


def test_un_giorno_SENZA_NIENTE_e_un_resoconto_vuoto_non_un_errore():
    """Una casa spenta produce un resoconto vuoto, e va scritto lo stesso: «quel
    giorno non e' successo niente» e «quel giorno non l'abbiamo guardato» sono
    due cose diverse, e l'analista deve poterle distinguere."""
    r = rep.build_report(day="2026-09-13", episodes=[], series={},
                         recipes={}, names={})

    assert r == {"giorno": "2026-09-13", "misure": [], "cronaca": []}


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
