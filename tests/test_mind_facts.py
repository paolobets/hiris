"""L'aggregazione: dai cambi agli oggetti.

**E' l'unico posto di questa fetta dove si giudica**, ed e' apposta: un
giudizio qui si rifa' finche' il grezzo esiste (22 giorni: 21 di promessa,
uno di guardia), uno in scrittura non si corregge piu'.

Un oggetto e' **una cosa compiuta della casa**: qualcosa che e' cominciato, e'
durato, e' finito -- con dentro chi lo ha fatto e cosa c'era attorno.
"""
import os

import pytest

from hiris.app.home_space import type_vocabulary as tv
from hiris.app.home_space.historian import day_boundaries
from hiris.app.home_space.type_judgments import TypeJudgments
from hiris.app.mind.facts import CHRONICLE_RULE, GENRES, aggregate_day, genre_for
from hiris.app.mind.store import ObservationsStore
from hiris.app.mind.watcher import Watcher

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


def cronaca(archivio, giorno=None):
    """Le voci di cronaca di un giorno: dove le prove leggevano gli OGGETTI.

    Lo strato degli oggetti e' uscito il 15/09/2026 (spec §13) e gli episodi
    vivono dentro il resoconto. Le prove non si sono cancellate: si sono
    **tradotte**, perche' una prova tradotta e' una proprieta' che resta --
    `protagonista` e' diventato `chi`, `inizio_ts` e' `quando_ts`, e
    `corpo.stato` e' `cosa`. Quelle che verificavano i comprimari e le loro
    misure sono uscite davvero: misurato sulla casa vera prima di cancellare,
    i comprimari erano **zero su 200 oggetti**.
    """
    scritto = archivio.report(giorno or G)
    return (scritto or {}).get("cronaca") or []


def test_il_genere_discende_dalla_natura():
    """Dal 17/09/2026 il secondo argomento e' la `device_class` del grezzo, non
    la gamba (spec 2026-09-16 §5): il genere di un'entita' e' un giudizio
    dell'istantanea, i prefissi di sistema restano codice.

    `sensor.presa` di classe `power` non ha genere (D2): `energia` non ha una
    forma, e il seme non lo scrive. Mutazione ESEGUITA: in `genre_for`,
    chiedere a `judgments.genre_of(subject, None)` invece di passare la classe
    -- rossa su `genre_for("binary_sensor.fumo", "smoke") == "sicurezza"`."""
    assert genre_for("climate.camera_t", None) == "funzionamento"
    assert genre_for("cover.tapparella", None) == "funzionamento"
    assert genre_for("person.marta", None) == "presenza"
    assert genre_for("sensor.presa", "power") is None
    assert genre_for("problema:sonos.x", None) == "guasto"
    assert genre_for("sensor.camera_t", "temperature") is None
    assert genre_for("binary_sensor.fumo", "smoke") == "sicurezza"
    for g in GENRES:
        assert isinstance(g, str)


def test_il_genere_di_sicurezza_e_diverso_dal_guasto_di_sistema():
    """Correzione 0.1: 'guasto' resta per le condizioni di SISTEMA
    (problema:/integrazione:, un confine netto); la gamba sicurezza ha un
    genere proprio, 'sicurezza' -- una porta aperta con la chiave e
    un'integrazione Sonos rotta non sono lo stesso genere di fatto.

    Dal 17/09/2026 il secondo argomento di `genre_for` e' la `device_class`,
    non la gamba. Mutazione ESEGUITA: togliere `genre=Ours("sicurezza")` dalla
    riga `lock` del letterale -- rossa sulla prima asserzione."""
    assert genre_for("lock.porta_ingresso", None) == "sicurezza"
    assert genre_for("problema:sonos.x", None) == "guasto"
    assert genre_for("integrazione:abc", None) == "guasto"
    assert "sicurezza" in GENRES
    # Quattro generi, non sei (16/09/2026, spec «il giudizio dei tipi» §5,
    # D2): `GENRES` e' diventato `type_vocabulary.CHRONICLE_GENRES`, i soli
    # generi con una FORMA scritta in questo file. "energia" e "bilancio"
    # sono usciti: nessun ramo di `aggregate_day` trattava il primo (una riga
    # `energia` cadeva oltre tutti i rami senza produrre niente), e nessun
    # codice produceva mai il secondo -- la docstring che lo descriveva era
    # una ragione smentita dal file stesso.
    assert len(GENRES) == 4
    assert "bilancio" not in GENRES and "energia" not in GENRES


def test_a_log_subject_is_a_fault():
    """Il terzo prefisso entra nello stesso confine netto degli altri due:
    `genre_for` decide dal prefisso, e una voce di log e' una condizione di
    sistema come un repair o un'integrazione rotta.

    Mutazione: togliere `"log:"` dalla tupla dei prefissi -- il test torna
    rosso su `assert genre_for("log:homeassistant.setup@setup.py:123", None)
    == "guasto"`.
    """
    assert genre_for("log:homeassistant.setup@setup.py:123", None) == "guasto"


def test_un_termostato_acceso_e_spento_diventa_UN_oggetto(archivio):
    archivio.record(quando_ts=ts(15, 30), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    archivio.record(quando_ts=ts(17, 5), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = cronaca(archivio)[0]
    assert o["genere"] == "funzionamento"
    assert o["chi"] == "climate.camera_t"
    assert o["quando_ts"] == ts(15, 30)
    assert o["fine_ts"] == ts(17, 5)


def test_una_cosa_ancora_in_corso_a_mezzanotte_resta_aperta(archivio):
    archivio.record(quando_ts=ts(22, 0), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    assert cronaca(archivio)[0]["fine_ts"] is None


def test_un_assenza_e_un_oggetto(archivio):
    archivio.record(quando_ts=ts(8, 10), source="entita",
                    subject="person.paolo", da="home", a="not_home")
    archivio.record(quando_ts=ts(17, 34), source="entita",
                    subject="person.paolo", da="not_home", a="home")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    o = cronaca(archivio)[0]
    assert o["genere"] == "presenza"
    assert o["cosa"] == "not_home"


def test_un_cambio_di_zona_a_meta_assenza_non_riapre_l_oggetto(archivio):
    """La settima finta (mandato, punto 1): la guardia del ramo presenza
    (`if subject not in open_episodes`; dal 17/09/2026 il ramo e' unico per
    presenza, funzionamento e sicurezza) impedisce che un cambio di ZONA a meta'
    di un'assenza -- le zone sono stati VERI di una `person`, non solo
    "home"/"not_home" -- riapra l'oggetto azzerandone inizio e stato. Paolo
    esce di casa alle 8:10 ("not_home"), entra in una zona ("ufficio") alle
    9:00, rientra alle 17:34: l'assenza vera dura dalle 8:10 alle 17:34, con
    stato "not_home" -- non dalle 9:00, con stato "ufficio".

    Mutazione ESEGUITA e verificata rossa (rieseguita il 17/09/2026 sul ramo
    unico): togliere la guardia `if subject not in open_episodes:` e aprire
    sempre -- il cambio di zona delle 9:00 riapre
    l'oggetto, e inizio_ts/stato tornano ts(9,0)/"ufficio" invece di
    ts(8,10)/"not_home"."""
    archivio.record(quando_ts=ts(8, 10), source="entita",
                    subject="person.paolo", da="home", a="not_home")
    archivio.record(quando_ts=ts(9, 0), source="entita",
                    subject="person.paolo", da="not_home", a="ufficio")
    archivio.record(quando_ts=ts(17, 34), source="entita",
                    subject="person.paolo", da="ufficio", a="home")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = cronaca(archivio)[0]
    assert o["genere"] == "presenza"
    assert o["quando_ts"] == ts(8, 10)
    assert o["fine_ts"] == ts(17, 34)
    assert o["cosa"] == "not_home"


def test_un_guasto_di_sistema_e_un_oggetto(archivio):
    archivio.record(quando_ts=ts(9, 0), source="sistema",
                    subject="problema:sonos.subscriptions_failed", da=None, a="aperto")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    o = cronaca(archivio)[0]
    assert o["genere"] == "guasto"
    assert o["fine_ts"] is None


def test_a_fault_body_says_which_condition_not_the_word_open(archivio):
    """Ogni oggetto di guasto in archivio diceva `stato: "aperto"`, anche
    quelli chiusi: `setup_retry` e `setup_error` non sono la stessa cosa, e
    un campo che non varia mai non e' un fatto -- contraddice i timestamp
    che gli stanno accanto.

    Mutazione: rimettere la costante `"aperto"` al posto di `r["a"]` -- il
    test torna rosso su `assert corpo["cosa"] == "setup_retry"`.
    """
    archivio.record(quando_ts=ts(9, 0), source="sistema",
                    subject="integrazione:01ABC", da=None, a="setup_retry",
                    domain="lifx", title="Abat-jour")
    archivio.record(quando_ts=ts(11, 30), source="sistema",
                    subject="integrazione:01ABC", da="setup_retry", a="chiuso")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    o = cronaca(archivio)[0]
    assert o["genere"] == "guasto"
    assert o["fine_ts"] is not None
    corpo = o
    assert corpo["cosa"] == "setup_retry"
    assert corpo["dominio"] == "lifx"
    assert corpo["titolo"] == "Abat-jour"


def test_an_old_row_saying_open_still_opens_an_episode(archivio):
    """Le righe scritte prima della migrazione 3 portano ancora `"aperto"`
    e devono continuare ad aprire: la convenzione nuova e' «chiude solo
    "chiuso"», quindi non serve nessun caso a parte. E' cio' che rende
    superflua la convivenza che la spec ipotizzava.

    Mutazione: chiudere su qualunque valore diverso da una condizione nota
    -- nessun oggetto nasce: `cronaca(archivio)` e' vuoto, e il test
    torna rosso su un `IndexError` nell'indicizzare `[0]`, prima di
    arrivare a nessuno degli `assert`.
    """
    archivio.record(quando_ts=ts(9, 0), source="sistema",
                    subject="integrazione:01OLD", da=None, a="aperto")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    o = cronaca(archivio)[0]
    assert o["genere"] == "guasto"
    assert o["cosa"] == "aperto"
    assert o.get("dominio") is None


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
    o = cronaca(archivio)[0]
    assert o["genere"] == "guasto"
    assert o["fine_ts"] is None
    corpo = o
    assert corpo["cosa"] == "setup_error"
    assert corpo["dominio"] == "lifx"
    assert corpo["titolo"] == "Abat-jour"


def test_a_log_entry_becomes_a_fault_object(archivio):
    """Il terzo prefisso (Task 2, «le tracce e il log») attraversa la STESSA
    aggregazione dei due gemelli qui sopra: nasce, dura, chiude -- `stato`
    porta il livello, `dominio` il logger, `titolo` la prima riga del
    messaggio, esattamente come per un'integrazione rotta.

    Una prima mutazione che UCCIDE questo test e' nella tupla di prefissi di
    `genre_for`: senza `"log:"` il soggetto non produce nessun genere,
    `aggregate_day` non apre nessun episodio, e `cronaca(archivio)` torna
    vuoto -- il test torna rosso su `IndexError` nell'indicizzare `[0]`.
    (Fino al 17/09/2026 questo docstring diceva che il test esercitava anche
    `_reading_aspect`; quella funzione e' uscita col genere dall'istantanea.)

    Una seconda, indipendente, e' su `comparso_ts` (la colonna nuova del
    giro di revisione, `store.py::_migration_4`): togliere
    `"comparso_ts": r.get("first_occurred")` dalla costruzione
    dell'episodio in `aggregate_day` -- il test torna rosso su
    `KeyError: 'comparso_ts'` nell'indicizzare `corpo["comparso_ts"]`.
    """
    archivio.record(quando_ts=ts(9, 0), source="sistema",
                    subject="log:homeassistant.components.hydrawise@hydrawise/coordinator.py:88",
                    da=None, a="ERROR",
                    domain="homeassistant.components.hydrawise", title="403 Forbidden",
                    first_occurred=ts(9, 0) - 3 * 86400)
    archivio.record(quando_ts=ts(11, 0), source="sistema",
                    subject="log:homeassistant.components.hydrawise@hydrawise/coordinator.py:88",
                    da="ERROR", a="chiuso")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    o = cronaca(archivio)[0]
    assert o["genere"] == "guasto"
    assert o["fine_ts"] is not None
    corpo = o
    assert corpo["cosa"] == "ERROR"
    assert corpo["dominio"] == "homeassistant.components.hydrawise"
    assert corpo["titolo"] == "403 Forbidden"
    assert corpo["comparso_ts"] == ts(9, 0) - 3 * 86400


def test_comparso_ts_is_absent_for_repairs_and_integrations(archivio):
    """`comparso_ts` e' SOLO per una voce di log: un `problema:` o
    un'`integrazione:` non lo dichiarano mai (`_reading_row` rilegge `None`),
    e la chiave tace nel corpo come ogni altra che non ha niente da dire --
    non diventa mai `null`.

    Mutazione: scrivere sempre `base_body["comparso_ts"] = o.get("comparso_ts")`
    senza il controllo `is not None` -- il test torna rosso su
    `assert "comparso_ts" not in o`.
    """
    archivio.record(quando_ts=ts(9, 0), source="sistema",
                    subject="integrazione:01XYZ", da=None, a="setup_error",
                    domain="lifx", title="Abat-jour")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    o = cronaca(archivio)[0]
    assert o["genere"] == "guasto"
    assert "comparso_ts" not in o


def test_watch_system_writes_a_log_condition_that_aggregate_day_can_see(archivio):
    """Prova end-to-end della correzione del giro di revisione:
    `Watcher.watch_system` scrive la nascita di una voce di log con
    `quando_ts=now` anche quando `first_occurred` e' di tre giorni fa -- il
    caso misurato sulla casa vera, dove HA tiene le voci dall'ultimo suo
    riavvio -- e `aggregate_day`, che legge solo la finestra del giorno, la
    vede comunque.

    Mutazione: in `watcher.py::watch_system`, scrivere `quando_ts=
    first_occurred` (la prima stesura, prima della correzione) invece di
    `quando_ts=now` sempre -- il test torna rosso su `IndexError`
    nell'indicizzare `cronaca(archivio)[0]`, perche' la riga di apertura
    finirebbe tre giorni prima della finestra che `aggregate_day` legge.
    """
    osservatore = Watcher(archivio, now=lambda: ts(9, 0))
    tre_giorni_fa = ts(9, 0) - 3 * 86400
    entry = {"name": "custom_components.zcsazzurro.sensor", "level": "WARNING",
             "count": 1, "first_occurred": tre_giorni_fa,
             "source": ["zcsazzurro/sensor.py", 44],
             "message": ["Timeout leggendo l'inverter"]}
    osservatore.watch_system(problems=[], integrations=[], log_entries=[entry])
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    o = cronaca(archivio)[0]
    assert o["genere"] == "guasto"
    assert o["quando_ts"] == ts(9, 0)
    assert o["comparso_ts"] == tre_giorni_fa


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
    assert len(cronaca(archivio)) == 1


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

def test_serrature_allarmi_sirene_rilevatori_sono_sicurezza():
    """Le nature risolvibili dal solo dominio -- serratura, pannello
    dell'allarme, sirena -- e i rilevatori (quando la `device_class` e' quella
    giusta) diventano un oggetto di sicurezza: sono una minaccia, non un
    funzionamento normale,
    e hanno la stessa FORMA di una condizione di sistema -- nate, durate,
    chiuse o ancora aperte -- ma non lo STESSO genere (0.1: una porta aperta
    con la chiave e un'integrazione Sonos rotta non sono la stessa cosa). Un
    `else` che le mandasse a vuoto sarebbe il buco che la review del primo
    task ha gia' trovato una volta (§4 della spec).

    `sensor.co_soggiorno` e' `None` e non `"sicurezza"` da questa correzione
    (giro di review, punto 7): e' un `sensor` che MISURA (una concentrazione
    numerica), non un `binary_sensor` che SCATTA -- vedi il docstring di
    `genre_for` per la ragione per cui resta fuori.

    **Dal 17/09/2026 il secondo argomento e' la `device_class`**, non la
    gamba: il rilevatore e' `sicurezza` per la sua classe (`smoke`), il
    monossido misurato non ha genere perche' il seme non ne scrive nessuno per
    `sensor.carbon_monoxide` (spec 2026-09-16 §5). Mutazione ESEGUITA: dare
    `genre=Ours("sicurezza")` alla coppia `sensor`/`carbon_monoxide` nel
    letterale -- rossa sull'ultima asserzione."""
    assert genre_for("lock.porta_ingresso", None) == "sicurezza"
    assert genre_for("alarm_control_panel.casa", None) == "sicurezza"
    assert genre_for("siren.sirena_esterna", None) == "sicurezza"
    assert genre_for("binary_sensor.fumo_cucina", "smoke") == "sicurezza"
    assert genre_for("sensor.co_soggiorno", "carbon_monoxide") is None


def test_una_sirena_che_suona_e_rientra_e_un_oggetto_di_sicurezza(archivio):
    """Lo scenario che la spec §4 chiama il buco peggiore possibile: un
    allarme che scatta e rientra deve diventare un oggetto con la sua durata,
    non sparire come sarebbe successo prima che la sesta gamba esistesse."""
    archivio.record(quando_ts=ts(3, 15), source="entita",
                    subject="siren.sirena_esterna", da="off", a="on")
    archivio.record(quando_ts=ts(3, 20), source="entita",
                    subject="siren.sirena_esterna", da="on", a="off")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = cronaca(archivio)[0]
    assert o["genere"] == "sicurezza"
    assert o["quando_ts"] == ts(3, 15)
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
    o = cronaca(archivio)[0]
    assert o["genere"] == "sicurezza"
    assert o["quando_ts"] == ts(22, 0)
    assert o["fine_ts"] == ts(22, 5)


# -- Task 3, punto 0: il grezzo porta le tre classi che il pavimento legge --
#
# Prima di quella correzione la gamba si ricostruiva dal grezzo SENZA la
# classe: per `sensor`/`binary_sensor` (che decidono dalla classe, non dal
# dominio) tornava sempre `None`, e non nasceva un solo oggetto per fumo, gas,
# monossido, allagamento, manomissione. Dal 17/09/2026 la classe del grezzo
# arriva a `genre_for`, che chiede il genere della coppia all'istantanea.

def test_un_binary_sensor_di_fumo_diventa_un_oggetto_di_sicurezza(archivio):
    """Mutazione ESEGUITA (17/09/2026): in `build_episodes`, chiamare
    `genre_for(subject, None, judgments=judgments)` invece di passare
    `r.get("device_class")` -- `genre_for` torna `None` per un
    `binary_sensor` senza classe, e questo episodio non nasce (conteggio 0)."""
    archivio.record(quando_ts=ts(2, 0), source="entita",
                    subject="binary_sensor.fumo_cucina", da="off", a="on",
                    device_class="smoke")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    o = cronaca(archivio)[0]
    assert o["genere"] == "sicurezza"
    assert o["chi"] == "binary_sensor.fumo_cucina"


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
    oggetto <<presenza, stato unavailable>> di un minuto per ogni persona.

    Dal 06/10/2026 (Task 1.4 degli attori, Passo 3, D5) quel minuto e' una
    voce -- ma d'ASSENZA della fonte, col genere delle condizioni di sistema,
    non una presenza: «fuori casa» resta una cosa che la persona ha fatto,
    «non risponde» una cosa della fonte."""
    archivio.record(quando_ts=ts(9, 0), source="entita",
                    subject="person.paolo", da="home", a="unavailable")
    archivio.record(quando_ts=ts(9, 1), source="entita",
                    subject="person.paolo", da="unavailable", a="home")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    [voce] = cronaca(archivio)
    assert (voce["genere"], voce["cosa"]) == (tv.SYSTEM_GENRE, "unavailable")


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
    o = cronaca(archivio)[0]
    assert o["genere"] == "sicurezza"
    assert o["quando_ts"] == ts(1, 0)
    assert o["fine_ts"] == ts(9, 0)


# -- Punto 5: le misure non sconfinano nel prossimo episodio, ne' partono --
# -- prima dell'inizio dell'oggetto -----------------------------------------

def test_un_sensore_co_numerico_non_genera_un_oggetto_di_sicurezza(archivio):
    """Un `sensor` MISURA, non SCATTA: senza una soglia onesta, una
    concentrazione come "0.4" non e' mai in `_RESTING` e aprirebbe un oggetto
    di sicurezza perennemente aperto al giorno, per ogni sensore CO
    numerico della casa. Mutazione ESEGUITA (17/09/2026, riscritta: l'eccezione
    `dominio == "sensor"` di `genre_for` non esiste piu', ora e' l'assenza di
    una riga `genere` nel seme): dare `genre=Ours("sicurezza")` alla coppia
    `sensor`/`carbon_monoxide` nel letterale -- rossa, conteggio 1 invece di 0."""
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


def test_il_confine_di_inizio_esclude_l_istante_prima_di_mezzanotte():
    """MEZZANOTTE - 1 e' l'ultimo istante del giorno che finisce: deve restare
    FUORI da G. La finestra e' semi-aperta -- `[inizio, fine)` -- ed e' quello
    che fa combaciare due giorni adiacenti senza sovrapporli.

    **La prova guarda la finestra, non il conteggio degli oggetti.** Fino al
    10/09/2026 asseriva «G produce zero oggetti», e quella spia ha smesso di
    dire cio' che sembrava: da quando l'aggregazione semina cio' che era gia'
    in corso a mezzanotte, un termostato acceso un secondo prima **e' un fatto
    di G** -- acceso lo era. Il confine non e' cambiato; era la spia a
    misurare un'altra cosa.

    Mutazione: `from_ts - 1` dentro `day_boundaries` ("per stare sicuri").
    """
    da_ts, a_ts = day_boundaries(G, "Europe/Rome")
    assert da_ts == MEZZANOTTE
    assert a_ts == MEZZANOTTE + 24 * 3600
    assert day_boundaries("2026-08-23", "Europe/Rome")[1] == da_ts


def test_un_cambio_di_un_secondo_prima_appartiene_al_giorno_che_finisce(archivio):
    """Lo stesso confine, visto dagli oggetti: il CAMBIO e' del 23 (e' li' che
    e' successo), e in G quel termostato risulta acceso **dall'istante vero**,
    non da mezzanotte."""
    _watched(archivio, "climate.camera_t")
    archivio.record(quando_ts=MEZZANOTTE - 1, source="entita",
                    subject="climate.camera_t", da="off", a="heat")

    assert aggregate_day(store=archivio, day="2026-08-23",
                         timezone="Europe/Rome") == 1
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    assert cronaca(archivio)[0]["quando_ts"] == MEZZANOTTE - 1


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
    # **Uno, non due** (15/09/2026): il CONTATORE del gas non produce piu'
    # un episodio -- l'energia e' un numero, e i numeri stanno fra le misure.
    # Il RILEVATORE si', ed e' il punto della prova: le due classi `gas` si
    # chiamano uguale e non sono la stessa cosa.
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    oggetti = {o["chi"]: o for o in cronaca(archivio)}
    assert "sensor.gas_contatore" not in oggetti, (
        "un contatore non e' un episodio: il suo numero sta fra le misure")
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
    o = cronaca(archivio)[0]
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
    o = cronaca(archivio)[0]
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
    oggetti = cronaca(archivio)
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
    o = cronaca(archivio)[0]
    assert o["quando_ts"] == ts(21, 0)
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
    o = cronaca(archivio)[0]
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
    o = cronaca(archivio)[0]
    assert o["quando_ts"] == ts(6, 0)
    assert o["fine_ts"] == ts(8, 1)


# -- Punto 2: `unavailable`/`unknown` sono trasparenti, non un riposo -- il
# -- funzionamento e la sicurezza li trattavano come "spento" perche'
# -- `_UNKNOWN` era un sottoinsieme di `_RESTING`.

def test_un_termostato_che_passa_da_unavailable_si_interrompe_e_ne_riparte_uno(archivio):
    """La prova (c) del piano, con D5 «raccolte» (06/10/2026): un riscaldamento
    acceso alle 15:30, `unavailable` alle 18:00, di nuovo `heat` alle 18:05,
    spento alle 20:00. Fino alla regola 3 era UNA voce, 15:30 -> 20:00: il
    buco si saltava. Ora sono tre: l'accensione interrotta alle 18, l'assenza
    dalle 18 alle 18:05, e un'accensione nuova dalle 18:05 alle 20 -- di quei
    cinque minuti non si sa niente, e la cronaca non li racconta come
    riscaldamento.

    (Questa prova e il suo gemello sull'allarme difendevano il salto: il
    gemello e' uscito, diceva la stessa proprieta' su un altro genere.)"""
    archivio.record(quando_ts=ts(15, 30), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    archivio.record(quando_ts=ts(18, 0), source="entita",
                    subject="climate.camera_t", da="heat", a="unavailable")
    archivio.record(quando_ts=ts(18, 5), source="entita",
                    subject="climate.camera_t", da="unavailable", a="heat")
    archivio.record(quando_ts=ts(20, 0), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 3
    assert [(v["genere"], v["cosa"], v["quando_ts"], v["fine_ts"], v.get("interrotto"))
            for v in cronaca(archivio)] == [
        ("funzionamento", "heat", ts(15, 30), ts(18, 0), True),
        (tv.SYSTEM_GENRE, "unavailable", ts(18, 0), ts(18, 5), None),
        ("funzionamento", "heat", ts(18, 5), ts(20, 0), None)]




# -- Punto 3: il riepilogo dell'energia non deve ingerire un 'unavailable' -
# -- da riavvio a bordo giornata.

def test_il_nome_salvato_nel_grezzo_entra_nel_corpo_dell_oggetto(archivio):
    """Mutazione ESEGUITA: togliere le tre righe `nome = names.get(subject)` /
    `if nome:` / `base_body["nome"] = nome` da `close()` (`mind/facts.py`) --
    il test torna rosso su `assert corpo["nome"] == "Termostato Camera"`
    (`KeyError: 'nome'`).
    """
    archivio.record(quando_ts=ts(15, 30), source="entita",
                    subject="climate.camera_t", da="off", a="heat",
                    friendly_name="Termostato Camera")
    archivio.record(quando_ts=ts(17, 5), source="entita",
                    subject="climate.camera_t", da="heat", a="off",
                    friendly_name="Termostato Camera")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    corpo = cronaca(archivio)[0]
    assert corpo["nome"] == "Termostato Camera"
    # L'identificatore NON si perde: il nome si aggiunge accanto al grezzo,
    # non al suo posto -- e' cio' che distingue due entita' omonime.
    assert cronaca(archivio)[0]["chi"] == "climate.camera_t"


def test_senza_nome_nel_grezzo_la_chiave_TACE_non_diventa_null(archivio):
    """Un `nome: null` sarebbe un buco travestito da dato: la chiave non c'e'
    proprio, come `dominio`/`titolo` quando non hanno niente da dire. E' la
    condizione su cui la pagina decide di dichiarare l'identificatore.

    Mutazione ESEGUITA: scrivere `base_body["nome"] = names.get(subject)`
    senza la guardia `if nome:` (`mind/facts.py`, `close()`) -- il test
    torna rosso su `assert "nome" not in corpo`.
    """
    archivio.record(quando_ts=ts(15, 30), source="entita",
                    subject="climate.senza_nome", da="off", a="heat")
    archivio.record(quando_ts=ts(17, 5), source="entita",
                    subject="climate.senza_nome", da="heat", a="off")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    corpo = cronaca(archivio)[0]
    assert "nome" not in corpo
    assert corpo["cosa"] == "heat"


def test_una_condizione_di_sistema_non_porta_un_nome_amichevole(archivio):
    """Un `integrazione:`/`problema:`/`log:` non e' un'entita': non ha un
    `friendly_name`, e ha gia' il suo `titolo`. La chiave non deve comparire
    nemmeno vuota.

    Mutazione ESEGUITA: la stessa del test qui sopra sulla guardia `if nome:`
    -- il test torna rosso su `assert "nome" not in corpo`.
    """
    archivio.record(quando_ts=ts(9), source="sistema",
                    subject="integrazione:01ABC", da=None, a="setup_retry",
                    domain="lifx", title="Abat-jour")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    corpo = cronaca(archivio)[0]
    assert "nome" not in corpo
    assert corpo["titolo"] == "Abat-jour"


def test_il_giorno_dell_aggiornamento_il_primo_nome_NON_VUOTO_vince(archivio):
    """Il caso vero del primo avvio dopo l'aggiornamento: i cambi scritti
    prima della colonna non portano il nome, quelli scritti dopo si', e il
    proprietario legge la pagina proprio quel giorno. Un `None` non e' un
    nome, e' l'assenza di uno: saltarlo per prendere il nome che una riga
    successiva dello STESSO soggetto, nello STESSO giorno, dichiara davvero
    non inventa niente -- non e' l'anagrafe di oggi, e' il grezzo di allora.

    Mutazione ESEGUITA: sostituire `if name and r["soggetto"] not in names:`
    con `names.setdefault(r["soggetto"], name)` (che registra anche il
    `None` della prima riga) -- il test torna rosso su
    `assert corpo["nome"] == "Paolo"`.
    """
    archivio.record(quando_ts=ts(8, 10), source="entita",
                    subject="person.paolo", da="home", a="not_home")
    archivio.record(quando_ts=ts(12, 0), source="entita",
                    subject="person.paolo", da="not_home", a="not_home",
                    friendly_name="Paolo")
    archivio.record(quando_ts=ts(17, 34), source="entita",
                    subject="person.paolo", da="not_home", a="home",
                    friendly_name="Paolo")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    corpo = cronaca(archivio)[0]
    assert corpo["nome"] == "Paolo"


# ---------------------------------------------------------------------------
# La classe entra nel corpo dell'oggetto (fetta «lo stato», 07/09/2026).
# Non e' un dato «per ogni evenienza»: e' il SECONDO dei quattro gradini con
# cui Home Assistant traduce uno stato, e senza di lei quel gradino non
# potrebbe mai rispondere. Come il nome, viene dal GREZZO di quel giorno --
# gli oggetti vivono piu' a lungo dei 22 giorni di grezzo.
# ---------------------------------------------------------------------------

def test_la_classe_del_grezzo_entra_nel_corpo_dell_oggetto(archivio):
    """Mutazione ESEGUITA: togliere `"classe": r.get("device_class")`
    dall'apertura del ramo `sicurezza` in `aggregate_day` (`mind/facts.py`) --
    il test torna rosso su `assert corpo["classe"] == "smoke"`
    (`KeyError: 'classe'`).
    """
    archivio.record(quando_ts=ts(15, 30), source="entita",
                    subject="binary_sensor.fumo_cucina", da="off", a="on",
                    device_class="smoke")
    archivio.record(quando_ts=ts(17, 5), source="entita",
                    subject="binary_sensor.fumo_cucina", da="on", a="off",
                    device_class="smoke")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    corpo = cronaca(archivio)[0]
    assert corpo["classe"] == "smoke"
    # Lo stato GREZZO resta quello che era: la classe si aggiunge accanto,
    # non lo sostituisce ne' lo riscrive.
    assert corpo["cosa"] == "on"


def test_senza_classe_nel_grezzo_la_chiave_TACE_non_diventa_null(archivio):
    """Stessa disciplina di `nome`/`dominio`/`titolo`: un `classe: null`
    sarebbe un buco travestito da dato. Chi rende cade allora sul terzo
    gradino, che e' la verita' -- «di quella riga non sappiamo la classe» --
    non un'invenzione.

    Mutazione ESEGUITA: scrivere `base_body["classe"] = o.get("classe")`
    senza la guardia `if o.get("classe"):` (`mind/facts.py`, `close()`) -- il
    test torna rosso su `assert "classe" not in corpo`.
    """
    archivio.record(quando_ts=ts(15, 30), source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    archivio.record(quando_ts=ts(17, 5), source="entita",
                    subject="climate.camera_t", da="heat", a="off")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    corpo = cronaca(archivio)[0]
    assert "classe" not in corpo
    assert corpo["cosa"] == "heat"


def test_una_condizione_di_sistema_non_porta_nessuna_classe(archivio):
    """Un `integrazione:`/`problema:`/`log:` non e' un'entita' e non ha una
    `device_class`: la chiave non deve comparire nemmeno vuota. E' lo stesso
    confine che tiene fuori quei soggetti dal vocabolario degli stati al
    confine dell'API."""
    archivio.record(quando_ts=ts(9, 0), source="sistema",
                    subject="integrazione:01ABC", da=None, a="setup_retry",
                    domain="lifx", title="Abat-jour")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    corpo = cronaca(archivio)[0]
    assert corpo["cosa"] == "setup_retry"
    assert "classe" not in corpo


def test_un_episodio_gia_aperto_prima_del_giorno_esiste_anche_oggi(archivio):
    """**Il difetto misurato in produzione il 10/09/2026.** Un termostato
    acceso il 06/09 e mai piu' cambiato ha prodotto otto oggetti quel giorno e
    **zero** il 07, l'08 e il 09 -- eppure era acceso tutto il tempo.

    L'aggregazione leggeva solo i cambi DENTRO il giorno, e un fatto che dura
    non ha cambi dentro il giorno: comincia prima. Lo stato in cui la casa era
    a mezzanotte si chiede all'archivio (`last_before`), e l'episodio nasce
    aperto con la sua data d'inizio VERA -- non con la mezzanotte, che
    direbbe una bugia su quando e' cominciato.

    Mutazione che la uccide: togliere la semina dallo stato precedente --
    zero oggetti, esattamente cio' che la casa vera produceva.
    """
    ieri = MEZZANOTTE - 8 * 3600
    _watched(archivio, "climate.camera_t")
    archivio.record(quando_ts=ieri, source="entita", subject="climate.camera_t",
                    da="off", a="heat")

    quanti = aggregate_day(store=archivio, day=G, timezone="Europe/Rome")

    assert quanti == 1
    oggetto = cronaca(archivio)[0]
    assert oggetto["genere"] == "funzionamento"
    assert oggetto["chi"] == "climate.camera_t"
    assert oggetto["quando_ts"] == ieri      # la data vera, non la mezzanotte
    assert oggetto["fine_ts"] is None        # ancora in corso a fine giornata


def test_cio_che_era_spento_prima_del_giorno_non_apre_niente(archivio):
    """La semina porta lo stato, non un episodio: se a mezzanotte era spento,
    non c'e' niente in corso da raccontare. Il soggetto e' nello scope: fuori,
    la prova passerebbe per la ragione sbagliata (05/10/2026)."""
    _watched(archivio, "climate.camera_t")
    archivio.record(quando_ts=MEZZANOTTE - 8 * 3600, source="entita",
                    subject="climate.camera_t", da="heat", a="off")

    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 0


def test_un_episodio_cominciato_ieri_e_finito_oggi_si_chiude_con_l_inizio_vero(archivio):
    """Prima, il cambio che CHIUDE non trovava niente di aperto e si perdeva:
    l'accensione era in un altro giorno. Ora chiude l'episodio giusto, e la
    durata e' quella vera."""
    ieri = MEZZANOTTE - 3 * 3600
    _watched(archivio, "light.cucina")
    archivio.record(quando_ts=ieri, source="entita", subject="light.cucina",
                    da="off", a="on")
    archivio.record(quando_ts=ts(7), source="entita", subject="light.cucina",
                    da="on", a="off")

    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")

    oggetto = cronaca(archivio)[0]
    assert (oggetto["quando_ts"], oggetto["fine_ts"]) == (ieri, ts(7))

def test_aggregate_day_scrive_nel_resoconto_l_obiettivo_di_QUEL_giorno(archivio):
    """**L'obiettivo che valeva allora, non quello di oggi** (spec §11). Chi
    legge trenta giorni di misure in serie deve sapere se in mezzo la domanda
    e' cambiata, o legge una tendenza dove c'e' un cambio d'obiettivo.

    Si scrive un obiettivo PRIMA del giorno e uno DOPO: quello che finisce nel
    resoconto dev'essere il primo, o la riga starebbe dicendo che il giorno
    rispondeva a una domanda che ancora non esisteva.

    Mutazione ESEGUITA: passare `objective=None` in `aggregate_day` -- rossa
    su `assert scritto["obiettivo"]["testo"] == "quella di allora"`.
    """
    da_ts, a_ts = day_boundaries(G, "Europe/Rome")
    archivio.set_objective("quella di allora", when_ts=da_ts - 3600.0)
    archivio.set_objective("quella di dopo", when_ts=a_ts + 3600.0)
    archivio.record(quando_ts=ts(15, 30), source="entita",
                    subject="climate.camera_t", da="off", a="heat")

    aggregate_day(store=archivio, day=G, timezone="Europe/Rome",
                  recipes={}, series={}, names={})

    scritto = archivio.report(G)
    assert scritto["obiettivo"]["testo"] == "quella di allora"

def test_il_nome_del_DISPOSITIVO_arriva_alle_misure(archivio):
    """**Difetto trovato leggendo la prima analisi vera, il 15/09/2026**:
    l'analista parlava al proprietario in esadecimale -- «513a6661 ·
    prelievo» invece di «Inverter · prelievo». Misurato sul resoconto del
    giorno: **zero misure su 73 portavano un nome**.

    La causa: `aggregate_day` riceve `names` -- i nomi dei DISPOSITIVI, per
    chiave l'id del dispositivo -- e poi riusa la stessa variabile per i nomi
    delle ENTITA' letti dal grezzo, per chiave l'`entity_id`. Due cose diverse
    dette con una parola sola: la seconda cancellava la prima, e nessuna prova
    guardava.

    Mutazione: rimettere una variabile sola -- rossa.
    """
    archivio.record(quando_ts=ts(15, 30), source="entita",
                    subject="climate.camera_t", da="off", a="heat",
                    friendly_name="Termostato Camera")

    aggregate_day(store=archivio, day=G, timezone="Europe/Rome",
                  recipes={"dev1": {"why": "la produzione", "steps": [
                      {"name": "totale", "operation": "somma_periodo",
                       "inputs": ["@sensor.p"], "params": {"unit": "kWh"}}]}},
                  series={"sensor.p": [{"inizio": 0.0, "fine": 3600.0,
                                        "valore": 2.0}]},
                  names={"dev1": "Inverter"})

    scritto = archivio.report(G)
    assert scritto["misure"][0]["nome"] == "Inverter", "il nome del dispositivo"
    # E il nome dell'ENTITA' continua ad arrivare alla cronaca: sono due
    # strade diverse, e questa correzione non deve chiuderne una per aprire
    # l'altra.
    assert scritto["cronaca"][0]["nome"] == "Termostato Camera"


# ---------------------------------------------------------------------------
# Il genere e il riposo dall'istantanea dei giudizi (spec 2026-09-16 §5).
# Una regola sola per l'apertura: un episodio e' APERTO quando lo stato non e'
# a riposo PER IL SUO SOGGETTO. `none` e il vuoto non aprono e non chiudono.
# ---------------------------------------------------------------------------

def _giudizi(*righe):
    """Il seme del repo piu' le righe che la casa scrive sopra."""
    return TypeJudgments.from_rows(tv.judgment_seed_rows() + righe,
                                   genres=tv.CHRONICLE_GENRES,
                                   absent_forms=tv.ABSENT_STATE_FORMS.value)


def test_un_sensore_di_presenza_col_genere_scritto_dalla_casa_APRE_a_on_e_CHIUDE_a_off(archivio):
    """Spec §5, la regola unica. Mutazione ESEGUITA: rimettere il ramo della
    presenza che chiude solo su `home` -- rossa (l'episodio resta aperto)."""
    archivio.record(quando_ts=ts(9, 0), source="entita", subject="binary_sensor.fp300",
                    da="off", a="on", device_class="occupancy")
    archivio.record(quando_ts=ts(9, 30), source="entita", subject="binary_sensor.fp300",
                    da="on", a="off", device_class="occupancy")
    giudizi = _giudizi(("tipo", "binary_sensor.occupancy", "genere", "presenza"))
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome", judgments=giudizi) == 1
    voce = cronaca(archivio)[0]
    assert voce["genere"] == "presenza" and voce["fine_ts"] == ts(9, 30)


def test_senza_la_riga_della_casa_il_sensore_di_presenza_resta_MUTO_come_oggi(archivio):
    """I sensori di presenza non entrano nel seme: li scrive il proprietario
    (spec §5). Mutazione ESEGUITA: aggiungere la riga `genere` `presenza` di
    `binary_sensor.occupancy` a `judgment_seed_rows()` -- rossa (conteggio 1)."""
    archivio.record(quando_ts=ts(9, 0), source="entita", subject="binary_sensor.fp300",
                    da="off", a="on", device_class="occupancy")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 0


def test_l_assenza_di_una_persona_resta_quella_di_oggi(archivio):
    """Mutazione ESEGUITA: togliere `riposo` da `person` nel seme -- rossa (a
    `home` l'assenza non chiude piu')."""
    archivio.record(quando_ts=ts(8, 0), source="entita", subject="person.marta",
                    da="home", a="not_home")
    archivio.record(quando_ts=ts(17, 0), source="entita", subject="person.marta",
                    da="not_home", a="home")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    voce = cronaca(archivio)[0]
    assert voce["cosa"] == "not_home" and voce["fine_ts"] == ts(17, 0)


def test_none_su_un_tracker_NON_apre_un_assenza_della_persona(archivio):
    """Cambio dichiarato (spec §1 misura 8): 200 righe `none` in una settimana
    da 6 apparati di rete aprivano assenze false di presenza. Restano fuori
    dalla presenza; dal 06/10/2026 (D5) il `none` e' una voce d'assenza della
    FONTE, col genere delle condizioni di sistema."""
    archivio.record(quando_ts=ts(23, 0), source="entita", subject="device_tracker.switch_2",
                    da="home", a="none")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    [voce] = cronaca(archivio)
    assert (voce["genere"], voce["cosa"], voce["fine_ts"]) == (tv.SYSTEM_GENRE, "none", None)


def test_none_su_uno_switch_interrompe_e_NON_apre(archivio):
    """Su uno `switch` `none` chiudeva l'episodio come un riposo (spec §1
    misura 8); dal 17/09/2026 non chiudeva e non apriva niente; dal 06/10/2026
    (D5 «raccolte») lo INTERROMPE e apre l'assenza -- che non e' un riposo e
    non e' un'accensione. Sulla presa spenta non apre nessun episodio: solo
    la voce d'assenza.

    Mutazione ESEGUITA: rimettere il salto delle assenze in cima al ciclo del
    giorno -- rossa (una voce sola: l'accensione delle 10, ancora aperta)."""
    archivio.record(quando_ts=ts(10, 0), source="entita", subject="switch.accesso_internet",
                    da="off", a="on")
    archivio.record(quando_ts=ts(23, 0), source="entita", subject="switch.accesso_internet",
                    da="on", a="none")
    archivio.record(quando_ts=ts(9, 0), source="entita", subject="switch.presa",
                    da="on", a="off")
    archivio.record(quando_ts=ts(22, 0), source="entita", subject="switch.presa",
                    da="off", a="none")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 3
    assert [(v["chi"], v["genere"], v["quando_ts"], v["fine_ts"], v.get("interrotto"))
            for v in cronaca(archivio)] == [
        ("switch.accesso_internet", "funzionamento", ts(10), ts(23), True),
        ("switch.presa", tv.SYSTEM_GENRE, ts(22), None, None),
        ("switch.accesso_internet", tv.SYSTEM_GENRE, ts(23), None, None)]


def test_none_prima_della_mezzanotte_e_un_assenza_della_fonte_ereditata(archivio):
    """Lo stesso cambio, sulla strada di cio' che era gia' in corso a
    mezzanotte (`_replay_open`): un tracker lasciato a `none` la sera prima
    non e' una presenza cominciata ieri -- e' una fonte che da ieri non
    risponde, e la voce lo dice dall'inizio vero. Solo per chi e' nello scope:
    il soggetto ci entra, o la prova passerebbe per la ragione sbagliata."""
    _watched(archivio, "device_tracker.switch_2")
    archivio.record(quando_ts=MEZZANOTTE - 3600, source="entita",
                    subject="device_tracker.switch_2", da="home", a="none")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    [voce] = cronaca(archivio)
    assert (voce["genere"], voce["quando_ts"], voce["fine_ts"]) == (
        tv.SYSTEM_GENRE, MEZZANOTTE - 3600, None)


def test_un_giudizio_della_casa_su_UNA_entita_la_tace(archivio):
    """`nessuno` su un'entita' nega il genere del suo dominio (spec §3).
    Mutazione ESEGUITA: in `build_episodes`, chiamare `genre_for` senza
    `judgments=` -- rossa (conteggio 1: vale il seme, `switch` e'
    `funzionamento`)."""
    archivio.record(quando_ts=ts(10, 0), source="entita", subject="switch.accesso_internet",
                    da="off", a="on")
    giudizi = _giudizi(("entita", "switch.accesso_internet", "genere", "nessuno"))
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome", judgments=giudizi) == 0


def test_il_riposo_e_quello_del_SOGGETTO_non_l_unione_dei_tipi(archivio):
    """Una TV che resta `on` senza riprodurre e' a riposo per QUESTA casa: la
    riga `riposo` sull'entita' chiude l'episodio a `on`. Con l'unione dei
    riposi di tutti i tipi `on` non e' riposo di nessuno, e l'episodio
    resterebbe aperto.

    Mutazione ESEGUITA: in `_is_on`, chiedere il riposo al solo DOMINIO --
    `judgments.resting_of(domain)`, senza la classe ne' l'entita' -- rossa
    (`assert None == 1787605200.0`: `media_player` non dichiara nessun riposo,
    l'episodio non si chiude); ripristinata con l'editor, sha256 identico.

    **La mutazione dichiarata prima era impossibile** (giro di correzioni 1,
    punto 7): citava `type_vocabulary.resting_states()`, uscita col Task 8.
    Il suo bersaglio vero era «non chiedere il riposo del SOGGETTO», che e'
    esattamente cio' che la mutazione qui sopra fa."""
    archivio.record(quando_ts=ts(21, 0), source="entita", subject="media_player.tv",
                    da="on", a="playing")
    archivio.record(quando_ts=ts(23, 0), source="entita", subject="media_player.tv",
                    da="playing", a="on")
    giudizi = _giudizi(("entita", "media_player.tv", "riposo", '["on"]'))
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome", judgments=giudizi) == 1
    assert cronaca(archivio)[0]["fine_ts"] == ts(23, 0)


# ---------------------------------------------------------------------------
# L'impronta nel resoconto e la cronaca rifatta (spec 2026-09-16 §6).
# ---------------------------------------------------------------------------

def test_il_resoconto_porta_l_impronta_dei_giudizi_con_cui_e_nata_la_cronaca(archivio):
    """Spec §6: «la scrive chiunque scriva la cronaca». L'aggregazione notturna,
    la riparazione d'avvio e il recupero passano tutti da `aggregate_day`.
    Mutazione ESEGUITA: in `aggregate_day` scrivere l'impronta di
    `REPO_JUDGMENTS` invece di quella di `judgments` -- rossa (l'istantanea
    della prova ha una riga `genere` in piu', quindi un'altra impronta)."""
    giudizi = _giudizi(("tipo", "binary_sensor.occupancy", "genere", "presenza"))
    assert giudizi.chronicle_fingerprint() != tv.REPO_JUDGMENTS.chronicle_fingerprint()
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome", judgments=giudizi)
    assert archivio.report(G)["giudizio"] == {"impronta": giudizi.chronicle_fingerprint(),
                                              "regola": CHRONICLE_RULE}


def test_rifare_la_cronaca_NON_tocca_misure_forme_obiettivo(archivio):
    """Spec §6: solo `cronaca` e `giudizio` cambiano, byte per byte il resto.
    Mutazione ESEGUITA: in `rebuild_chronicle` chiamare `aggregate_day` (che
    riscrive tutto con misure vuote) -- rossa."""
    import json

    from hiris.app.mind.facts import rebuild_chronicle

    archivio.record(quando_ts=ts(9, 0), source="entita", subject="binary_sensor.fp300",
                    da="off", a="on", device_class="occupancy")
    archivio.replace_report(G, {"giorno": G, "obiettivo": {"testo": "x", "scritto_ts": 1.0},
                                "misure": [{"soggetto": "d", "misura": "m", "valore": 3,
                                            "unita": "kWh", "copertura": 1.0}],
                                "forme": [{"soggetto": "d", "valore": [1, 2]}],
                                "cronaca": [], "giudizio": {"impronta": "vecchia"}})
    prima = archivio.report(G)
    giudizi = _giudizi(("tipo", "binary_sensor.occupancy", "genere", "presenza"))
    assert rebuild_chronicle(store=archivio, day=G, timezone="Europe/Rome", judgments=giudizi)
    dopo = archivio.report(G)
    for chiave in ("giorno", "obiettivo", "misure", "forme"):
        assert json.dumps(dopo[chiave], sort_keys=True) == json.dumps(prima[chiave], sort_keys=True)
    assert len(dopo["cronaca"]) == 1
    assert dopo["giudizio"] == {"impronta": giudizi.chronicle_fingerprint(),
                                "regola": CHRONICLE_RULE}


def test_rifare_la_cronaca_di_un_giorno_SENZA_resoconto_non_scrive_niente(archivio):
    """Rifare la cronaca non e' fare il giorno: un giorno senza resoconto lo fa
    intero il recupero, con le misure. Mutazione ESEGUITA: togliere il ritorno
    anticipato su `report is None` -- rossa (solleva, o scrive un resoconto
    senza misure)."""
    from hiris.app.mind.facts import rebuild_chronicle

    archivio.record(quando_ts=ts(10, 0), source="entita", subject="switch.presa",
                    da="off", a="on")
    assert rebuild_chronicle(store=archivio, day=G, timezone="Europe/Rome",
                             judgments=tv.REPO_JUDGMENTS) is False
    assert archivio.report(G) is None


def test_una_cronaca_senza_impronta_o_con_un_altra_e_VECCHIA():
    """Mutazioni ESEGUITE: (1) considerare vecchia solo un'impronta diversa, non
    l'assenza -- rossa sulla prima (i resoconti scritti prima del 17/09/2026
    non hanno impronta); (2) confrontare con `REPO_JUDGMENTS` invece che con
    `judgments` -- rossa: l'istantanea della prova NON e' il seme (fix round 1,
    la forma di prima col seme lasciava verde questa mutazione)."""
    from hiris.app.mind.facts import chronicle_is_stale

    j = _giudizi(("tipo", "binary_sensor.occupancy", "genere", "presenza"))
    assert j.chronicle_fingerprint() != tv.REPO_JUDGMENTS.chronicle_fingerprint()
    assert chronicle_is_stale({"cronaca": []}, j)
    assert chronicle_is_stale({"giudizio": {"impronta": "altra"}}, j)
    assert chronicle_is_stale(
        {"giudizio": {"impronta": tv.REPO_JUDGMENTS.chronicle_fingerprint()}}, j)
    assert not chronicle_is_stale({"giudizio": {"impronta": j.chronicle_fingerprint(),
                                                "regola": CHRONICLE_RULE}}, j)


def _giorno_ereditato(archivio):
    """Un giorno con un episodio EREDITATO (il termostato acceso da tre giorni),
    uno chiuso dentro il giorno e uno aperto dentro il giorno; scritto col seme
    e marcato con un'impronta vecchia, come un resoconto nato prima."""
    _watched(archivio, "climate.camera")
    archivio.record(quando_ts=MEZZANOTTE - 3 * 86400, source="entita",
                    subject="climate.camera", da="off", a="heat")
    archivio.record(quando_ts=ts(8, 0), source="entita", subject="switch.presa",
                    da="off", a="on")
    archivio.record(quando_ts=ts(9, 0), source="entita", subject="switch.presa",
                    da="on", a="off")
    archivio.record(quando_ts=ts(10, 0), source="entita", subject="light.b",
                    da="off", a="on")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    scritto = archivio.report(G)
    assert [v["chi"] for v in scritto["cronaca"]] == [
        "switch.presa", "climate.camera", "light.b"]
    archivio.replace_report(G, {**scritto, "giudizio": {"impronta": "vecchia"}})
    return scritto["cronaca"]


def test_rifare_la_cronaca_TIENE_l_episodio_ereditato_il_cui_grezzo_e_potato(archivio):
    """Fix round 1 (revisione di Fable, eseguita): la riga d'origine di un
    episodio ereditato da prima di mezzanotte esce dal grezzo prima del giorno
    stesso, e rifare la cronaca lo perdeva. Resta, al suo posto nell'ordine di
    oggi. Mutazioni ESEGUITE: (1) togliere la fusione degli ereditati -- rossa
    (restano due voci); (2) accodarli in fondo invece di inserirli con la
    regola d'ordine -- rossa."""
    from hiris.app.mind.facts import rebuild_chronicle
    from hiris.app.mind.store import READING_RETENTION_S

    prima = _giorno_ereditato(archivio)
    # Il taglio cade un'ora prima di mezzanotte: via la riga d'origine del
    # termostato, restano quelle del giorno.
    archivio.prune(MEZZANOTTE - 3600 + READING_RETENTION_S)
    assert rebuild_chronicle(store=archivio, day=G, timezone="Europe/Rome",
                             judgments=tv.REPO_JUDGMENTS)
    dopo = archivio.report(G)["cronaca"]
    assert [v["chi"] for v in dopo] == ["switch.presa", "climate.camera", "light.b"]
    assert dopo[1] == prima[1]


def test_rifare_la_cronaca_TOGLIE_l_ereditato_il_cui_soggetto_ora_non_ha_genere(archivio):
    """Un ereditato col grezzo potato si tiene solo se il suo soggetto ha
    ancora un genere: un `nessuno` scritto dalla casa lo toglie. Mutazione
    ESEGUITA: tenere l'ereditato senza chiedere il genere -- rossa."""
    from hiris.app.mind.facts import rebuild_chronicle
    from hiris.app.mind.store import READING_RETENTION_S

    _giorno_ereditato(archivio)
    archivio.prune(MEZZANOTTE - 3600 + READING_RETENTION_S)
    giudizi = _giudizi(("entita", "climate.camera", "genere", "nessuno"))
    assert rebuild_chronicle(store=archivio, day=G, timezone="Europe/Rome", judgments=giudizi)
    assert [v["chi"] for v in archivio.report(G)["cronaca"]] == ["switch.presa", "light.b"]


def test_rifare_la_cronaca_TOGLIE_l_ereditato_che_il_grezzo_ancora_smentisce(archivio):
    """Se la riga d'origine c'e' ancora, l'assenza dalla cronaca rifatta e' un
    GIUDIZIO nuovo, non un grezzo perso: qui `heat` diventa un riposo del
    termostato, e l'episodio non c'e' piu'. Tenerlo scriverebbe l'impronta
    nuova su una voce del giudizio vecchio. Mutazione ESEGUITA: tenere
    l'ereditato anche quando `store.last_before` ha ancora il soggetto --
    rossa."""
    from hiris.app.mind.facts import rebuild_chronicle

    _giorno_ereditato(archivio)
    giudizi = _giudizi(("entita", "climate.camera", "riposo", '["off", "heat"]'))
    assert rebuild_chronicle(store=archivio, day=G, timezone="Europe/Rome", judgments=giudizi)
    assert [v["chi"] for v in archivio.report(G)["cronaca"]] == ["switch.presa", "light.b"]


# ── La fonte finita (Task 1.4 degli attori, Passo 1, 05/10/2026) ────────────
#
# Misurato il 05/10/2026 sulla casa vera: delle 85 voci di cronaca sbagliate
# fra il 30/09 e il 04/10, 60 erano episodi «aperti» da giorni di fonti che
# Home Assistant non nomina piu' (12 soggetti, tutti spenti dal proprietario
# con la loro istanza). Un'entita' disabilitata o rimossa non manda un ultimo
# cambio -- `watcher.watch_reading` scarta `new_state` a `None` -- e l'ultima
# riga del grezzo e' l'`unavailable` del riavvio, che la cronaca salta.
# Nessuno chiedeva alla fonte se fosse ancora viva: ora si chiede a
# `House.source`, la fonte della Tappa 3.
#
# Le righe hanno la forma che `watcher.watch_reading` scrive: `da`/`a` dello
# stato, `fonte = 'entita'`. Le case sono scritte nella forma delle righe di
# Home Assistant (`config/entity_registry/list`, `config_entries/get`, gli
# stati) e passano dal lettore vero, come in `tests/test_fonte_della_casa.py`.
#
# Mutazioni ESEGUITE (05/10/2026), ognuna ripristinata con sha256 identico e
# `git status` riletto, tutte rosse per la ragione giusta:
# - la chiusura per la fonte tolta (`if house is not None` -> `if False`) --
#   rosse la spenta, la sparita ereditata e la cronaca rifatta;
# - solo `sparita` chiude (non le spente) -- rosse la spenta e la rifatta;
# - l'ultima riga DOPO il giorno non lascia piu' aperto -- rossa la «dopo»;
# - l'ereditato finito prima del giorno chiuso invece che tolto -- rossa la
#   sparita ereditata;
# - `chronicle_is_stale` confronta la sola impronta -- rossa la regola;
# - tolto `house=` dalla chiamata di `rebuild_chronicle` in `server.py` --
#   rossa la prova delle chiamate, con file e riga.


def _house(*, entities=(), states=(), entries=()):
    """Una casa: registro delle entita', stati vivi e istanze, nella forma di
    Home Assistant, montata come la monta il prodotto."""
    from hiris.app.home_space.house import House
    from hiris.app.home_space.reader import build_home_space
    from hiris.app.home_space.topology import live_mirror
    from hiris.app.proxy.entity_cache import _to_minimal

    entita = [{"entity_id": eid, "platform": "demo", "disabled_by": None,
               "hidden_by": None, **extra} for eid, extra in entities]
    mirror = live_mirror([_to_minimal({"entity_id": eid, "state": st, "attributes": {}})
                          for eid, st in states])
    return House(build_home_space({"entita": entita, "integrazioni": list(entries),
                                   "dispositivi": []}), mirror)


#: L'istanza spenta dal proprietario: in Home Assistant `ConfigEntryDisabler`
#: ha un valore solo, `user`. E' il caso misurato sulla casa vera.
_ENTRY_SWITCHED_OFF = {"entry_id": "e_spenta", "domain": "demo", "title": "Demo",
                       "state": "not_loaded", "source": "user", "disabled_by": "user"}


def _house_with_entry_switched_off(subject):
    return _house(entities=[(subject, {"config_entry_id": "e_spenta",
                                       "disabled_by": "config_entry"})],
                  entries=[_ENTRY_SWITCHED_OFF])


def _watched(archivio, *soggetti):
    for soggetto in soggetti:
        archivio.decide_scope(soggetto, inside=True, reason="prova", author="observer")


def test_l_episodio_di_una_fonte_spenta_si_chiude_alla_sua_ultima_riga_con_la_causa(archivio):
    """Acceso alle 8, poi l'`unavailable` alle 10, poi niente: la sua istanza
    e' stata spenta dal proprietario. L'accensione e' interrotta alle 10 dal
    buco (Passo 3); l'assenza che comincia alle 10 non resta «in corso»: si
    chiude all'ultima cosa che Home Assistant ne ha detto, e la voce dice
    perche', con la causa della fonte."""
    archivio.record(quando_ts=ts(8), source="entita", subject="switch.pompa",
                    da="off", a="on")
    archivio.record(quando_ts=ts(10), source="entita", subject="switch.pompa",
                    da="on", a="unavailable")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome",
                  house=_house_with_entry_switched_off("switch.pompa"))
    accesa, assente = cronaca(archivio)
    assert (accesa["quando_ts"], accesa["fine_ts"], accesa["interrotto"]) == (ts(8), ts(10), True)
    assert (assente["genere"], assente["quando_ts"], assente["fine_ts"]) == (
        tv.SYSTEM_GENRE, ts(10), ts(10))
    assert assente["chiusa_dalla_fonte"] == {"stato": "spenta_dal_proprietario",
                                             "causa": "config_entry", "spenta_da": "user"}


def test_l_episodio_ereditato_di_una_fonte_sparita_non_entra_nel_giorno_dopo(archivio):
    """Il caso delle 60 voci, nella sua forma vera: l'ultima riga del grezzo
    e' l'accensione di ieri (il riavvio di Home Assistant non ha lasciato
    righe), poi l'entita' e' sparita. Oggi non c'e' niente in corso:
    l'episodio e' finito ieri, alla sua ultima riga, e non si eredita."""
    _watched(archivio, "climate.studio")
    archivio.record(quando_ts=MEZZANOTTE - 10 * 3600, source="entita",
                    subject="climate.studio", da="off", a="heat")
    sparita = _house(entities=[("climate.studio", {})], states=[("light.altra", "on")])
    assert sparita.source("climate.studio")["stato"] == "sparita"

    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome", house=sparita) == 0


def test_senza_la_casa_niente_si_chiude_per_la_fonte(archivio):
    """La casa non letta non dice che una fonte e' finita: l'episodio resta
    com'era (e' il ripiego delle prove e di chi non ha l'anagrafe)."""
    _watched(archivio, "climate.studio")
    archivio.record(quando_ts=MEZZANOTTE - 10 * 3600, source="entita",
                    subject="climate.studio", da="off", a="heat")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome", house=None) == 1


def test_una_fonte_solo_non_disponibile_resta_assente_in_corso(archivio):
    """`non_disponibile` parla ancora: un riavvio la fa passare di li' e torna
    da sola. Non e' una fonte finita: l'accensione e' interrotta dal buco, e
    l'assenza resta in corso a fine giornata, senza `chiusa_dalla_fonte`."""
    archivio.record(quando_ts=ts(8), source="entita", subject="switch.pompa",
                    da="off", a="on")
    archivio.record(quando_ts=ts(10), source="entita", subject="switch.pompa",
                    da="on", a="unavailable")
    casa = _house(entities=[("switch.pompa", {})], states=[("switch.pompa", "unavailable")])
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome", house=casa)
    accesa, assente = cronaca(archivio)
    assert accesa["fine_ts"] == ts(10)
    assert (assente["genere"], assente["fine_ts"]) == (tv.SYSTEM_GENRE, None)
    assert "chiusa_dalla_fonte" not in accesa and "chiusa_dalla_fonte" not in assente


def test_una_fonte_sparita_DOPO_il_giorno_lascia_l_episodio_aperto_a_fine_giornata(archivio):
    """La fonte e' quella di adesso, ma il giorno e' quello di allora: se Home
    Assistant ne ha parlato DOPO la fine del giorno, a fine giornata era
    ancora accesa, e la voce lo dice come sempre."""
    archivio.record(quando_ts=ts(8), source="entita", subject="switch.pompa",
                    da="off", a="on")
    archivio.record(quando_ts=ts(26), source="entita", subject="switch.pompa",
                    da="on", a="unavailable")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome",
                  house=_house_with_entry_switched_off("switch.pompa"))
    [voce] = cronaca(archivio)
    assert voce["fine_ts"] is None
    assert "chiusa_dalla_fonte" not in voce


def test_rifare_la_cronaca_chiede_la_fonte_anche_lei(archivio):
    """La stessa regola dalla seconda porta che scrive la cronaca."""
    from hiris.app.mind.facts import rebuild_chronicle

    archivio.record(quando_ts=ts(8), source="entita", subject="switch.pompa",
                    da="off", a="on")
    archivio.record(quando_ts=ts(10), source="entita", subject="switch.pompa",
                    da="on", a="unavailable")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome", house=None)
    assert cronaca(archivio)[1]["fine_ts"] is None
    assert rebuild_chronicle(store=archivio, day=G, timezone="Europe/Rome",
                             judgments=tv.REPO_JUDGMENTS,
                             house=_house_with_entry_switched_off("switch.pompa"))
    assert cronaca(archivio)[1]["fine_ts"] == ts(10)


def test_una_cronaca_scritta_con_la_regola_di_prima_e_VECCHIA():
    """La regola con cui si costruisce la cronaca e' cambiata (la fonte
    finita): i resoconti scritti prima si riconoscono, come per l'impronta
    dei giudizi, e il recupero li rifa' finche' il grezzo c'e'."""
    from hiris.app.mind.facts import chronicle_is_stale

    j = tv.REPO_JUDGMENTS
    impronta = j.chronicle_fingerprint()
    assert chronicle_is_stale({"giudizio": {"impronta": impronta}}, j)
    assert chronicle_is_stale({"giudizio": {"impronta": impronta,
                                            "regola": CHRONICLE_RULE - 1}}, j)
    assert not chronicle_is_stale({"giudizio": {"impronta": impronta,
                                                "regola": CHRONICLE_RULE}}, j)


def test_ogni_chiamata_di_produzione_porta_la_casa():
    """Un parametro col ripiego `None` e' inerte in silenzio se un chiamante
    se lo dimentica: chi in `mind/facts.py` DICHIARA di ricevere `house` deve
    essere chiamato con `house=`, in tutto `hiris/app`. L'elenco si chiede
    alle firme, non si ricopia."""
    import ast
    import pathlib

    radice = pathlib.Path(__file__).resolve().parents[1] / "hiris" / "app"
    facts = ast.parse((radice / "mind" / "facts.py").read_text(encoding="utf-8"))
    sorvegliate = {n.name for n in ast.walk(facts)
                   if isinstance(n, ast.FunctionDef)
                   and "house" in [a.arg for a in n.args.kwonlyargs]}
    assert {"build_episodes", "aggregate_day", "rebuild_chronicle"} <= sorvegliate
    viste, mancanti = 0, []
    for percorso in radice.rglob("*.py"):
        for nodo in ast.walk(ast.parse(percorso.read_text(encoding="utf-8"))):
            if not isinstance(nodo, ast.Call):
                continue
            nome = getattr(nodo.func, "id", None) or getattr(nodo.func, "attr", None)
            if nome not in sorvegliate:
                continue
            viste += 1
            if "house" not in [k.arg for k in nodo.keywords]:
                mancanti.append(f"{percorso.name}:{nodo.lineno} {nome}")
    assert viste >= 5, f"viste solo {viste} chiamate: la derivazione si e' rotta"
    assert mancanti == []


# ── L'inizio giusto (Task 1.4 degli attori, Passo 2, 05/10/2026) ────────────
#
# Misurato il 05/10/2026 sulla casa vera: 21 delle 85 voci sbagliate avevano
# l'inizio alla riga di RITORNO dopo un'assenza (l'ultima riga del soggetto
# prima del giorno), non all'inizio vero della sequenza (voce C7 dell'audit);
# 4 venivano da una riga ereditata di un dispositivo fuori dallo scope di
# oggi, vecchia di settimane. L'ereditato si costruisce ora rigiocando le
# transizioni del soggetto con la regola del giorno, dentro una finestra
# dichiarata e solo per chi e' dentro lo scope.
#
# Mutazioni ESEGUITE (05/10/2026), ognuna ripristinata con sha256 identico e
# `git status` riletto, rosse per la ragione giusta:
# - il rigioco tiene l'ULTIMA riga accesa invece della prima (l'ereditato
#   torna all'ultima riga) -- rosse la sequenza e `heat` -> `cool`;
# - il rigioco non salta gli stati «non lo so» -- rossa l'`unavailable`
#   dopo un riposo (la prima forma di questa mutazione era INERTE sulle altre
#   prove: un `unavailable` dopo uno stato acceso non cambia niente, e la
#   prova che la discrimina e' nata per questo);
# - la finestra tolta (`window_start = 0.0`) -- rossa la riga vecchia;
# - lo scope non chiesto -- rossa la prova dello scope;
# - la seconda lettura di `last_before` rimessa in `rebuild_chronicle` --
#   rossa la prova della lettura unica (A-39).


def test_l_ereditato_dopo_un_buco_comincia_al_ritorno_e_il_buco_resta_ieri(archivio):
    """Acceso ieri alle 4, `unavailable` alle 14, di nuovo acceso alle 15.
    Con la regola 3 l'`unavailable` non chiudeva niente e l'episodio in corso
    a mezzanotte cominciava alle 4 (voce C7 dell'audit: l'inizio era la riga
    di RITORNO perche' il buco era invisibile). Con D5 «raccolte» (regola 4)
    il buco e' una voce: ieri l'accensione delle 4 e' interrotta alle 14,
    l'assenza dura fino alle 15, e da li' ne comincia una nuova -- che e'
    quella in corso a mezzanotte. Lo stesso rigioco del giorno, quindi lo
    stesso inizio ieri e oggi.

    Mutazione ESEGUITA: nel rigioco saltare le assenze invece di
    interrompere -- rossa (l'inizio torna alle 4)."""
    _watched(archivio, "switch.pompa")
    for quando, da, a in ((-20, "off", "on"), (-10, "on", "unavailable"),
                          (-9, "unavailable", "on")):
        archivio.record(quando_ts=MEZZANOTTE + quando * 3600, source="entita",
                        subject="switch.pompa", da=da, a=a)
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    [voce] = cronaca(archivio)
    assert (voce["quando_ts"], voce["fine_ts"], voce["cosa"]) == (
        MEZZANOTTE - 9 * 3600, None, "on")
    aggregate_day(store=archivio, day="2026-08-23", timezone="Europe/Rome")
    assert [(v["genere"], v["quando_ts"], v["fine_ts"])
            for v in cronaca(archivio, "2026-08-23")] == [
        ("funzionamento", MEZZANOTTE - 20 * 3600, MEZZANOTTE - 10 * 3600),
        (tv.SYSTEM_GENRE, MEZZANOTTE - 10 * 3600, MEZZANOTTE - 9 * 3600),
        ("funzionamento", MEZZANOTTE - 9 * 3600, None)]


def test_un_cambio_fra_due_stati_accesi_non_sposta_l_inizio_ereditato(archivio):
    """La stessa regola del ciclo del giorno: `heat` -> `cool` non riapre
    l'episodio, che resta quello cominciato con `heat`. Prima la cronaca di
    ieri e quella di oggi davano allo stesso episodio due inizi diversi."""
    _watched(archivio, "climate.studio")
    archivio.record(quando_ts=MEZZANOTTE - 20 * 3600, source="entita",
                    subject="climate.studio", da="off", a="heat")
    archivio.record(quando_ts=MEZZANOTTE - 5 * 3600, source="entita",
                    subject="climate.studio", da="heat", a="cool")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    [voce] = cronaca(archivio)
    assert (voce["quando_ts"], voce["cosa"]) == (MEZZANOTTE - 20 * 3600, "heat")


def test_un_unavailable_prima_di_mezzanotte_interrompe_l_ereditato(archivio):
    """Acceso ieri, `unavailable` due ore prima di mezzanotte, e niente piu':
    oggi non c'e' un'accensione in corso -- c'e' un'assenza in corso, dalle
    22 di ieri. Con la regola 3 la cronaca di oggi diceva «acceso dalle 4 di
    ieri» per tutto il buco (il caso della luce dei tre giorni)."""
    _watched(archivio, "switch.pompa")
    archivio.record(quando_ts=MEZZANOTTE - 20 * 3600, source="entita",
                    subject="switch.pompa", da="off", a="on")
    archivio.record(quando_ts=MEZZANOTTE - 2 * 3600, source="entita",
                    subject="switch.pompa", da="on", a="unavailable")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    [voce] = cronaca(archivio)
    assert (voce["genere"], voce["quando_ts"], voce["fine_ts"]) == (
        tv.SYSTEM_GENRE, MEZZANOTTE - 2 * 3600, None)


def test_un_unavailable_dopo_un_riposo_non_apre_l_ereditato(archivio):
    """L'altra faccia: spento, poi `unavailable`, poi acceso. L'episodio nasce
    all'accensione, non all'`unavailable` -- che non e' «acceso», e' un buco.
    Mutazione ESEGUITA: nel rigioco non saltare gli stati «non lo so» --
    rossa (l'inizio diventa l'`unavailable`, e lo stato «unavailable»)."""
    _watched(archivio, "switch.pompa")
    for quando, da, a in ((-20, "on", "off"), (-10, "off", "unavailable"),
                          (-9, "unavailable", "on")):
        archivio.record(quando_ts=MEZZANOTTE + quando * 3600, source="entita",
                        subject="switch.pompa", da=da, a=a)
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    [voce] = cronaca(archivio)
    assert (voce["quando_ts"], voce["cosa"]) == (MEZZANOTTE - 9 * 3600, "on")


def test_una_riga_piu_vecchia_della_finestra_non_si_eredita(archivio):
    """La finestra e' quella del grezzo, `READING_RETENTION_S` contata
    dall'inizio del giorno: una riga piu' vecchia esiste solo se la potatura
    non e' ancora girata, e la cronaca non deve dipendere da quello."""
    from hiris.app.mind.store import READING_RETENTION_S

    _watched(archivio, "climate.studio")
    archivio.record(quando_ts=MEZZANOTTE - READING_RETENTION_S - 3600, source="entita",
                    subject="climate.studio", da="off", a="heat")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 0


def test_un_soggetto_fuori_dallo_scope_non_rientra_dalla_riga_ereditata(archivio):
    """Chi e' fuori dallo scope di adesso non ha piu' righe scritte: ereditato,
    resterebbe aperto per sempre (il dispositivo fantasma dall'11/09). Le sue
    righe DENTRO il giorno restano storia del giorno."""
    archivio.record(quando_ts=MEZZANOTTE - 20 * 3600, source="entita",
                    subject="device_tracker.vecchio", da="home", a="not_home")
    archivio.decide_scope("person.marta", inside=False, reason="prova", author="observer")
    archivio.record(quando_ts=MEZZANOTTE - 20 * 3600, source="entita",
                    subject="person.marta", da="home", a="not_home")
    archivio.record(quando_ts=ts(9), source="entita", subject="light.fuori",
                    da="off", a="on")
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    assert [v["chi"] for v in cronaca(archivio)] == ["light.fuori"]


def test_rifare_la_cronaca_legge_il_grezzo_di_prima_UNA_volta(archivio):
    """A-39 del registro: `rebuild_chronicle` chiedeva `last_before` due volte,
    una per costruire gli episodi e una per sapere quali soggetti hanno
    ancora grezzo prima del giorno. Ora la stessa lettura serve a tutti e
    due."""
    from hiris.app.mind.facts import rebuild_chronicle

    _giorno_ereditato(archivio)
    letture = []
    originale = archivio.last_before

    def contata(*args, **kwargs):
        letture.append(args)
        return originale(*args, **kwargs)

    archivio.last_before = contata
    assert rebuild_chronicle(store=archivio, day=G, timezone="Europe/Rome",
                             judgments=tv.REPO_JUDGMENTS, house=None)
    assert len(letture) == 1


def test_un_termostato_acceso_da_piu_della_vita_del_grezzo_resta_in_corso(archivio):
    """Acceso trenta giorni fa: la riga che l'ha acceso e' fuori dalla
    finestra del grezzo (`READING_RETENTION_S`), e dentro restano solo righe
    di attributo (`da == a`, scritte da `watcher` quando cambia un attributo
    voluto: sui termostati sono la maggior parte del grezzo). Il rigioco del
    Task 1.4 guardava solo i cambi di STATO, non ne trovava nessuno, e
    l'episodio in corso spariva dalla cronaca -- d'inverno, ogni termostato
    acceso da piu' di 22 giorni (revisione cloud, giro 3, 05/10/2026). La
    prima riga del soggetto nella finestra dice in che stato la finestra
    comincia: l'episodio c'e', e comincia li', che e' il primo istante noto."""
    from hiris.app.mind.store import READING_RETENTION_S

    _watched(archivio, "climate.camera")
    archivio.record(quando_ts=MEZZANOTTE - READING_RETENTION_S - 8 * 86400,
                    source="entita", subject="climate.camera", da="off", a="heat")
    for giorni in (10, 5, 1):
        archivio.record(quando_ts=MEZZANOTTE - giorni * 86400, source="entita",
                        subject="climate.camera", da="heat", a="heat",
                        attributes='{"hvac_action": "heating"}')

    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 1
    voce = archivio.report(G)["cronaca"][0]
    assert (voce["chi"], voce["quando_ts"]) == ("climate.camera", MEZZANOTTE - 10 * 86400)


# -- Task 1.4 degli attori, Passo 3: le assenze nella cronaca (D5 «raccolte») --
#
# Decisione del proprietario del 06/10/2026: un'entita' che smette di
# rispondere (`unavailable`, `unknown`, `none`, il vuoto) diventa una VOCE
# della cronaca, raggruppata come la dichiara Home Assistant -- una per
# integrazione quando l'istanza sparisce tutta insieme, una per entita'
# altrimenti -- e l'episodio in corso quando la fonte sparisce si chiude
# «interrotto»; al ritorno, se lo stato e' lo stesso, ne riparte uno nuovo.
# «Tutta insieme» e' diventato «nello stesso istante» dopo il rigioco dei
# giorni veri (vedi `facts._absences`).
#
# **Il grezzo di queste prove lo scrive l'osservatore**, da eventi nella forma
# in cui Home Assistant li manda (`_ha`): le righe di assenza sono quelle che
# `watcher.watch_reading` scrive davvero, non righe composte a mano.


def _iso(instant):
    from datetime import UTC, datetime
    return datetime.fromtimestamp(instant, UTC).isoformat()


def _ha(store, eid, old_state, new_state, instant, **attributes):
    """Un `state_changed` come Home Assistant lo manda: `old_state` e
    `new_state` interi, `last_changed` e `last_updated` mossi insieme (un cambio
    di STATO), gli attributi dell'entita' sullo stato nuovo. L'osservatore lo
    scrive nel grezzo, o la prova si ferma qui."""
    old = None if old_state is None else {"entity_id": eid, "state": old_state,
                                          "attributes": dict(attributes)}
    new = {"entity_id": eid, "state": new_state, "attributes": dict(attributes),
           "last_changed": _iso(instant), "last_updated": _iso(instant)}
    assert Watcher(store).watch_reading(
        {"entity_id": eid, "old_state": old, "new_state": new})


def _entries(store, day=None):
    return [(v["chi"], v["genere"], v["cosa"], v["quando_ts"], v["fine_ts"])
            for v in cronaca(store, day)]


#: L'istanza dell'irrigazione: quattro entita' guardate, come sulla casa
#: (misurato il 05/10: 77 buchi brevi di un'integrazione intera, 16 entita'
#: insieme). Il raggruppamento si chiede alla casa: `config_entry_id` nel
#: registro delle entita'.
_IRRIGATION = ("switch.zona_1", "switch.zona_2", "valve.zona_1", "binary_sensor.pioggia")
#: Il riposo di ciascuna, nella parola di Home Assistant: una valvola e'
#: `closed`, non `off`.
_RESTING = {"switch.zona_1": "off", "switch.zona_2": "off", "valve.zona_1": "closed",
            "binary_sensor.pioggia": "off"}


def _irrigation_house(*others):
    return _house(entities=[(eid, {"config_entry_id": "e_irr"}) for eid in _IRRIGATION]
                  + [(eid, {"config_entry_id": "e_altra"}) for eid in others],
                  states=[(eid, _RESTING.get(eid, "off")) for eid in (*_IRRIGATION, *others)],
                  entries=[{"entry_id": "e_irr", "domain": "rainbird", "title": "Giardino",
                            "state": "loaded", "source": "user", "disabled_by": None},
                           {"entry_id": "e_altra", "domain": "hue", "title": "Luci",
                            "state": "loaded", "source": "user", "disabled_by": None}])


def test_l_assenza_di_una_fonte_sola_e_la_sua_voce_e_interrompe_l_episodio(archivio):
    """Accesa alle 8, `unavailable` alle 10, di nuovo accesa alle 10:05,
    spenta alle 12. Tre voci, nell'ordine in cui si chiudono: l'accensione
    delle 8 interrotta alle 10, l'assenza dalle 10 alle 10:05 (il genere delle
    condizioni di sistema, lo stato che Home Assistant ha scritto), e
    un'accensione NUOVA dalle 10:05 alle 12. Fino alla regola 3
    l'`unavailable` si saltava e restava una voce sola, 8 -> 12, come se in
    mezzo niente fosse.

    Mutazione ESEGUITA: rimettere il salto delle assenze in cima al ciclo
    del giorno -- rossa (una voce sola, 8 -> 12)."""
    _watched(archivio, "switch.pompa")
    _ha(archivio, "switch.pompa", "off", "on", ts(8), friendly_name="Pompa")
    _ha(archivio, "switch.pompa", "on", "unavailable", ts(10), friendly_name="Pompa")
    _ha(archivio, "switch.pompa", "unavailable", "on", ts(10, 5), friendly_name="Pompa")
    _ha(archivio, "switch.pompa", "on", "off", ts(12), friendly_name="Pompa")
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome") == 3
    assert _entries(archivio) == [
        ("switch.pompa", "funzionamento", "on", ts(8), ts(10)),
        ("switch.pompa", tv.SYSTEM_GENRE, "unavailable", ts(10), ts(10, 5)),
        ("switch.pompa", "funzionamento", "on", ts(10, 5), ts(12))]
    interrupted, absence, restarted = cronaca(archivio)
    assert interrupted["interrotto"] is True
    assert absence["nome"] == "Pompa" and "interrotto" not in absence
    assert "interrotto" not in restarted


def test_la_luce_rimasta_unavailable_tre_giorni_risulta_assente_non_accesa(archivio):
    """Il caso del proprietario: accesa la sera, poi `unknown` e `unavailable`,
    e cosi' per tre giorni. Nel giorno di mezzo la cronaca dice «assente da
    quella sera, ancora in corso» -- non «accesa». Il giorno del ritorno, la
    stessa assenza si chiude e un'accensione nuova comincia al ritorno."""
    yesterday = "2026-08-23"
    two_evenings_ago = MEZZANOTTE - 86400 - 4 * 3600
    _watched(archivio, "light.lampadario")
    _ha(archivio, "light.lampadario", "off", "on", two_evenings_ago - 1800)
    _ha(archivio, "light.lampadario", "on", "unknown", two_evenings_ago)
    _ha(archivio, "light.lampadario", "unknown", "unavailable", two_evenings_ago + 1)
    _ha(archivio, "light.lampadario", "unavailable", "on", ts(16))
    _ha(archivio, "light.lampadario", "on", "off", ts(18))
    aggregate_day(store=archivio, day=yesterday, timezone="Europe/Rome")
    assert _entries(archivio, yesterday) == [
        ("light.lampadario", tv.SYSTEM_GENRE, "unknown", two_evenings_ago, None)]
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome")
    assert _entries(archivio) == [
        ("light.lampadario", tv.SYSTEM_GENRE, "unknown", two_evenings_ago, ts(16)),
        ("light.lampadario", "funzionamento", "on", ts(16), ts(18))]


def test_un_integrazione_che_sparisce_tutta_insieme_e_UNA_voce(archivio):
    """Le quattro entita' dell'irrigazione vanno `unavailable` insieme alle 10
    e tornano alle 10:05: una voce sola, per l'ISTANZA (`integrazione:` piu' il
    suo `config_entry_id`, lo stesso soggetto con cui l'osservatore scrive
    un'istanza in errore), che dice di quale integrazione e quali entita'
    erano assenti, ciascuna col suo intervallo. Una luce di un'altra istanza
    assente da sola resta la sua voce. L'accensione della zona 1 si
    interrompe come per una fonte sola.

    Mutazione ESEGUITA: togliere il raggruppamento per istanza -- rossa (le
    quattro voci delle entita' al posto di quella dell'istanza)."""
    house = _irrigation_house("light.portico")
    _watched(archivio, *_IRRIGATION, "light.portico")
    _ha(archivio, "switch.zona_1", "off", "on", ts(9))
    for i, eid in enumerate(_IRRIGATION):
        _ha(archivio, eid, "on" if eid == "switch.zona_1" else _RESTING[eid], "unavailable",
            ts(10) + i / 100)
    for i, eid in enumerate(_IRRIGATION):
        _ha(archivio, eid, "unavailable", _RESTING[eid], ts(10, 5) + i / 100)
    _ha(archivio, "light.portico", "off", "unavailable", ts(11))
    _ha(archivio, "light.portico", "unavailable", "off", ts(11, 10))
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome", house=house)
    assert _entries(archivio) == [
        ("switch.zona_1", "funzionamento", "on", ts(9), ts(10)),
        ("integrazione:e_irr", tv.SYSTEM_GENRE, "unavailable", ts(10), ts(10, 5) + 0.03),
        ("light.portico", tv.SYSTEM_GENRE, "unavailable", ts(11), ts(11, 10))]
    instance = cronaca(archivio)[1]
    assert instance["assenti"] == [
        {"chi": eid, "quando_ts": ts(10) + i / 100, "fine_ts": ts(10, 5) + i / 100}
        for i, eid in enumerate(_IRRIGATION)]
    assert instance["dominio"] == "rainbird"


def test_due_entita_della_stessa_istanza_assenti_insieme_sono_la_voce_dell_istanza(archivio):
    """«Insieme» e non «tutte» (misurato sulla casa: i buchi dell'irrigazione
    sono 16 entita' su 20 guardate, un sensore di durata per dispositivo resta
    vivo). Due entita' su quattro della stessa istanza assenti nello stesso
    istante sono la voce dell'istanza, con le due che mancavano.

    Prima stesura: «tutte», e questa prova chiedeva due voci di entita'. Il
    rigioco dei giorni veri l'ha smentita (nessuna voce d'istanza, un giorno da
    10 a 91 voci)."""
    house = _irrigation_house()
    _watched(archivio, *_IRRIGATION)
    for eid in _IRRIGATION:
        _ha(archivio, eid, None, _RESTING[eid], ts(1))
    for eid in _IRRIGATION[:2]:
        _ha(archivio, eid, _RESTING[eid], "unavailable", ts(10))
        _ha(archivio, eid, "unavailable", _RESTING[eid], ts(10, 5))
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome", house=house)
    [entry] = cronaca(archivio)
    assert entry["chi"] == "integrazione:e_irr"
    assert [a["chi"] for a in entry["assenti"]] == list(_IRRIGATION[:2])


def test_due_entita_della_stessa_istanza_assenti_in_momenti_diversi_restano_due_voci(archivio):
    """«Insieme» vuol dire nello stesso istante: due assenze della stessa
    istanza che non si toccano sono due fatti, e restano le voci delle due
    entita'. Una terza che le tocca entrambe le riunisce (la catena).

    Mutazione ESEGUITA: raccogliere per istanza senza guardare il tempo --
    rossa (una voce d'istanza dalle 10 alle 12:05)."""
    house = _irrigation_house()
    _watched(archivio, *_IRRIGATION)
    _ha(archivio, "switch.zona_1", "off", "unavailable", ts(10))
    _ha(archivio, "switch.zona_1", "unavailable", "off", ts(10, 5))
    _ha(archivio, "switch.zona_2", "off", "unavailable", ts(12))
    _ha(archivio, "switch.zona_2", "unavailable", "off", ts(12, 5))
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome", house=house)
    assert [(v["chi"], v["quando_ts"], v["fine_ts"]) for v in cronaca(archivio)] == [
        ("switch.zona_1", ts(10), ts(10, 5)), ("switch.zona_2", ts(12), ts(12, 5))]
    _ha(archivio, "valve.zona_1", "closed", "unavailable", ts(10, 1))
    _ha(archivio, "valve.zona_1", "unavailable", "closed", ts(12, 1))
    aggregate_day(store=archivio, day=G, timezone="Europe/Rome", house=house)
    [entry] = cronaca(archivio)
    assert (entry["chi"], entry["quando_ts"], entry["fine_ts"]) == (
        "integrazione:e_irr", ts(10), ts(12, 5))
    assert [a["chi"] for a in entry["assenti"]] == [
        "switch.zona_1", "valve.zona_1", "switch.zona_2"]


def test_un_assenza_aperta_a_mezzanotte_di_una_fonte_finita_non_entra_nel_giorno(archivio):
    """La regola della fonte finita (Passo 1) vale anche per un'assenza: un
    interruttore andato `unavailable` ieri e poi spento dal proprietario con la
    sua istanza non resta «assente, in corso» per i ventidue giorni del grezzo.
    La sua ultima riga e' di ieri: oggi non c'e' niente.

    Nata verde: con la regola 3 lo stesso esito veniva dall'episodio
    ereditato chiuso dalla fonte. Mutazione ESEGUITA perche' discrimini la
    regola 4: la fonte finita chiesta solo per gli episodi, non per le
    assenze -- rossa (una voce: l'assenza, «in corso»)."""
    _watched(archivio, "switch.pompa")
    _ha(archivio, "switch.pompa", "off", "on", MEZZANOTTE - 20 * 3600)
    _ha(archivio, "switch.pompa", "on", "unavailable", MEZZANOTTE - 10 * 3600)
    assert aggregate_day(store=archivio, day=G, timezone="Europe/Rome",
                         house=_house_with_entry_switched_off("switch.pompa")) == 0
