"""Il censore: `pubblicato - rivendicato = da decidere`.

**Due prove sul censore, non una** (spec §10.3). Davanti a un istantaneo che
contiene qualcosa di ignoto lo nomina; davanti a uno coperto per intero tace.
Una prova che passa perche' non c'e' niente da trovare non dimostra di saper
trovare, ed e' il difetto n.1 delle prove di questo progetto: si asserisce il
FATTO invece della proprieta' che dovrebbe produrlo.

**La suite gira senza la casa**, quindi qui non si legge Home Assistant: si
legge l'istantaneo versionato (`tests/data/pubblicato-dalla-casa.json`). Che
quell'istantaneo sia ancora quello di questa casa lo dice un'altra prova, che
gira solo quando la casa risponde (`test_type_census_live.py`) -- **due
fallimenti diversi, perche' sono due difetti diversi**.
"""
import json
import pathlib

import pytest

from hiris.app.home_space import type_census
from hiris.app.home_space.type_census import (
    EXCEPTIONS,
    OPEN_QUESTIONS,
    SUBJECTS,
    OpenQuestion,
    Subject,
    findings,
    published_but_unclaimed,
    report,
    state_key,
    undecided,
)

ISTANTANEO = pathlib.Path(__file__).resolve().parent / "data" / "pubblicato-dalla-casa.json"


@pytest.fixture(scope="module")
def casa():
    """L'istantaneo vero, letto dalla casa del proprietario l'08/09/2026."""
    return json.loads(ISTANTANEO.read_text(encoding="utf-8"))


def _classi_rivendicate(*domini):
    """Le classi che il prodotto rivendica, per i domini chiesti."""
    per_dominio = {domain: [] for domain in domini}
    for key in sorted(type_census.claimed_device_classes()):
        domain, _, device_class = key.partition(".")
        if domain in per_dominio:
            per_dominio[domain].append(device_class)
    return per_dominio


def _coperto():
    """Un istantaneo che contiene SOLO cose che il prodotto rivendica gia'.

    Costruito dalle rivendicazioni stesse, non copiato a mano: una copia a
    mano invecchierebbe e il giorno in cui invecchia questa prova comincerebbe
    a fallire per il motivo sbagliato.
    """
    return {
        type_census.SNAPSHOT_READ_ON: "2026-09-08",
        type_census.SNAPSHOT_HA_VERSION: "2026.9.1",
        type_census.SNAPSHOT_LANGUAGE: "it",
        "domini": ["light", "switch"],
        # Le classi del dominio le pubblica TUTTE, altrimenti il confronto
        # all'incontrario -- che e' meta' del censore -- avrebbe ragione a
        # gridare: una classe che noi nominiamo e la casa non pubblica e' una
        # riga irraggiungibile, ed e' esattamente cio' che `damper` era.
        "classi_per_dominio": _classi_rivendicate("sensor", "binary_sensor"),
        "stati_per_tipo": {"light": {"_": ["on", "off"]},
                           "climate": {"_": ["heat", "off"]}},
        "valori_di_state_class": ["measurement", "total"],
        "bit_per_dominio": {"light": [4, 8, 32]},
        "domini_accendibili": ["light", "switch"],
    }


# ---------------------------------------------------------------------------
# SA TROVARE -- una materia alla volta
# ---------------------------------------------------------------------------

def test_il_censore_nomina_un_dominio_che_nessuno_ha_classificato():
    """Il caso del mandato: un dominio nuovo compare in casa e nessuna lista
    del prodotto lo ha mai guardato. Il censore lo NOMINA.

    Mutazione ESEGUITA: in `published_but_unclaimed`, saltare il ramo dei
    domini (`found[Subject.DOMAIN]` mai riempito) -- la prova arrossisce su
    `assert 'domotica_marziana' in ()`.
    """
    istantaneo = _coperto()
    istantaneo["domini"] = [*istantaneo["domini"], "domotica_marziana"]
    trovati = published_but_unclaimed(istantaneo)
    assert "domotica_marziana" in trovati[Subject.DOMAIN]
    assert "domotica_marziana" in report(istantaneo)


def test_davanti_a_un_istantaneo_coperto_per_intero_il_censore_tace():
    """Il rovescio, e senza di lui la prova sopra non varrebbe niente: un
    censore che nominasse tutto passerebbe anche quella.

    Mutazione ESEGUITA: in `claimed_capability_bits`, tornare sempre un
    insieme vuoto -- una fonte di rivendicazione si svuota in silenzio e la
    prova arrossisce nominando `light=4`, `light=8`, `light=32`.
    """
    trovati = published_but_unclaimed(_coperto())
    assert all(not names for names in trovati.values()), trovati
    assert report(_coperto()) == "niente da decidere"


@pytest.mark.parametrize("subject,chiave,ignoto", [
    (Subject.DOMAIN, "domini", "domotica_marziana"),
    (Subject.STATE_CLASS, "valori_di_state_class", "misura_marziana"),
    (Subject.SWITCHABLE, "domini_accendibili", "domotica_marziana"),
], ids=["domini", "state_class", "accendibili"])
def test_ogni_materia_a_elenco_sa_trovare_il_suo_ignoto(subject, chiave, ignoto):
    """Le tre materie che sono un elenco piatto. Una materia che non sapesse
    trovare niente sarebbe una sorveglianza che non sorveglia -- e non lo
    direbbe: risponderebbe «tutto a posto».

    Mutazione ESEGUITA: in `published_but_unclaimed`, sostituire il ramo della
    materia con `pass` -- la prova di quella materia arrossisce, le altre due
    restano verdi (che e' il punto di averle separate).
    """
    istantaneo = _coperto()
    istantaneo[chiave] = [*istantaneo[chiave], ignoto]
    assert ignoto in published_but_unclaimed(istantaneo)[subject]


def test_la_materia_delle_classi_nomina_la_coppia_non_il_dominio():
    """Una classe ignota si nomina col suo dominio: `sensor.marziana`, non
    `marziana`. La stessa stringa su due domini diversi e' due fatti diversi
    -- `battery` e' una percentuale su `sensor` e «carica bassa» su
    `binary_sensor`.

    Mutazione ESEGUITA: in `class_key`, tornare `device_class` da solo -- la
    prova arrossisce su `assert 'sensor.marziana' in ('marziana',)`.
    """
    istantaneo = _coperto()
    istantaneo["classi_per_dominio"]["sensor"].append("marziana")
    trovate = published_but_unclaimed(istantaneo)[Subject.DEVICE_CLASS]
    # Le chiavi si scrivono a mano, non con `class_key`: un oracolo che passa
    # dalla stessa funzione che sta verificando non puo' vederla sbagliare.
    assert "sensor.marziana" in trovate
    assert "sensor.energy" not in trovate


def test_la_materia_degli_stati_nomina_il_tipo_e_lo_stato():
    """Uno stato ignoto si nomina col tipo che lo porta. E il tipo e' il TIPO:
    un dominio, o una coppia.

    Mutazione ESEGUITA: in `published_but_unclaimed`, sciogliere il `_` in una
    classe invece che in `None` (togliere il ramo `NO_DEVICE_CLASS`) -- lo
    stato del termostato viene cercato sotto una classe che non esiste e la
    prova arrossisce su `assert 'climate=marziano' in (...)`.
    """
    istantaneo = _coperto()
    istantaneo["stati_per_tipo"]["climate"]["_"] = ["heat", "off", "marziano"]
    istantaneo["stati_per_tipo"]["binary_sensor"] = {"door": ["on", "off", "socchiuso"]}
    trovati = published_but_unclaimed(istantaneo)[Subject.STATE]
    assert "climate=marziano" in trovati
    assert "binary_sensor.door=socchiuso" in trovati
    assert "climate=heat" not in trovati


def test_la_materia_dei_bit_nomina_il_bit_che_non_sappiamo_chiamare():
    """Un bit che il registro dei servizi dichiara e per cui non esiste un
    nome nella tabella del dominio.

    Mutazione ESEGUITA: in `claimed_capability_bits`, tornare un insieme di
    TUTTI i bit possibili invece della tabella -- la prova arrossisce su un
    elenco vuoto.
    """
    istantaneo = _coperto()
    istantaneo["bit_per_dominio"]["light"] = [4, 8, 32, 1024]
    trovati = published_but_unclaimed(istantaneo)[Subject.CAPABILITY_BIT]
    assert "light=1024" in trovati
    assert "light=4" not in trovati


def test_il_censore_gira_anche_all_incontrario():
    """Il verso che ha trovato `damper`: una classe che noi rivendichiamo e che
    Home Assistant non pubblica su quel dominio e' una riga irraggiungibile --
    nessuna entita' di nessuna casa potra' mai portarla.

    Il caso vero era `_CLASS_MEANING["damper"]` fra le classi di
    `binary_sensor`, mentre `damper` e' una `CoverDeviceClass`. Qui si
    riproduce togliendo `door` da cio' che l'istantaneo pubblica.

    Mutazione ESEGUITA: in `claimed_but_unpublished`, tornare sempre elenchi
    vuoti -- la prova arrossisce su `assert 'binary_sensor.door' in ()`.
    """
    istantaneo = _coperto()
    istantaneo["classi_per_dominio"]["binary_sensor"].remove("door")
    orfane = type_census.claimed_but_unpublished(istantaneo)[Subject.DEVICE_CLASS]
    assert "binary_sensor.door" in orfane


def test_il_rovescio_vale_anche_per_gli_accendibili():
    """Ed e' meta' del mandato: la spec §4 dice che la derivazione sbaglia in
    ENTRAMBI i versi, e `vacuum` -- che noi dichiariamo accendibile e Home
    Assistant comanda con `start`/`stop` -- e' il caso che lo dimostra. Senza
    questo verso l'eccezione scritta per `vacuum` non avrebbe nessun soggetto.

    Mutazione ESEGUITA: in `claimed_but_unpublished`, non riempire
    `found[Subject.SWITCHABLE]` -- la prova arrossisce, e con lei quella sulle
    eccezioni che non difendono piu' niente.
    """
    istantaneo = _coperto()
    istantaneo["domini"] = [*istantaneo["domini"], "vacuum"]
    orfani = type_census.claimed_but_unpublished(istantaneo)[Subject.SWITCHABLE]
    assert "vacuum" in orfani


def test_un_dominio_che_questa_casa_non_ha_non_e_un_difetto():
    """Il rovescio non deve gridare al buco su cio' che semplicemente non c'e':
    `vacuum` assente da una casa senza aspirapolvere e' un'assenza, non una
    rivendicazione sbagliata.

    Mutazione ESEGUITA: in `claimed_but_unpublished`, togliere
    `if domain in domains` -- la prova arrossisce perche' `vacuum` compare su
    una casa che non lo ha.
    """
    orfani = type_census.claimed_but_unpublished(_coperto())[Subject.SWITCHABLE]
    assert "vacuum" not in orfani


# ---------------------------------------------------------------------------
# L'ISTANTANEO DI QUESTA CASA -- e cio' che il censore ci ha trovato
# ---------------------------------------------------------------------------

def test_l_istantaneo_e_datato_e_dice_di_quale_casa_e(casa):
    """Un istantaneo che non sa di quando e' e di quale casa non si sa vecchio,
    ed e' la stessa disciplina che il vocabolario impone ai campi importati.

    Mutazione ESEGUITA: togliere la riga `letto_il` dall'istantaneo versionato
    -- la prova arrossisce su `KeyError: 'letto_il'`.
    """
    from datetime import date
    assert date.fromisoformat(casa[type_census.SNAPSHOT_READ_ON])
    assert casa[type_census.SNAPSHOT_HA_VERSION]
    assert casa[type_census.SNAPSHOT_LANGUAGE]


def test_i_bit_dell_istantaneo_sono_gia_scomposti(casa):
    """`cover: 3` e' `OPEN|CLOSE`, non un bit. Confrontare un valore combinato
    con una tabella di bit singoli non trova niente **e non fallisce**: dice
    «questo dominio non ha capacita' che conosciamo» su un dominio che le ha
    tutte. La scomposizione sta a monte, nell'istantaneo.

    Mutazione ESEGUITA: in `registry.single_bits`, tornare `{value}` -- il 3 di
    `cover` sopravvive alla rigenerazione e la prova arrossisce su
    `assert 3 in (1, 2, 4, ...)`.
    """
    for domain, bits in casa["bit_per_dominio"].items():
        for bit in bits:
            assert bit > 0 and bit & (bit - 1) == 0, (
                f"«{domain}» porta {bit}, che non e' una potenza di due: e' un "
                "valore combinato arrivato fino al confronto")


def test_l_istantaneo_di_questa_casa_non_lascia_niente_senza_un_posto(casa):
    """**La prova del mandato.** Cio' che Home Assistant pubblica e nessuno ha
    classificato ha un nome, e obbliga qualcuno a decidere: ogni voce e' chiusa
    col proprio giudizio nel vocabolario, con un'eccezione motivata, o con una
    domanda aperta e formulata per il proprietario.

    Un elenco vuoto qui NON vuol dire «tutto deciso»: vuol dire che ogni voce
    ha almeno un nome e un posto. Le 136 voci ancora aperte sono in
    `OPEN_QUESTIONS`, e sono nove domande.

    Mutazione ESEGUITA: togliere da `EXCEPTIONS` la voce
    `(Subject.CAPABILITY_BIT, "button=2")` -- la prova arrossisce e il
    messaggio nomina proprio quel bit.
    """
    resto = undecided(casa)
    assert all(not names for names in resto.values()), report(casa)


def test_il_censore_su_questa_casa_ha_trovato_davvero_qualcosa(casa):
    """L'oracolo delle prove qui sopra: se l'istantaneo non contenesse niente
    da censurare, «niente da decidere» non direbbe niente di nessuno.

    Sono 167 voci, in cinque materie su sei -- i domini sono l'unica materia
    coperta per intero, e lo e' perche' `_DOMAIN_NAMES` era gia' stata estesa
    a mano oltre le 45 piattaforme di Home Assistant.

    Mutazione ESEGUITA: svuotare `tests/data/pubblicato-dalla-casa.json` di
    `classi_per_dominio` -- la prova arrossisce su `assert 58 >= 100`.
    """
    tutte = findings(casa)
    assert len(tutte[Subject.DEVICE_CLASS]) >= 100
    assert len(tutte[Subject.STATE]) >= 40
    assert tutte[Subject.CAPABILITY_BIT]
    assert tutte[Subject.STATE_CLASS]
    assert tutte[Subject.SWITCHABLE]


def test_i_cinque_difetti_gia_misurati_sono_ancora_nominati(casa):
    """I cinque che la ricognizione aveva trovato girando il censore una volta
    sola. Nessuno e' stato silenziato: quattro sono ancora nominati (e aperti o
    eccettuati), il quinto -- `damper` -- e' stato chiuso cancellando la riga
    irraggiungibile, ed e' per questo che NON compare piu'.

    Mutazione ESEGUITA: in `published_but_unclaimed`, sostituire con `pass` il
    ramo degli stati -- i sei del boiler, i tre della serratura e i quattro del
    tosaerba smettono di essere nominati e la prova arrossisce su
    `assert 'water_heater=eco' in set()`.
    """
    stati = set(findings(casa)[Subject.STATE])
    assert state_key("water_heater", None, "eco") in stati
    assert state_key("lock", None, "jammed") in stati
    assert state_key("lawn_mower", None, "mowing") in stati
    # i cinque domini con bit e nessuna tabella: quattro hanno preso la loro
    # tabella (verificata alla fonte ai due tag), `button` ha la sua eccezione.
    from hiris.app.home_space.type_vocabulary import capability_tables
    tabelle = capability_tables()
    for domain in ("lock", "humidifier", "lawn_mower", "assist_satellite"):
        assert domain in tabelle, f"«{domain}» aveva bit e nessuna tabella"
    assert (Subject.CAPABILITY_BIT, "button=2") in EXCEPTIONS
    # `damper`: la riga irraggiungibile non c'e' piu', quindi il rovescio tace
    assert not type_census.claimed_but_unpublished(casa)[Subject.DEVICE_CLASS]


# ---------------------------------------------------------------------------
# LE ECCEZIONI E LE DOMANDE: nessuna passa senza la sua ragione
# ---------------------------------------------------------------------------

def test_ogni_eccezione_porta_la_sua_ragione_scritta():
    """«Un'eccezione senza motivo scritto non passa» -- e non e' un buon
    proposito: e' questa riga.

    Mutazione ESEGUITA: mettere `""` come ragione dell'eccezione di `vacuum` --
    la prova arrossisce nominandola.
    """
    mute = [key for key, reason in EXCEPTIONS.items()
            if not reason or len(reason.strip()) < 40]
    assert not mute, f"eccezioni senza una ragione scritta: {mute}"


def test_nessuna_eccezione_difende_una_voce_che_non_esiste_piu(casa):
    """Il rovescio della regola, ed e' la lezione di `damper`: una riga che
    dichiara di difendere una scelta che nessuno fa piu' SEMBRA verificata e
    non lo e'.

    Mutazione ESEGUITA: aggiungere a `EXCEPTIONS` una voce
    `(Subject.DOMAIN, "domotica_marziana")` con una ragione lunga -- la prova
    arrossisce su quella chiave.
    """
    vive = {(subject, name) for subject, names in findings(casa).items() for name in names}
    morte = sorted(f"{subject.value}: {name}" for subject, name in EXCEPTIONS
                   if (subject, name) not in vive)
    assert not morte, (
        "eccezioni che non corrispondono a niente che questa casa pubblichi: "
        + ", ".join(morte))


def test_una_voce_aperta_senza_la_sua_domanda_non_si_puo_nemmeno_costruire():
    """La struttura lo impedisce, non un controllo a valle: una prova dice che
    oggi nessuno l'ha fatto, il costruttore dice che non si puo' fare.

    Mutazione ESEGUITA: togliere il `raise` da `OpenQuestion.__init__` -- la
    prova arrossisce su `DID NOT RAISE`.
    """
    with pytest.raises(ValueError):
        OpenQuestion(Subject.DOMAIN, "   ", {"pippo"})
    with pytest.raises(ValueError):
        OpenQuestion(Subject.DOMAIN, "una domanda vera", set())


def test_ogni_domanda_aperta_e_rispondibile_in_una_riga():
    """Sono decisioni del proprietario, non compiti per chi scrive il codice:
    devono poter essere lette e risposte senza aprire il repository.

    Mutazione ESEGUITA: sostituire il testo di una domanda con «da decidere» --
    la prova arrossisce perche' non contiene nessun punto interrogativo.
    """
    for question in OPEN_QUESTIONS:
        assert "?" in question.question, question.question
        assert len(question.question) > 80, question.question
        assert question.subject in SUBJECTS


def test_nessuna_domanda_aperta_riguarda_una_voce_gia_chiusa():
    """Una voce non puo' essere insieme un'eccezione motivata e una domanda
    aperta: sarebbero due risposte diverse alla stessa domanda, ed e' esattamente
    «due cose dette con una parola sola» applicato al censore.

    Mutazione ESEGUITA: aggiungere a `EXCEPTIONS` la chiave
    `(Subject.STATE, "water_heater=eco")` -- la prova arrossisce.
    """
    aperte = {(question.subject, key)
              for question in OPEN_QUESTIONS for key in question.keys}
    doppie = sorted(f"{subject.value}: {name}" for subject, name in aperte & set(EXCEPTIONS))
    assert not doppie, f"voci insieme eccettuate e aperte: {doppie}"


def test_nessuna_domanda_aperta_su_una_voce_che_questa_casa_non_pubblica(casa):
    """Stessa disciplina delle eccezioni: una domanda su un soggetto che non
    esiste piu' e' rumore che seppellisce le domande vere.

    Mutazione ESEGUITA: aggiungere `state_key("water_heater", None, "marziano")`
    ai soggetti della prima domanda -- la prova arrossisce su quella chiave.
    """
    vive = {(subject, name) for subject, names in findings(casa).items() for name in names}
    orfane = sorted(f"{question.subject.value}: {key}"
                    for question in OPEN_QUESTIONS for key in question.keys
                    if (question.subject, key) not in vive)
    assert not orfane, f"domande su voci che questa casa non pubblica piu': {orfane}"
