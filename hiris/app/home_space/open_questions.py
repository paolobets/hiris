"""Le domande aperte sui tipi: cio' che aspetta una decisione del proprietario.

Il censore dei tipi (`scripts/censore_tipi.py`, un attrezzo) confronta cio' che
Home Assistant pubblica con cio' che il vocabolario rivendica, e non decide:
obbliga a decidere. Quando il giudizio non e' ovvio e non e' nostro, la voce
resta **aperta e nominata**, con la domanda gia' formulata per chi deve
rispondere. Quelle voci stanno QUI, nel prodotto, perche' il prodotto le
mostra: la pagina dei giudizi (`api/handlers_mind.py`) le elenca accanto ai
tipi a cui chiedono una risposta.

Il resto del censore -- il confronto, le eccezioni motivate, la forma
dell'istantaneo -- non ha lettori nel prodotto e sta fra gli attrezzi
(`scripts/`).

Spec: `docs/design/2026-09-07-l-anagrafe-dei-tipi.md` §5.
"""
from __future__ import annotations

from enum import Enum


class Subject(Enum):
    """Le materie su cui il censore gira.

    Il valore e' la parola italiana con cui la spec la nomina: e' cio' che una
    persona legge nel messaggio di una prova rossa, e tradurla due volte fra il
    codice e la prosa e' il modo in cui due cose diverse tornano a chiamarsi
    con una parola sola.
    """

    DOMAIN = "domini"
    DEVICE_CLASS = "device_class per dominio"
    STATE = "stati per tipo"
    STATE_CLASS = "valori di state_class"
    CAPABILITY_BIT = "bit di capacita' per dominio"
    SWITCHABLE = "domini accendibili"



def state_key(domain: str, device_class: str | None, state: str) -> str:
    """Il nome con cui il censore chiama uno stato. Un tipo con classe si
    nomina per intero: `binary_sensor.door=on` non e' `binary_sensor=on`."""
    if device_class:
        return f"{domain}.{device_class}={state}"
    return f"{domain}={state}"


def class_key(domain: str, device_class: str) -> str:
    return f"{domain}.{device_class}"


# --------------------------------------------------------------------------
# LE DOMANDE APERTE: cio' che il censore nomina e NON tocca a noi decidere
# --------------------------------------------------------------------------
#
# **Questa non e' la lista di cio' che si e' scelto di ignorare.** E' la lista
# di cio' che il censore ha trovato e che richiede una decisione del
# proprietario -- ognuna con la domanda gia' formulata in modo che si possa
# rispondere in una riga. Sta in git, datata, e una prova verifica che ogni
# voce ne porti una: una domanda aperta senza domanda scritta non e' una voce
# aperta, e' una voce dimenticata.
#
# Misurato l'08/09/2026 sulla casa vera, HA `2026.9.1`.

class OpenQuestion:
    """Una decisione che aspetta il proprietario, e la domanda per prenderla."""

    __slots__ = ("keys", "question", "subject")

    def __init__(self, subject: Subject, question: str, keys) -> None:
        if not question or not question.strip():
            raise ValueError(
                "una voce lasciata aperta senza la domanda scritta non e' una "
                "voce aperta: e' una voce dimenticata")
        if not keys:
            raise ValueError(
                "una domanda aperta senza soggetti non nomina niente: il "
                "censore obbliga a decidere SU QUALCOSA")
        self.subject = subject
        self.question = question
        self.keys = frozenset(keys)


OPEN_QUESTIONS: tuple[OpenQuestion, ...] = (
    # -- gli stati -----------------------------------------------------------
    #
    # **Cinque domande su sei sono state chiuse dal proprietario l'08/09/2026**
    # -- i sei modi di `water_heater`, lo `stopped` di `cover` e `valve`, il
    # `lawn_mower` trattato come l'aspirapolvice, i quattro domini lasciati
    # fuori, e `remote`/`siren` dichiarati accendibili. Le risposte non stanno
    # qui: stanno dove valgono, cioe' nel vocabolario dei tipi e fra le
    # eccezioni motivate qui sopra. **Questo elenco e' cio' che resta aperto,
    # non un verbale di cio' che e' stato deciso**: una domanda che ha avuto
    # risposta e resta scritta qui e' una domanda che qualcuno riporra'.
    OpenQuestion(
        Subject.STATE,
        "Una serratura `jammed` (inceppata): il proprietario ha deciso l'08/09/2026 "
        "che **e' un GUASTO** -- «e' inceppata, non sta lavorando» -- e quindi non "
        "va ne' fra i riposi ne' fra i funzionamenti di `lock`, che sono gli unici "
        "due posti che il vocabolario ha oggi. **La decisione c'e', il posto dove "
        "scriverla no**: «guasto» in questo prodotto e' un GENERE "
        "(`mind/facts.py::GENRES`), e il genere si decide per SOGGETTO -- "
        "`genre_for(soggetto, classe)` lo stato non lo riceve nemmeno, e un "
        "soggetto ha un genere solo per tutta la giornata (`open_episodes` e' "
        "indicizzato per soggetto: una serratura che si inceppa a episodio di "
        "sicurezza aperto non potrebbe cambiare genere senza chiuderne uno e "
        "aprirne un altro). Farlo entrare vuol dire un genere che dipende dallo "
        "stato, ed e' un lavoro suo -- non una riga. Finche' non si fa, `jammed` "
        "resta un funzionamento di fatto: apre un episodio di «sicurezza» che si "
        "chiude quando la serratura torna a posto. **Serve una fetta per il "
        "genere che dipende dallo stato, o si accetta che un guasto della "
        "serratura si racconti come un fatto di sicurezza?**",
        {state_key("lock", None, "jammed")}),

    # Nata dalla correzione R3a (revisione del tratto v3.23.0..HEAD,
    # 08/09/2026): questi quattro stati stavano in `EXCEPTIONS` con una
    # ragione ("SONO il riposo") che il vocabolario smentisce -- `disarmed`
    # e' dichiarato esplicitamente NON-riposo (`type_vocabulary.py`, commento
    # sopra `alarm_control_panel`). Nessuna ragione vera prende il suo posto,
    # perche' non c'e' ancora un giudizio: la domanda e' aperta, non chiusa
    # per errore.
    OpenQuestion(
        Subject.STATE,
        "Quattro stati di `alarm_control_panel` diversi da `triggered` e dai "
        "cinque `armed_*` (che sono riposo): `disarmed`, `arming`, "
        "`disarming`, `pending`. `disarmed` puo' durare giorni -- il "
        "vocabolario lo dichiara gia' NON-riposo (`_is_on(\"disarmed\") is "
        "True`, misurato), ma non gli ha ancora dato un genere: e' "
        "FUNZIONAMENTO, come `lock.unlocked` (\"e' il fatto che il genere "
        "sicurezza esiste per osservare\")? `arming`/`disarming`/`pending` "
        "sono transitori di pochi secondi, la stessa forma di "
        "`lock.locking`/`unlocking` -- vanno trattati allo stesso modo? Chi "
        "risponde decide se un impianto lasciato disarmato per ore apre un "
        "episodio di sicurezza o resta silenzioso.",
        {state_key("alarm_control_panel", None, state) for state in
         ("disarmed", "arming", "disarming", "pending")}),

    # Nata dalla correzione R3b (revisione del tratto v3.23.0..HEAD,
    # 08/09/2026): `update=off` stava eccettuato insieme a `calendar`/`sensor`
    # citando una decisione (il campo `notable` di `type_vocabulary`) che non nomina
    # `update`. Il proprietario non ha mai deciso se un aggiornamento
    # disponibile riguardi il «buono stato» della casa.
    OpenQuestion(
        Subject.STATE,
        "Un aggiornamento disponibile (`update=on`, 53 entita' di questa casa "
        "misurate l'08/09/2026) tocca il «buono stato» della casa, e nessuno lo "
        "ha mai deciso: oggi non e' notevole ne' osservato, semplicemente "
        "perche' `update` non e' nell'elenco dei domini-evento. Si dichiara "
        "notevole il giorno in cui un aggiornamento diventa disponibile, o "
        "resta un fatto che si va a chiedere con `search`? `update=off` (nessun "
        "aggiornamento) resta aperto con lui: e' la stessa domanda vista al "
        "contrario, non una seconda domanda.",
        {state_key("update", None, "off")}),

    # -- le classi del dispositivo ------------------------------------------
    OpenQuestion(
        Subject.DEVICE_CLASS,
        "Trentuno classi di `sensor` che Home Assistant pubblica e che nessuna "
        "lista di HIRIS ha mai nominato. La domanda della spec §7 e' una sola, "
        "e finora non era mai stata POSTA: quali di queste servono a una delle "
        "sei gambe dell'obiettivo (`chi c'e'`, comfort, dispersione, energia, "
        "buono stato, sicurezza)? I candidati evidenti sono `moisture`, "
        "`precipitation`, `radon`, `signal_strength`, `volume`, `water`; il "
        "resto probabilmente no.",
        {class_key("sensor", device_class) for device_class in (
            "absolute_humidity", "apparent_power", "aqi", "area",
            "blood_glucose_concentration", "conductivity", "date", "distance",
            "energy_distance", "energy_storage", "frequency", "irradiance",
            "moisture", "monetary", "ph", "pm4", "power_factor", "precipitation",
            "precipitation_intensity", "radon", "reactive_energy", "reactive_power",
            "signal_strength", "speed", "temperature_delta", "volume",
            "volume_flow_rate", "volume_storage", "weight", "wind_direction",
            "wind_speed")}),
    OpenQuestion(
        Subject.DEVICE_CLASS,
        "Cinquantasette classi di `number` -- e sono, una per una, le stesse "
        "stringhe delle classi di `sensor`. La domanda si risponde una volta "
        "sola: `number` deve avere gambe e significati PROPRI, oppure il "
        "significato di `number.temperature` e' quello di `sensor.temperature` "
        "gia' scritto, e un `number` resta cio' che si IMPOSTA e non cio' che "
        "si misura?",
        {class_key("number", device_class) for device_class in (
            "absolute_humidity", "apparent_power", "aqi", "area",
            "atmospheric_pressure", "battery", "blood_glucose_concentration",
            "carbon_dioxide", "carbon_monoxide", "conductivity", "current",
            "data_rate", "data_size", "distance", "energy", "energy_distance",
            "energy_storage", "frequency", "gas", "humidity", "illuminance",
            "irradiance", "moisture", "monetary", "nitrogen_dioxide",
            "nitrogen_monoxide", "nitrous_oxide", "ozone", "ph", "pm1", "pm10",
            "pm25", "pm4", "power", "power_factor", "precipitation",
            "precipitation_intensity", "pressure", "radon", "reactive_energy",
            "reactive_power", "signal_strength", "sound_pressure", "speed",
            "sulphur_dioxide", "temperature", "temperature_delta",
            "volatile_organic_compounds", "volatile_organic_compounds_parts",
            "voltage", "volume", "volume_flow_rate", "volume_storage", "water",
            "weight", "wind_direction", "wind_speed")}),
    OpenQuestion(
        Subject.DEVICE_CLASS,
        "Ventuno classi di sei domini che HIRIS chiama tutti con un nome solo: "
        "una tapparella si chiama «tapparella» anche quando e' un cancello "
        "(`cover.gate`) o una tenda da sole (`cover.awning`), e un evento si "
        "chiama «evento» anche quando e' un campanello (`event.doorbell`). "
        "Vanno nominate una per una -- diventando tipologie con un nome "
        "proprio -- o basta il nome del dominio?",
        {class_key("cover", device_class) for device_class in (
            "awning", "blind", "curtain", "damper", "door", "garage", "gate",
            "shade", "shutter", "window")}
        | {class_key("event", device_class) for device_class in
           ("button", "doorbell", "motion")}
        | {class_key("humidifier", device_class) for device_class in
           ("dehumidifier", "humidifier")}
        | {class_key("infrared", device_class) for device_class in
           ("emitter", "receiver")}
        | {class_key("media_player", device_class) for device_class in
           ("projector", "receiver")}
        | {class_key("valve", "gas"), class_key("button", "update")}),
)
