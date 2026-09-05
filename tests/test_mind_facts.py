"""L'aggregazione: dai cambi agli oggetti.

**E' l'unico posto di questa fetta dove si giudica**, ed e' apposta: un
giudizio qui si rifa' finche' il grezzo esiste (22 giorni: 21 di promessa,
uno di guardia), uno in scrittura non si corregge piu'.

Un oggetto e' **una cosa compiuta della casa**: qualcosa che e' cominciato, e'
durato, e' finito -- con dentro chi lo ha fatto e cosa c'era attorno.
"""
import os

import pytest

from hiris.app.mind.facts import GENRES, aggregate_day, day_boundaries, genre_for
from hiris.app.mind.store import ObservationsStore

# 24 agosto 2026: mezzanotte a Roma e' 22:00 UTC del 23.
G = "2026-08-24"
MEZZANOTTE = 1787522400.0   # 2026-08-23T22:00:00+00:00 = 24/08 00:00 +02:00


def ts(ore, minuti=0):
    return MEZZANOTTE + ore * 3600 + minuti * 60


@pytest.fixture()
def archivio(tmp_path):
    a = ObservationsStore(os.path.join(str(tmp_path), "o.db"))
    yield a
    a.close()


def test_il_genere_discende_dalla_natura():
    assert genre_for("climate.camera_t", "comfort") == "funzionamento"
    assert genre_for("cover.tapparella", "dispersione") == "funzionamento"
    assert genre_for("person.marta", "chi c'e'") == "presenza"
    assert genre_for("sensor.presa_energia", "energia") == "energia"
    assert genre_for("problema:sonos.x", None) == "guasto"
    assert genre_for("sensor.camera_temperatura", "comfort") is None
    for g in GENRES:
        assert isinstance(g, str)


def test_il_genere_di_sicurezza_e_diverso_dal_guasto_di_sistema():
    """Correzione 0.1: 'guasto' resta per le condizioni di SISTEMA
    (problema:/integrazione:, un confine netto); la gamba sicurezza ha un
    genere proprio, 'sicurezza' -- una porta aperta con la chiave e
    un'integrazione Sonos rotta non sono lo stesso genere di fatto."""
    assert genre_for("lock.porta_ingresso", "sicurezza") == "sicurezza"
    assert genre_for("problema:sonos.x", None) == "guasto"
    assert genre_for("integrazione:abc", None) == "guasto"
    assert "sicurezza" in GENRES
    # Sei generi, non cinque (27/08/2026, mandato «il bilancio
    # dell'energia»): "bilancio" e' nato in GENRES, ma non lo produce
    # `genre_for()` -- non nasce da un soggetto/gamba come gli altri
    # cinque, arriva gia' costruito da fuori (`aggregate_day(bilanci=...)`,
    # vedi `test_mind_balance.py`).
    assert len(GENRES) == 6
    assert "bilancio" in GENRES


def test_un_termostato_acceso_e_spento_diventa_UN_oggetto(archivio):
    archivio.record(quando_ts=ts(15, 30), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    archivio.record(quando_ts=ts(17, 5), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = archivio.facts(day=G)[0]
    assert o["genere"] == "funzionamento"
    assert o["protagonista"] == "climate.camera_t"
    assert o["inizio_ts"] == ts(15, 30)
    assert o["fine_ts"] == ts(17, 5)


def test_l_oggetto_porta_cosa_ha_fatto_la_temperatura_mentre_durava(archivio):
    """E' il senso dell'esempio fondativo: «la casa e' calda alle 16:30» non e'
    un fatto sul termostato ne' sul sensore -- e' il legame fra i due."""
    archivio.record(quando_ts=ts(15, 30), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    for ora, valore in ((15, "18.2"), (16, "20.1"), (17, "21.0")):
        archivio.record(quando_ts=ts(ora, 45), source="entita",
                        subject="sensor.camera_temperatura", da=None, a=valore)
    archivio.record(quando_ts=ts(17, 5), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome",
                         companions=lambda s: ["sensor.camera_temperatura"])
    corpo = archivio.facts(day=G)[0]["corpo"]
    assert corpo["comprimari"] == ["sensor.camera_temperatura"]
    assert corpo["misure"]["sensor.camera_temperatura"] == {"da": "18.2", "a": "21.0"}


def test_una_cosa_ancora_in_corso_a_mezzanotte_resta_aperta(archivio):
    archivio.record(quando_ts=ts(22, 0), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    assert archivio.facts(day=G)[0]["fine_ts"] is None


def test_un_assenza_e_un_oggetto(archivio):
    archivio.record(quando_ts=ts(8, 10), source="entita",
                    subject="person.paolo", da="home", a="not_home")
    archivio.record(quando_ts=ts(17, 34), source="entita",
                    subject="person.paolo", da="not_home", a="home")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    o = archivio.facts(day=G)[0]
    assert o["genere"] == "presenza"
    assert o["corpo"]["stato"] == "not_home"


def test_un_cambio_di_zona_a_meta_assenza_non_riapre_l_oggetto(archivio):
    """La settima finta (mandato, punto 1): la guardia del ramo presenza
    (`elif subject not in open_episodes`) impedisce che un cambio di ZONA a meta'
    di un'assenza -- le zone sono stati VERI di una `person`, non solo
    "home"/"not_home" -- riapra l'oggetto azzerandone inizio e stato. Paolo
    esce di casa alle 8:10 ("not_home"), entra in una zona ("ufficio") alle
    9:00, rientra alle 17:34: l'assenza vera dura dalle 8:10 alle 17:34, con
    stato "not_home" -- non dalle 9:00, con stato "ufficio".

    Mutazione ESEGUITA e verificata rossa: `elif subject not in open_episodes:`
    -> `else:` nel ramo presenza -- il cambio di zona delle 9:00 riapre
    l'oggetto, e inizio_ts/stato tornano ts(9,0)/"ufficio" invece di
    ts(8,10)/"not_home"."""
    archivio.record(quando_ts=ts(8, 10), source="entita",
                    subject="person.paolo", da="home", a="not_home")
    archivio.record(quando_ts=ts(9, 0), source="entita",
                    subject="person.paolo", da="not_home", a="ufficio")
    archivio.record(quando_ts=ts(17, 34), source="entita",
                    subject="person.paolo", da="ufficio", a="home")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = archivio.facts(day=G)[0]
    assert o["genere"] == "presenza"
    assert o["inizio_ts"] == ts(8, 10)
    assert o["fine_ts"] == ts(17, 34)
    assert o["corpo"]["stato"] == "not_home"


def test_un_guasto_di_sistema_e_un_oggetto(archivio):
    archivio.record(quando_ts=ts(9, 0), source="sistema",
                    subject="problema:sonos.subscriptions_failed", da=None, a="aperto")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    o = archivio.facts(day=G)[0]
    assert o["genere"] == "guasto"
    assert o["fine_ts"] is None


def test_a_fault_body_says_which_condition_not_the_word_open(archivio):
    """Ogni oggetto di guasto in archivio diceva `stato: "aperto"`, anche
    quelli chiusi: `setup_retry` e `setup_error` non sono la stessa cosa, e
    un campo che non varia mai non e' un fatto -- contraddice i timestamp
    che gli stanno accanto.

    Mutazione: rimettere la costante `"aperto"` al posto di `r["a"]` -- il
    test torna rosso su `assert corpo["stato"] == "setup_retry"`.
    """
    archivio.record(quando_ts=ts(9, 0), source="sistema",
                    subject="integrazione:01ABC", da=None, a="setup_retry",
                    domain="lifx", title="Abat-jour")
    archivio.record(quando_ts=ts(11, 30), source="sistema",
                    subject="integrazione:01ABC", da="setup_retry", a="chiuso")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    o = archivio.facts(day=G)[0]
    assert o["genere"] == "guasto"
    assert o["fine_ts"] is not None
    corpo = o["corpo"]
    assert corpo["stato"] == "setup_retry"
    assert corpo["dominio"] == "lifx"
    assert corpo["titolo"] == "Abat-jour"


def test_an_old_row_saying_open_still_opens_an_episode(archivio):
    """Le righe scritte prima della migrazione 3 portano ancora `"aperto"`
    e devono continuare ad aprire: la convenzione nuova e' «chiude solo
    "chiuso"», quindi non serve nessun caso a parte. E' cio' che rende
    superflua la convivenza che la spec ipotizzava.

    Mutazione: chiudere su qualunque valore diverso da una condizione nota
    -- nessun oggetto nasce: `archivio.facts(day=G)` e' vuoto, e il test
    torna rosso su un `IndexError` nell'indicizzare `[0]`, prima di
    arrivare a nessuno degli `assert`.
    """
    archivio.record(quando_ts=ts(9, 0), source="sistema",
                    subject="integrazione:01OLD", da=None, a="aperto")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    o = archivio.facts(day=G)[0]
    assert o["genere"] == "guasto"
    assert o["corpo"]["stato"] == "aperto"
    assert o["corpo"].get("dominio") is None


def test_a_fault_still_open_at_midnight_keeps_its_condition_and_domain(archivio):
    """Il caso piu' frequente in produzione: un'integrazione si rompe e resta
    rotta, senza nessuna riga di chiusura nella giornata. L'episodio si
    chiude solo a fine giornata (`close(subject, None)`, come ogni oggetto
    ancora in corso a mezzanotte) e passa dallo STESSO `close()` di un
    guasto chiuso in giornata -- rischio basso, ma non provato finche' non
    c'e' una prova apposta.

    Mutazione: nella chiusura di fine giornata, costruire il corpo senza
    ricopiare `dominio`/`titolo` (come se il percorso "ancora aperto"
    bypassasse `close()`) -- il test torna rosso su
    `assert corpo["dominio"] == "lifx"`.
    """
    archivio.record(quando_ts=ts(9, 0), source="sistema",
                    subject="integrazione:01XYZ", da=None, a="setup_error",
                    domain="lifx", title="Abat-jour")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    o = archivio.facts(day=G)[0]
    assert o["genere"] == "guasto"
    assert o["fine_ts"] is None
    corpo = o["corpo"]
    assert corpo["stato"] == "setup_error"
    assert corpo["dominio"] == "lifx"
    assert corpo["titolo"] == "Abat-jour"


def test_i_sensori_da_soli_NON_generano_oggetti(archivio):
    """«La temperatura e' salita» da sola non e' una cosa compiuta: e' il
    CONTESTO di qualcosa che e' successo. Se generasse oggetti, una giornata
    ne produrrebbe migliaia e nessuno sarebbe leggibile."""
    for ora in range(20):
        archivio.record(quando_ts=ts(ora), source="entita",
                        subject="sensor.camera_temperatura", da=None, a=str(18 + ora))
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 0


def test_rifare_un_giorno_non_raddoppia(archivio):
    """Il grezzo resta 22 giorni proprio perche' l'aggregazione si possa
    rifare. Se rifarla duplicasse, quella possibilita' non esisterebbe."""
    archivio.record(quando_ts=ts(15), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    assert len(archivio.facts(day=G)) == 1


def test_il_giorno_e_quello_della_CASA_non_UTC(archivio):
    """Le 23:30 di Roma sono le 21:30 UTC: un giorno calcolato in UTC
    spezzerebbe ogni serata in due. La fetta dello schedulatore ha gia' pagato
    un difetto di orologi diversi."""
    archivio.record(quando_ts=ts(23, 30), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1


def test_senza_fuso_noto_non_si_inventa(archivio):
    """`sistema_di_riferimento()` puo' non aver mai letto la casa. UTC e'
    dichiarato; un fuso inventato sposterebbe i giorni senza dirlo.

    Correzione (giro di review, punto 1): la versione precedente usava
    `ts(15)`, mezzogiorno abbondante -- un istante che cade dentro la
    giornata sia in UTC sia in un fuso inventato, quindi il test passava in
    entrambi i casi e provava solo che `timezone=None` non facesse crashare.

    **Cambio a `ts(1)`**: le 23:00Z del 23 agosto, che cade FRA le due
    mezzanotti. In UTC appartiene a "2026-08-23". Con un fuso inventato
    (es. `Europe/Rome`, +02:00) apparterrebbe gia' al 24: il conteggio del 23
    tornerebbe zero. E' la mutazione -- far tornare a `home_space_zone(None)` un
    `ZoneInfo("Europe/Rome")` -- che questo test deve rilevare."""
    archivio.record(quando_ts=ts(1), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    assert aggregate_day(store=archivio, day="2026-08-23", timezone=None) == 1


# -- Correzione B: la finestra di `cambi()` e' semi-aperta -----------------

def test_un_cambio_a_mezzanotte_appartiene_al_giorno_che_comincia(archivio):
    """MEZZANOTTE e' l'istante esatto in cui G comincia. Con la finestra
    semi-aperta di `archivio.cambi` (`[from_ts, to_ts)`) un cambio a quell'
    istante deve finire SOLO in G, mai nel giorno che finisce in quell'
    istante, e mai in entrambi -- altrimenti sarebbe contato due volte."""
    archivio.record(quando_ts=MEZZANOTTE, source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    assert aggregate_day(store=archivio, day="2026-08-23",
                          timezone="Europe/Rome") == 0
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1


# -- Correzione E: il pavimento ha sei gambe, la sicurezza non e' un buco --
# -- Correzione 0.1: la sicurezza e' un genere proprio, non piu' 'guasto' --

def test_il_genere_conosce_tutte_e_sei_le_gambe():
    """Le nature risolvibili dal solo dominio -- serratura, pannello
    dell'allarme, sirena -- e i rilevatori (quando la gamba e' nota) diventano
    un oggetto di sicurezza: sono una minaccia, non un funzionamento normale,
    e hanno la stessa FORMA di una condizione di sistema -- nate, durate,
    chiuse o ancora aperte -- ma non lo STESSO genere (0.1: una porta aperta
    con la chiave e un'integrazione Sonos rotta non sono la stessa cosa). Un
    `else` che le mandasse a vuoto sarebbe il buco che la review del primo
    task ha gia' trovato una volta (§4 della spec).

    `sensor.co_soggiorno` e' `None` e non `"sicurezza"` da questa correzione
    (giro di review, punto 7): e' un `sensor` che MISURA (una concentrazione
    numerica), non un `binary_sensor` che SCATTA -- vedi il docstring di
    `genre_for` per la ragione per cui resta fuori."""
    assert genre_for("lock.porta_ingresso", "sicurezza") == "sicurezza"
    assert genre_for("alarm_control_panel.casa", "sicurezza") == "sicurezza"
    assert genre_for("siren.sirena_esterna", "sicurezza") == "sicurezza"
    assert genre_for("binary_sensor.fumo_cucina", "sicurezza") == "sicurezza"
    assert genre_for("sensor.co_soggiorno", "sicurezza") is None


def test_una_sirena_che_suona_e_rientra_e_un_oggetto_di_sicurezza(archivio):
    """Lo scenario che la spec §4 chiama il buco peggiore possibile: un
    allarme che scatta e rientra deve diventare un oggetto con la sua durata,
    non sparire come sarebbe successo prima che la sesta gamba esistesse."""
    archivio.record(quando_ts=ts(3, 15), source="entita",
                    subject="siren.sirena_esterna", da="off", a="on")
    archivio.record(quando_ts=ts(3, 20), source="entita",
                    subject="siren.sirena_esterna", da="on", a="off")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = archivio.facts(day=G)[0]
    assert o["genere"] == "sicurezza"
    assert o["inizio_ts"] == ts(3, 15)
    assert o["fine_ts"] == ts(3, 20)


def test_una_serratura_sbloccata_e_richiusa_e_un_oggetto_di_sicurezza(archivio):
    """Lock e pannello dell'allarme non usano il vocabolario on/off: qui la
    prova che «locked» chiude l'episodio esattamente come «off» lo fa per gli
    altri, e che «unlocked» lo tiene aperto."""
    archivio.record(quando_ts=ts(22, 0), source="entita",
                    subject="lock.porta_ingresso", da="locked", a="unlocked")
    archivio.record(quando_ts=ts(22, 5), source="entita",
                    subject="lock.porta_ingresso", da="unlocked", a="locked")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = archivio.facts(day=G)[0]
    assert o["genere"] == "sicurezza"
    assert o["inizio_ts"] == ts(22, 0)
    assert o["fine_ts"] == ts(22, 5)


# -- Task 3, punto 0: il grezzo porta le tre classi che il pavimento legge --
#
# Prima di questa correzione, `_reading_aspect` chiamava `pavimento.aspect`
# SENZA attributi: per `sensor`/`binary_sensor` (che decidono la gamba dalla
# classe, non dal dominio) la gamba tornava sempre `None`. Conseguenza
# misurata: il genere `energia` non nasceva MAI, e nemmeno un solo oggetto
# per fumo, gas, monossido, allagamento, manomissione -- la gamba "sicurezza"
# restava raggiungibile solo per serrature, sirene e pannello dell'allarme.

def test_un_binary_sensor_di_fumo_diventa_un_oggetto_di_sicurezza(archivio):
    """La mutazione e' non passare le classi a `aspect` dentro
    `_reading_aspect`: senza `device_class="smoke"`, `pavimento.aspect`
    tornerebbe `None` per un `binary_sensor`, `genre_for` tornerebbe `None`, e
    questo oggetto -- oggi impossibile -- non nascerebbe."""
    archivio.record(quando_ts=ts(2, 0), source="entita",
                    subject="binary_sensor.fumo_cucina", da="off", a="on",
                    device_class="smoke")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = archivio.facts(day=G)[0]
    assert o["genere"] == "sicurezza"
    assert o["protagonista"] == "binary_sensor.fumo_cucina"


def test_un_sensor_di_energia_diventa_un_oggetto_di_energia(archivio):
    """Il genere `energia` non nasceva mai (punto 0 del mandato): stessa
    mutazione del test gemello sul fumo, sul dominio `sensor`."""
    archivio.record(quando_ts=ts(2, 0), source="entita",
                    subject="sensor.energia_casa", da=None, a="1234.5",
                    device_class="energy")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = archivio.facts(day=G)[0]
    assert o["genere"] == "energia"
    assert o["protagonista"] == "sensor.energia_casa"


def test_riga_senza_le_tre_colonne_non_fa_sollevare_l_aggregazione(archivio):
    """Il grezzo gia' in casa, scritto prima di questa correzione, non porta
    le tre classi: le colonne sono annullabili apposta perche' continui a
    rileggersi senza far sollevare `aggregate_day`."""
    archivio.record(quando_ts=ts(2, 0), source="entita",
                    subject="binary_sensor.fumo_cucina", da="off", a="on")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 0


# -- Giro di correzioni dopo la review (2026-08-26) -------------------------

# -- Punto 2: la presenza non deve fabbricare oggetti a ogni riavvio di HA --

def test_un_riavvio_di_ha_non_apre_un_oggetto_di_presenza(archivio):
    """Il ramo `presenza` controllava solo `r["a"] == "home"`: qualunque
    altro valore apriva un oggetto, compresi `unavailable` e `unknown`. A
    ogni riavvio di Home Assistant le `person` ci passano, quindi nasceva un
    oggetto <<presenza, stato unavailable>> di un minuto per ogni persona, a
    ogni riavvio. Mutazione: togliere il filtro `_UNKNOWN` dal ramo
    `presenza` -- il conteggio tornerebbe 1 invece di 0."""
    archivio.record(quando_ts=ts(9, 0), source="entita",
                    subject="person.paolo", da="home", a="unavailable")
    archivio.record(quando_ts=ts(9, 1), source="entita",
                    subject="person.paolo", da="unavailable", a="home")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 0


# -- Punto 3b: il riposo di un pannello d'allarme e' ARMATO, non disarmato --

def test_l_allarme_inserito_non_apre_un_oggetto(archivio):
    """Inserire l'allarme la sera e' la cosa che va bene: deve chiudere,
    mai aprire. Mutazione: rimettere "disarmed" in `_RESTING` e togliere gli
    "armed_*" -- "armed_home" tornerebbe "acceso" e aprirebbe un oggetto che
    non chiuderebbe mai in giornata."""
    archivio.record(quando_ts=ts(22, 0), source="entita",
                    subject="alarm_control_panel.casa", da="disarmed",
                    a="armed_home")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 0


def test_l_allarme_disinserito_per_otto_ore_apre_un_oggetto(archivio):
    """La casa lasciata senza allarme e' la cosa NOTEVOLE: otto ore da
    "disarmed" a "armed_home" devono produrre un oggetto con quella durata.
    Stessa mutazione del test gemello: con "disarmed" in `_RESTING` questa
    riga chiuderebbe (nessun oggetto aperto) invece di aprirne uno."""
    archivio.record(quando_ts=ts(1, 0), source="entita",
                    subject="alarm_control_panel.casa", da="armed_home",
                    a="disarmed")
    archivio.record(quando_ts=ts(9, 0), source="entita",
                    subject="alarm_control_panel.casa", da="disarmed",
                    a="armed_home")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = archivio.facts(day=G)[0]
    assert o["genere"] == "sicurezza"
    assert o["inizio_ts"] == ts(1, 0)
    assert o["fine_ts"] == ts(9, 0)


# -- Punto 5: le misure non sconfinano nel prossimo episodio, ne' partono --
# -- prima dell'inizio dell'oggetto -----------------------------------------

def test_le_misure_non_sconfinano_nel_prossimo_episodio_dello_stesso_protagonista(archivio):
    """Riscaldamento acceso 15:30-17:05 e di nuovo 19:00-20:00, temperature
    misurate fino alle 23:00: il PRIMO episodio non deve riportare come
    temperatura finale quella delle 23:00 -- e' il clima del secondo
    episodio e oltre. Il limite superiore vero e' l'inizio del prossimo
    oggetto dello STESSO protagonista, non la fine della giornata.
    Mutazione: usare sempre `to_ts` come limite superiore -- il primo
    episodio finirebbe con "a": "17.0" invece di "19.0"."""
    archivio.record(quando_ts=ts(15, 30), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    archivio.record(quando_ts=ts(16, 0), source="entita",
                    subject="sensor.camera_temperatura", da=None, a="19.0")
    archivio.record(quando_ts=ts(17, 5), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    archivio.record(quando_ts=ts(19, 0), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    archivio.record(quando_ts=ts(19, 30), source="entita",
                    subject="sensor.camera_temperatura", da=None, a="20.5")
    archivio.record(quando_ts=ts(20, 0), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    archivio.record(quando_ts=ts(23, 0), source="entita",
                    subject="sensor.camera_temperatura", da=None, a="17.0")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome",
                   companions=lambda s: ["sensor.camera_temperatura"])
    oggetti = sorted(archivio.facts(day=G), key=lambda o: o["inizio_ts"])
    assert len(oggetti) == 2
    primo, secondo = oggetti
    assert primo["corpo"]["misure"]["sensor.camera_temperatura"] == {
        "da": "19.0", "a": "19.0"}
    assert secondo["corpo"]["misure"]["sensor.camera_temperatura"] == {
        "da": "20.5", "a": "17.0"}


def test_le_misure_non_includono_letture_precedenti_all_inizio_dell_oggetto(archivio):
    """Una misura delle 14:00, prima che il riscaldamento si accenda alle
    15:30, non deve finire come valore INIZIALE dell'episodio: e' il clima
    di prima, non quello di mentre l'oggetto durava. Mutazione: togliere il
    confine inferiore (`e["inizio"] <= t`) -- la misura delle 14:00
    entrerebbe e "da" diventerebbe "14.0" invece di "18.2"."""
    archivio.record(quando_ts=ts(14, 0), source="entita",
                    subject="sensor.camera_temperatura", da=None, a="14.0")
    archivio.record(quando_ts=ts(15, 30), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    archivio.record(quando_ts=ts(16, 0), source="entita",
                    subject="sensor.camera_temperatura", da=None, a="18.2")
    archivio.record(quando_ts=ts(17, 5), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome",
                   companions=lambda s: ["sensor.camera_temperatura"])
    o = archivio.facts(day=G)[0]
    assert o["corpo"]["misure"]["sensor.camera_temperatura"] == {
        "da": "18.2", "a": "18.2"}


# -- Punto 6: un'energia si CHIUDE e porta iniziale/finale/differenza ------

def test_un_energia_si_chiude_e_porta_iniziale_finale_e_differenza(archivio):
    """Prima di questa correzione un contatore apriva un oggetto al primo
    cambio e non lo chiudeva MAI dentro la giornata: un oggetto
    perennemente aperto, con dentro solo la prima lettura, per ognuno dei
    29 contatori della casa. Mutazione: tornare al vecchio ramo "apri se non
    gia' aperto, mai chiudere" -- `fine_ts` tornerebbe `None` e il corpo
    non porterebbe piu' "valore_iniziale"/"valore_finale"/"differenza"."""
    archivio.record(quando_ts=ts(1), source="entita",
                    subject="sensor.energia_casa", da=None, a="100.0",
                    device_class="energy")
    archivio.record(quando_ts=ts(12), source="entita",
                    subject="sensor.energia_casa", da=None, a="115.0",
                    device_class="energy")
    archivio.record(quando_ts=ts(23), source="entita",
                    subject="sensor.energia_casa", da=None, a="130.5",
                    device_class="energy")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = archivio.facts(day=G)[0]
    assert o["genere"] == "energia"
    assert o["inizio_ts"] == ts(1)
    assert o["fine_ts"] == ts(23)
    assert o["corpo"]["valore_iniziale"] == "100.0"
    assert o["corpo"]["valore_finale"] == "130.5"
    assert o["corpo"]["differenza"] == pytest.approx(30.5)


# -- Punto 7: un sensor numerico di monossido non genera un guasto perenne --

def test_un_sensore_co_numerico_non_genera_un_oggetto_di_sicurezza(archivio):
    """Un `sensor` MISURA, non SCATTA: senza una soglia onesta, una
    concentrazione come "0.4" non e' mai in `_RESTING` e aprirebbe un oggetto
    di sicurezza perennemente aperto al giorno, per ogni sensore CO
    numerico della casa. Mutazione: togliere l'eccezione `dominio ==
    "sensor"` dal ramo sicurezza di `genre_for` -- il conteggio tornerebbe
    1 invece di 0."""
    archivio.record(quando_ts=ts(2), source="entita",
                    subject="sensor.co_soggiorno", da=None, a="0.4",
                    device_class="carbon_monoxide")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 0


# -- Punto 8: tre finte e un elenco che non sapevano produrre il difetto ---

def _comprimari_per_soggetto(soggetto):
    """Finta che DISCRIMINA per soggetto -- non un `lambda s: [...]`
    costante, che passerebbe anche se `aggregate_day` chiamasse
    `comprimari` con il soggetto SBAGLIATO (es. sempre il primo
    protagonista incontrato nel giorno)."""
    return {
        "climate.camera_t": ["sensor.camera_temperatura"],
        "climate.soggiorno_t": ["sensor.soggiorno_temperatura"],
    }.get(soggetto, [])


def test_comprimari_riceve_il_soggetto_giusto_non_uno_qualunque(archivio):
    """Se `aggregate_day` chiamasse `comprimari` con un soggetto sbagliato,
    i due oggetti scambierebbero i comprimari: questa finta lo scoprirebbe
    perche' torna elenchi DIVERSI per soggetti diversi, dove una finta
    costante (`lambda s: [...]`) non lo scoprirebbe mai. Mutazione provata:
    dentro `aggregate_day`, chiamare `companions(subject)` passando sempre
    la stringa fissa "climate.camera_t" invece di `e["protagonista"]` --
    l'oggetto di "climate.soggiorno_t" riceverebbe i comprimari sbagliati."""
    archivio.record(quando_ts=ts(10), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    archivio.record(quando_ts=ts(10, 30), source="entita",
                    subject="sensor.camera_temperatura", da=None, a="20.0")
    archivio.record(quando_ts=ts(11), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    archivio.record(quando_ts=ts(12), source="entita",
                    subject="climate.soggiorno_t", da="off", a="heat")
    archivio.record(quando_ts=ts(12, 30), source="entita",
                    subject="sensor.soggiorno_temperatura", da=None, a="22.0")
    archivio.record(quando_ts=ts(13), source="entita",
                    subject="climate.soggiorno_t", da="heat", a="off")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome",
                   companions=_comprimari_per_soggetto)
    oggetti = {o["protagonista"]: o for o in archivio.facts(day=G)}
    assert oggetti["climate.camera_t"]["corpo"]["comprimari"] == [
        "sensor.camera_temperatura"]
    assert oggetti["climate.soggiorno_t"]["corpo"]["comprimari"] == [
        "sensor.soggiorno_temperatura"]


def test_il_confine_di_inizio_esclude_l_istante_prima_di_mezzanotte(archivio):
    """MEZZANOTTE - 1 e' l'ultimo istante del giorno che finisce: deve
    restare FUORI da G. Mutazione: `from_ts - 1` dentro `day_boundaries` ("per
    stare sicuri") -- l'istante entrerebbe in G per errore, e il conteggio
    di G tornerebbe 1 invece di 0."""
    archivio.record(quando_ts=MEZZANOTTE - 1, source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 0
    assert aggregate_day(store=archivio, day="2026-08-23",
                          timezone="Europe/Rome") == 1


def test_gas_sensor_e_gas_rilevatore_non_si_confondono(archivio):
    """La trappola che il pavimento tiene separata per dominio: `sensor`
    classe `gas` e' un CONTATORE (energia), `binary_sensor` classe `gas` e'
    un RILEVATORE di fuga (sicurezza). Se qualcuno fondesse i due rami per
    sola classe, questo test arrossisce: coppia provata fianco a fianco,
    nello stesso test."""
    archivio.record(quando_ts=ts(5), source="entita",
                    subject="sensor.gas_contatore", da=None, a="120.5",
                    device_class="gas")
    archivio.record(quando_ts=ts(6), source="entita",
                    subject="binary_sensor.gas_cucina", da="off", a="on",
                    device_class="gas")
    archivio.record(quando_ts=ts(6, 5), source="entita",
                    subject="binary_sensor.gas_cucina", da="on", a="off",
                    device_class="gas")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 2
    oggetti = {o["protagonista"]: o for o in archivio.facts(day=G)}
    assert oggetti["sensor.gas_contatore"]["genere"] == "energia"
    assert oggetti["binary_sensor.gas_cucina"]["genere"] == "sicurezza"


def test_confini_giorno_ha_25_ore_nel_weekend_di_ottobre():
    """La spec (§3) nomina proprio questo weekend: l'ora torna indietro e il
    giorno dura un'ora in piu'. Mutazione: sommare sempre `timedelta(days=1)`
    in secondi civili fissi (86400) invece che tramite l'aritmetica del
    fuso -- la differenza tornerebbe 86400 invece di 90000."""
    da_ts, a_ts = day_boundaries("2026-10-25", "Europe/Rome")
    assert a_ts - da_ts == 25 * 3600


# -- Punto 9: `_OPERABLE` era una lista scritta a mano incompleta --------

def test_domini_aggiunti_a_funzionano_producono_un_funzionamento():
    """`_OPERABLE` mancava domini comuni che funzionano come gli altri
    sei, e cadevano in silenzio (nessun oggetto, nessun errore). Mutazione:
    togliere uno dei quattro da `_OPERABLE` -- l'assert corrispondente
    tornerebbe `None` invece di "funzionamento"."""
    assert genre_for("humidifier.camera", None) == "funzionamento"
    assert genre_for("vacuum.robot", None) == "funzionamento"
    assert genre_for("valve.giardino", None) == "funzionamento"
    assert genre_for("media_player.soggiorno", None) == "funzionamento"


# -- Secondo giro di correzioni dopo la review (26 agosto) ------------------
#
# -- Punto 1: i domini nuovi hanno portato stati di riposo che nessuno
# -- conosceva -- `_OPERABLE` era stato allargato senza guardare
# -- `_RESTING` a fianco. Terza occorrenza della stessa famiglia di difetto
# -- in questa fetta (l'allarme rovesciato, l'energia che non chiudeva).

def test_un_robot_che_torna_alla_base_chiude_il_suo_oggetto(archivio):
    """'docked' e' il riposo del vacuum -- verificato sulla documentazione
    Home Assistant (Vacuum entity: "docked... it is assumed that docked
    can also mean charging"), non sull'elenco del mandato. Prima di questa
    correzione mancava da `_RESTING`: il robot che finisce e torna alla
    base restava un oggetto aperto per sempre (`fine_ts: None`). Mutazione:
    togliere 'docked' da `_RESTING` -- `fine_ts` tornerebbe `None` invece
    dell'orario del rientro."""
    archivio.record(quando_ts=ts(10, 0), source="entita",
                    subject="vacuum.robot_soggiorno", da="docked", a="cleaning")
    archivio.record(quando_ts=ts(10, 45), source="entita",
                    subject="vacuum.robot_soggiorno", da="cleaning", a="docked")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = archivio.facts(day=G)[0]
    assert o["genere"] == "funzionamento"
    assert o["fine_ts"] == ts(10, 45)


def test_una_tv_che_va_in_idle_chiude_il_suo_oggetto(archivio):
    """'idle' e' il riposo del media_player quando resta acceso senza
    riprodurre nulla (documentazione HA: "turned on and accepting
    commands, but currently not playing any media"). La TV di questa casa
    ci si ferma senza mai passare da 'off'. Mutazione: togliere 'idle' da
    `_RESTING` -- `fine_ts` tornerebbe `None`."""
    archivio.record(quando_ts=ts(21, 0), source="entita",
                    subject="media_player.tv_soggiorno", da="idle", a="playing")
    archivio.record(quando_ts=ts(23, 10), source="entita",
                    subject="media_player.tv_soggiorno", da="playing", a="idle")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = archivio.facts(day=G)[0]
    assert o["genere"] == "funzionamento"
    assert o["fine_ts"] == ts(23, 10)


def test_gli_altri_riposi_dei_domini_nuovi_chiudono_anche_loro(archivio):
    """Home Assistant documenta altri riposi per gli stessi due domini,
    oltre a 'docked' e 'idle': 'returning' ed 'error' per il vacuum (il
    robot che sta rientrando, o in errore, non sta piu' pulendo); 'standby'
    per il media_player ('standby' e' deprecato verso 'off'/'idle' dalla
    2026.8 ma ancora prodotto da alcune integrazioni -- questa casa ce
    l'ha). Ognuno chiude l'oggetto esattamente come 'docked'/'idle'.

    **'paused' NON e' fra questi** (giro di pulizia, punto 3, correzione
    del 26 agosto): una pausa non e' un riposo, e' un'attivita' SOSPESA --
    l'apparecchio non ha finito. Vedi
    `test_un_film_in_pausa_resta_un_solo_oggetto` per la prova dedicata.

    Mutazione, ripetuta per ciascuno dei riposi rimasti: toglierlo da
    `_RESTING` -- il numero di oggetti ancora aperti a fine giornata
    salirebbe da 0 al numero di stati rimossi."""
    casi = [
        ("vacuum.robot_soggiorno", "cleaning", "returning"),
        ("vacuum.robot_soggiorno", "cleaning", "error"),
        ("media_player.tv_soggiorno", "playing", "standby"),
    ]
    for i, (soggetto, acceso, riposo) in enumerate(casi):
        archivio.record(quando_ts=ts(i, 0), source="entita",
                        subject=soggetto, da=riposo, a=acceso)
        archivio.record(quando_ts=ts(i, 30), source="entita",
                        subject=soggetto, da=acceso, a=riposo)
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    oggetti = archivio.facts(day=G)
    assert len(oggetti) == len(casi)
    assert all(o["fine_ts"] is not None for o in oggetti)


# -- Giro di pulizia (26 agosto), punto 3: 'paused' non e' un riposo -------
#
# Deciso contro il mandato precedente che l'aveva dettato: un film in pausa
# cinque minuti non e' finito, e' SOSPESO. Prima di questa correzione
# 'paused' chiudeva l'episodio come 'off'/'docked'/'idle', e la ripresa ne
# apriva un secondo -- un film in pausa cinque minuti diventava due oggetti,
# e una pulizia interrotta e ripresa diventava due pulizie. Riposo e' «ha
# finito»; sospensione e' «non ha finito».

def test_un_film_in_pausa_resta_un_solo_oggetto(archivio):
    """La prova diretta del punto 3: un film messo in pausa in mezzo alla
    visione, e ripreso, e' UN episodio solo -- spezzarlo lo renderebbe
    illeggibile (criterio di accettazione, spec §1). Mutazione: rimettere
    'paused' in `_RESTING` -- l'oggetto si chiuderebbe alle 21:40 e la
    ripresa alle 21:45 ne aprirebbe un secondo, portando il conteggio a 2
    invece di 1."""
    archivio.record(quando_ts=ts(21, 0), source="entita",
                    subject="media_player.tv_soggiorno", da="idle", a="playing")
    archivio.record(quando_ts=ts(21, 40), source="entita",
                    subject="media_player.tv_soggiorno", da="playing", a="paused")
    archivio.record(quando_ts=ts(21, 45), source="entita",
                    subject="media_player.tv_soggiorno", da="paused", a="playing")
    archivio.record(quando_ts=ts(23, 10), source="entita",
                    subject="media_player.tv_soggiorno", da="playing", a="idle")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = archivio.facts(day=G)[0]
    assert o["inizio_ts"] == ts(21, 0)
    assert o["fine_ts"] == ts(23, 10)


def test_un_apparecchio_lasciato_in_pausa_a_fine_giornata_resta_aperto(archivio):
    """La verita' dichiarata dal mandato: un apparecchio lasciato in pausa
    non ha finito, quindi il suo oggetto resta APERTO (`fine_ts: None`), non
    chiuso come se il riposo fosse arrivato. Mutazione: rimettere 'paused'
    in `_RESTING` -- l'oggetto si chiuderebbe alle 22:00 invece di restare
    aperto."""
    archivio.record(quando_ts=ts(22, 0), source="entita",
                    subject="vacuum.robot_soggiorno", da="docked", a="cleaning")
    archivio.record(quando_ts=ts(22, 30), source="entita",
                    subject="vacuum.robot_soggiorno", da="cleaning", a="paused")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = archivio.facts(day=G)[0]
    assert o["fine_ts"] is None


def test_una_valvola_che_si_apre_o_chiude_non_genera_falsi_riposi(archivio):
    """Verifica del punto 6 del mandato: `valve` condivide 'closed' con
    'cover' come unico riposo -- 'open'/'opening'/'closing' sono tutti
    attivi (documentazione HA: "opening... the process of opening",
    "closing... the process of closing"). Una valvola a meta' apertura non
    e' ferma. Mutazione: aggiungere 'opening' a `_RESTING` -- il conteggio
    finale tornerebbe 2 invece di 1 (l'oggetto si chiuderebbe a meta'
    apertura e "closing" ne aprirebbe un secondo)."""
    archivio.record(quando_ts=ts(6, 0), source="entita",
                    subject="valve.giardino", da="closed", a="opening")
    archivio.record(quando_ts=ts(6, 1), source="entita",
                    subject="valve.giardino", da="opening", a="open")
    archivio.record(quando_ts=ts(8, 0), source="entita",
                    subject="valve.giardino", da="open", a="closing")
    archivio.record(quando_ts=ts(8, 1), source="entita",
                    subject="valve.giardino", da="closing", a="closed")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = archivio.facts(day=G)[0]
    assert o["inizio_ts"] == ts(6, 0)
    assert o["fine_ts"] == ts(8, 1)


# -- Punto 2: `unavailable`/`unknown` sono trasparenti, non un riposo -- il
# -- funzionamento e la sicurezza li trattavano come "spento" perche'
# -- `_UNKNOWN` era un sottoinsieme di `_RESTING`.

def test_un_riavvio_di_ha_non_spezza_un_riscaldamento_acceso(archivio):
    """Uno stato 'unavailable' non e' 'e' finito' ne' 'e' cominciato': e'
    'non lo sappiamo'. Un riscaldamento acceso alle 15:30, un riavvio che
    lo fa passare per 'unavailable' alle 18:00 e tornare 'heat' alle 18:05,
    spento alle 20:00: deve nascere UN oggetto dalle 15:30 alle 20:00, non
    due.

    Le due difese in gioco sono `_RESTING` (non contiene 'unavailable'/
    'unknown') e il filtro `_UNKNOWN` in cima ad `aggregate_day`. Mutazioni
    ESEGUITE e verificate una per una (giro di pulizia, punto 3 -- il
    rapporto precedente le diceva entrambe inerti per LA STESSA ragione,
    ed era vero solo per la prima):

    - rimettere 'unavailable' in `_RESTING` da sola resta verde: il filtro
      `_UNKNOWN` in cima toglie la riga PRIMA che arrivi a controllare
      `_RESTING`, che quindi non la vede mai. **Questa meta' e' oggi
      ridondanza morta**: nessun test la sorveglia da sola, la sua unica
      guardia e' questo commento;
    - togliere il filtro `_UNKNOWN` in cima da solo resta verde ANCHE QUI,
      ma per una ragione diversa: quando 'unavailable' arriva a episodio
      GIA' aperto, `_is_on("unavailable")` torna `True` (non e' in
      `_RESTING`), e la guardia `if subject not in open_episodes` non fa nulla
      perche' il soggetto e' gia' dentro -- l'oggetto resta aperto per
      assorbimento del guardiano, non perche' la difesa regga qui.
      **Questa meta', pero', e' sorvegliata altrove**: da
      `test_un_riavvio_di_ha_non_apre_un_oggetto_di_presenza` e da
      `test_il_riepilogo_dell_energia_salta_le_letture_unavailable`, dove
      l'episodio NON e' ancora aperto quando arriva 'unavailable' e il
      filtro e' l'unica cosa che impedisce un oggetto spurio o una
      lettura contaminata -- provato dal vivo: entrambi arrossiscono
      togliendo solo il filtro.

    Serve quindi la COPPIA per arrossire proprio questo test: rimettere
    'unavailable'/'unknown' dentro `_RESTING` **e** togliere il filtro
    `_UNKNOWN` in cima (lo stato pre-correzione, prima che le due difese
    esistessero) -- solo insieme riproducono il difetto originale, e il
    conteggio torna 2 invece di 1. Questo test e il suo gemello (allarme)
    sono comunque l'ultima linea: scattano il giorno in cui un refattore
    togliesse il filtro credendo che l'appartenenza a `_RESTING` da sola
    copra il caso dell'episodio gia' aperto -- non lo copre, e senza il
    filtro nessun altro test qui dentro se ne accorgerebbe."""
    archivio.record(quando_ts=ts(15, 30), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    archivio.record(quando_ts=ts(18, 0), source="entita",
                    subject="climate.camera_t", da="heat", a="unavailable")
    archivio.record(quando_ts=ts(18, 5), source="entita",
                    subject="climate.camera_t", da="unavailable", a="heat")
    archivio.record(quando_ts=ts(20, 0), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = archivio.facts(day=G)[0]
    assert o["inizio_ts"] == ts(15, 30)
    assert o["fine_ts"] == ts(20, 0)


def test_un_riavvio_di_ha_non_spezza_un_allarme_disinserito(archivio):
    """Stesso difetto, ramo sicurezza: la casa lasciata disarmata e' la
    cosa NOTEVOLE (vedi il punto 3b), e un riavvio a meta' non deve
    spezzarla in due.

    Stesso ragionamento del test gemello (riscaldamento), ESEGUITO e
    verificato rosso per entrambe le meta' separatamente (giro di
    pulizia, punto 3): rimettere 'unavailable' in `_RESTING` da sola resta
    verde, schermata dal filtro `_UNKNOWN` in cima -- e QUI e' ridondanza
    morta, nessun test la sorveglia da sola. Togliere il filtro `_UNKNOWN`
    in cima da solo resta verde anche qui, per lo stesso assorbimento:
    l'episodio e' gia' aperto ("disarmed" dall'1:00) quando 'unavailable'
    arriva alle 5:00, `_is_on("unavailable")` torna `True`, e la guardia
    non fa nulla perche' il soggetto e' gia' dentro -- ma quella meta' e'
    sorvegliata altrove (vedi il gemello per i due test che la
    catturano).

    Serve quindi la COPPIA per arrossire proprio questo test: rimettere
    'unavailable'/'unknown' dentro `_RESTING` **e** togliere il filtro in
    cima -- e solo cosi' l'oggetto si chiude alle 5:00 e "disarmed" alle
    5:05 ne apre un secondo, portando il conteggio a 2. Questo test e il
    suo gemello sono l'ultima linea proprio per il caso dell'episodio
    gia' aperto, che l'appartenenza a `_RESTING` da sola non copre."""
    archivio.record(quando_ts=ts(1, 0), source="entita",
                    subject="alarm_control_panel.casa", da="armed_home",
                    a="disarmed")
    archivio.record(quando_ts=ts(5, 0), source="entita",
                    subject="alarm_control_panel.casa", da="disarmed",
                    a="unavailable")
    archivio.record(quando_ts=ts(5, 5), source="entita",
                    subject="alarm_control_panel.casa", da="unavailable",
                    a="disarmed")
    archivio.record(quando_ts=ts(9, 0), source="entita",
                    subject="alarm_control_panel.casa", da="disarmed",
                    a="armed_home")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = archivio.facts(day=G)[0]
    assert o["inizio_ts"] == ts(1, 0)
    assert o["fine_ts"] == ts(9, 0)


# -- Punto 3: il riepilogo dell'energia non deve ingerire un 'unavailable' -
# -- da riavvio a bordo giornata.

def test_il_riepilogo_dell_energia_salta_le_letture_unavailable(archivio):
    """Un riavvio di Home Assistant a bordo giornata scrive 'unavailable'
    come prima o ultima lettura del contatore: il riepilogo deve ignorarla
    e usare la prima/ultima lettura VERA, non uscire con
    `valore_finale: "unavailable"` e `differenza: None` su ogni contatore
    della casa a ogni riavvio. Mutazione: filtrare `_UNKNOWN` solo nel ramo
    presenza (com'era prima di questa correzione) invece che in cima al
    ciclo, prima di costruire `misure` -- `valore_iniziale` tornerebbe
    'unavailable' e `differenza` None."""
    archivio.record(quando_ts=ts(0, 1), source="entita",
                    subject="sensor.energia_casa", da=None, a="unavailable",
                    device_class="energy")
    archivio.record(quando_ts=ts(1), source="entita",
                    subject="sensor.energia_casa", da=None, a="100.0",
                    device_class="energy")
    archivio.record(quando_ts=ts(23), source="entita",
                    subject="sensor.energia_casa", da=None, a="130.5",
                    device_class="energy")
    archivio.record(quando_ts=ts(23, 59), source="entita",
                    subject="sensor.energia_casa", da=None, a="unavailable",
                    device_class="energy")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    o = archivio.facts(day=G)[0]
    assert o["corpo"]["valore_iniziale"] == "100.0"
    assert o["corpo"]["valore_finale"] == "130.5"
    assert o["corpo"]["differenza"] == pytest.approx(30.5)


# -- Punto 4: la quinta finta -- il limite superiore delle misure deve
# -- guardare il protagonista, non gli inizi di TUTTI gli episodi.

def test_il_limite_superiore_rispetta_il_protagonista_non_ignora_gli_altri(archivio):
    """Due protagonisti con episodi intrecciati nel tempo: `climate.
    soggiorno_t` (9:15-14:00) si accende PRIMA che il primo episodio di
    `climate.camera_t` (9:00-9:30) finisca il suo intervallo di misura, e
    molto prima del secondo episodio di camera_t (15:00-15:30). Il limite
    superiore delle misure del primo episodio di camera_t deve essere
    l'inizio del SUO prossimo episodio (15:00), non l'inizio dell'episodio
    di soggiorno_t (9:15) solo perche' capita prima. Mutazione: raccogliere
    gli inizi di TUTTI gli episodi in un'unica lista invece che per
    protagonista (`next_starts` indicizzato senza il protagonista) --
    il limite del primo episodio di camera_t crollerebbe a 9:15 e la
    misura delle 10:00 sparirebbe dal suo corpo (nessun punto in
    [9:00, 9:15))."""
    archivio.record(quando_ts=ts(9, 0), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    archivio.record(quando_ts=ts(9, 30), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    archivio.record(quando_ts=ts(9, 15), source="entita",
                    subject="climate.soggiorno_t", da="off", a="heat")
    archivio.record(quando_ts=ts(14, 0), source="entita",
                    subject="climate.soggiorno_t", da="heat", a="off")
    archivio.record(quando_ts=ts(15, 0), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    archivio.record(quando_ts=ts(15, 30), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    archivio.record(quando_ts=ts(10, 0), source="entita",
                    subject="sensor.camera_temperatura", da=None, a="19.5")
    aggregate_day(
        store=archivio, day=G, timezone="Europe/Rome",
        companions=lambda s: (["sensor.camera_temperatura"]
                              if s == "climate.camera_t" else []))
    oggetti = [o for o in archivio.facts(day=G)
              if o["protagonista"] == "climate.camera_t"]
    primo = min(oggetti, key=lambda o: o["inizio_ts"])
    assert primo["inizio_ts"] == ts(9, 0)
    assert primo["corpo"]["misure"]["sensor.camera_temperatura"] == {
        "da": "19.5", "a": "19.5"}


# -- Giro di pulizia (26 agosto), punto 1: il PROSSIMO episodio non e' -----
# -- l'ULTIMO -- sesta occorrenza della stessa forma in questa fetta: un
# -- parametro che nessun test distingueva da un altro possibile.

def test_il_limite_superiore_e_il_prossimo_episodio_non_l_ultimo(archivio):
    """Nessun test, finora, aveva TRE episodi dello stesso protagonista:
    con solo due, `min(later)` e `max(later)` tornano lo stesso
    valore, e niente distingue "il prossimo" da "l'ultimo". Con tre
    accensioni del riscaldamento, il limite superiore delle misure del
    PRIMO episodio deve fermarsi al SECONDO (il prossimo), non sconfinare
    fino al TERZO. Mutazione: `min` -> `max` in `upper_limit` -- la
    misura delle 13:00, che sta nella finestra del secondo episodio (non
    dentro la sua durata, ma prima del terzo), finirebbe attribuita anche al
    primo, e "a" diventerebbe "22.0" invece di "20.0"."""
    archivio.record(quando_ts=ts(9, 0), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    archivio.record(quando_ts=ts(9, 15), source="entita",
                    subject="sensor.camera_temperatura", da=None, a="20.0")
    archivio.record(quando_ts=ts(9, 30), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    archivio.record(quando_ts=ts(12, 0), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    archivio.record(quando_ts=ts(12, 30), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    archivio.record(quando_ts=ts(13, 0), source="entita",
                    subject="sensor.camera_temperatura", da=None, a="22.0")
    archivio.record(quando_ts=ts(15, 0), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    archivio.record(quando_ts=ts(15, 30), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome",
                   companions=lambda s: (["sensor.camera_temperatura"]
                                         if s == "climate.camera_t" else []))
    oggetti = sorted(archivio.facts(day=G), key=lambda o: o["inizio_ts"])
    assert len(oggetti) == 3
    primo = oggetti[0]
    assert primo["corpo"]["misure"]["sensor.camera_temperatura"] == {
        "da": "20.0", "a": "20.0"}


# -- Giro di pulizia (26 agosto), punto 4: i confini delle misure ----------

def test_il_confine_inferiore_delle_misure_include_l_istante_di_inizio_dell_oggetto(archivio):
    """Una misura presa nello STESSO istante in cui l'oggetto comincia e' il
    caso FREQUENTE: e' lo stesso istante dell'evento che apre l'episodio.
    Deve starci nel corpo. Mutazione: `<=` -> `<` sul limite inferiore --
    la misura delle 15:30 sparirebbe dal corpo (nessun punto in
    [15:30, 17:05))."""
    archivio.record(quando_ts=ts(15, 30), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    archivio.record(quando_ts=ts(15, 30), source="entita",
                    subject="sensor.camera_temperatura", da=None, a="18.2")
    archivio.record(quando_ts=ts(17, 5), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome",
                   companions=lambda s: ["sensor.camera_temperatura"])
    o = archivio.facts(day=G)[0]
    assert o["corpo"]["misure"]["sensor.camera_temperatura"] == {
        "da": "18.2", "a": "18.2"}


def test_il_confine_superiore_delle_misure_esclude_l_inizio_del_prossimo_episodio(archivio):
    """Una misura esattamente all'inizio del PROSSIMO episodio non appartiene
    a QUESTO oggetto: e' gia' il clima del prossimo. Mutazione: `<` -> `<=`
    sul limite superiore -- la misura delle 12:00 finirebbe attribuita anche
    al primo episodio, e "a" diventerebbe "99.9" invece di "20.0"."""
    archivio.record(quando_ts=ts(9, 0), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    archivio.record(quando_ts=ts(9, 15), source="entita",
                    subject="sensor.camera_temperatura", da=None, a="20.0")
    archivio.record(quando_ts=ts(9, 30), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    archivio.record(quando_ts=ts(12, 0), source="entita",
                    subject="sensor.camera_temperatura", da=None, a="99.9")
    archivio.record(quando_ts=ts(12, 0), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    archivio.record(quando_ts=ts(12, 30), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome",
                   companions=lambda s: (["sensor.camera_temperatura"]
                                         if s == "climate.camera_t" else []))
    oggetti = sorted(archivio.facts(day=G), key=lambda o: o["inizio_ts"])
    primo = oggetti[0]
    assert primo["corpo"]["misure"]["sensor.camera_temperatura"] == {
        "da": "20.0", "a": "20.0"}


# -- Punto 6, pulizia 2: una sola lettura non sa dire la differenza --------

def test_un_energia_con_una_sola_lettura_non_sa_dire_la_differenza(archivio):
    """Una sola lettura nel giorno non permette di sapere quanto e'
    cambiato: la verita' e' 'non lo sappiamo', non 'zero' -- la stessa
    distinzione del punto 2, e il codice altrove la fa gia' restituendo
    `None` quando il valore non si legge come numero (`_difference`). Con
    una sola lettura, iniziale e finale sono la STESSA riga: il conto
    tornerebbe 0.0, che direbbe il fatto falso "non e' cambiato niente".
    Mutazione: calcolare comunque `_difference(iniziale, finale)` anche con
    un solo punto -- `differenza` tornerebbe 0.0 invece di `None`."""
    archivio.record(quando_ts=ts(12), source="entita",
                    subject="sensor.energia_casa", da=None, a="100.0",
                    device_class="energy")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = archivio.facts(day=G)[0]
    assert o["corpo"]["valore_iniziale"] == "100.0"
    assert o["corpo"]["valore_finale"] == "100.0"
    assert o["corpo"]["differenza"] is None


# -- Le direzioni dell'energia: come i comprimari, mai nel grezzo -----------
#
# `aggregate_day` riceve `directions(subject) -> dict | None` dal chiamante,
# esattamente come riceve `companions(subject) -> list[str]` (mandato
# "le direzioni dell'energia", punto 2). Non si scrive nel grezzo: la
# direzione e' una CONFIGURAZIONE (la dashboard Energia dell'utente puo'
# cambiare), e congelarla in scrittura la renderebbe irrecuperabile per i 21
# giorni in cui il grezzo permette di rifare il giudizio -- la stessa
# ragione per cui non si salva la gamba gia' calcolata.

def test_un_episodio_di_energia_porta_direzione_e_provenienza_quando_note(archivio):
    """Il caso base: `direzioni()` sa dire la direzione del protagonista, e il
    corpo dell'episodio di energia la porta per intero -- `direzione` E
    `provenienza`, non solo una delle due."""
    archivio.record(quando_ts=ts(1), source="entita",
                    subject="sensor.energia_prodotta", da=None, a="10.0",
                    device_class="energy")
    archivio.record(quando_ts=ts(20), source="entita",
                    subject="sensor.energia_prodotta", da=None, a="25.0",
                    device_class="energy")
    aggregate_day(
        store=archivio, day=G, timezone="Europe/Rome",
        directions=lambda s: {"direzione": "produzione", "provenienza": "dichiarata"}
        if s == "sensor.energia_prodotta" else None)
    o = archivio.facts(day=G)[0]
    assert o["corpo"]["direzione"] == "produzione"
    assert o["corpo"]["provenienza"] == "dichiarata"


def test_senza_direzioni_il_campo_non_c_e_mai_una_sconosciuta_travestita(archivio):
    """Mandato: «quando la direzione non si conosce, il campo non c'e' -- non
    un "sconosciuta" travestito da dato.» Senza passare `direzioni` affatto
    (come ogni test precedente in questo file, che non lo conoscevano ancora),
    il corpo di un episodio di energia non deve avere NESSUNA delle due
    chiavi."""
    archivio.record(quando_ts=ts(2), source="entita",
                    subject="sensor.energia_casa", da=None, a="5.0",
                    device_class="energy")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    o = archivio.facts(day=G)[0]
    assert "direzione" not in o["corpo"]
    assert "provenienza" not in o["corpo"]


def test_direzioni_passata_ma_ignota_per_questo_soggetto_non_scrive_niente(archivio):
    """`direzioni` c'e' (non e' `None`) ma torna `None` per QUESTO soggetto --
    la dashboard Energia non lo copre e nessun `translation_key` lo riconosce.
    Il campo resta assente, non una stringa vuota o "sconosciuta".
    Mutazione ESEGUITA: `if info:` sostituito con `if True:` nel corpo di
    `aggregate_day` -- arrossisce, perche' `corpo["direzione"]` diventerebbe
    la chiave di un dizionario `None` (`TypeError`) o (con una guardia diversa)
    scriverebbe `None` come valore invece di omettere la chiave. Ripristinato
    subito dopo."""
    archivio.record(quando_ts=ts(2), source="entita",
                    subject="sensor.energia_senza_fonte", da=None, a="5.0",
                    device_class="energy")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome",
                   directions=lambda s: None)
    o = archivio.facts(day=G)[0]
    assert "direzione" not in o["corpo"]
    assert "provenienza" not in o["corpo"]


def test_la_direzione_non_finisce_su_un_genere_che_non_e_energia(archivio):
    """Difesa contro un `direzioni` troppo permissivo, o un refuso nel ramo
    che lo applica: un `funzionamento` non deve MAI portare `direzione`,
    anche se il chiamante (per errore, o per un `lambda` scritto troppo
    largo) risponderebbe per qualunque soggetto."""
    archivio.record(quando_ts=ts(15, 30), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    archivio.record(quando_ts=ts(17, 5), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    aggregate_day(
        store=archivio, day=G, timezone="Europe/Rome",
        directions=lambda s: {"direzione": "produzione", "provenienza": "dichiarata"})
    o = archivio.facts(day=G)[0]
    assert o["genere"] == "funzionamento"
    assert "direzione" not in o["corpo"]
    assert "provenienza" not in o["corpo"]


def test_direzioni_si_chiede_una_volta_per_protagonista_non_per_riga_del_grezzo(archivio):
    """Come i comprimari (docstring di `aggregate_day`, Task 6): la mappa
    delle direzioni si costruisce una volta per giro di aggregazione da chi
    chiama, ma QUI dentro -- nel ciclo che costruisce il corpo -- si chiede
    UNA volta per episodio, non per ogni riga del grezzo che ha contribuito
    alla lettura iniziale/finale. Con tre letture per lo stesso contatore
    (un solo episodio di energia), la lambda deve essere invocata una sola
    volta per quel protagonista."""
    chiesti = []

    def direzioni(soggetto):
        chiesti.append(soggetto)
        return {"direzione": "prelievo", "provenienza": "dichiarata"}

    for ora, valore in ((1, "10.0"), (12, "20.0"), (23, "30.0")):
        archivio.record(quando_ts=ts(ora), source="entita",
                        subject="sensor.energia_prelievo", da=None, a=valore,
                        device_class="energy")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome",
                   directions=direzioni)
    assert chiesti == ["sensor.energia_prelievo"]
