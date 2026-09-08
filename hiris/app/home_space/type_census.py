"""Il censore: cio' che Home Assistant pubblica e nessuno ha classificato **ha
un nome**.

    pubblicato - rivendicato dal vocabolario = da decidere

Il censore **non decide: obbliga a decidere.** Ogni voce che emerge si chiude
in uno dei due modi, e non ce n'e' un terzo -- o entra nel vocabolario col suo
giudizio, o resta fuori con un'eccezione **motivata e scritta** (`EXCEPTIONS`).
E quando il giudizio non e' ovvio e non e' nostro, la voce resta **aperta e
nominata**, con la domanda gia' formulata per chi deve rispondere
(`OPEN_QUESTIONS`): e' il limite onesto del mandato -- accorgersene si', da
soli; aggiornare il giudizio no, perche' una lista che SEMBRA verificata e non
lo e' e' peggio di una lista dichiaratamente vecchia.

**Sei materie.** Le cinque del piano -- domini, `device_class` per dominio,
stati per tipo, valori di `state_class`, bit di capacita' per dominio -- piu'
i **domini accendibili**, che la spec §4 impone di sorvegliare («il derivato
non sostituisce il giudizio: lo SORVEGLIA») e senza la quale le otto eccezioni
che quella stessa spec richiede non avrebbero nessun soggetto.

**Costa zero chiamate nuove.** Entrambe le fonti sono gia' in memoria: le 801
chiavi di `frontend/get_translations` stanno in `StateTranslations`, il
registro dei servizi si invalida gia' da se' su
`service_registered`/`service_removed`. Un'integrazione installata oggi entra
nel confronto senza una riga di rete in piu'.

**Il vincolo che decide la forma: la suite gira SENZA la casa.** Quindi il
censore non legge Home Assistant: legge un **istantaneo del pubblicato,
versionato nel repository e datato** (`tests/data/pubblicato-dalla-casa.json`,
prodotto da `scripts/istantaneo_pubblicato.py`). Una **seconda** prova, che
gira solo quando la casa risponde, verifica che l'istantaneo non sia scaduto.
**Due prove, due fallimenti diversi**, perche' sono due difetti diversi:

- *«il vocabolario non copre cio' che Home Assistant pubblica»* -- e allora
  qualcuno deve decidere;
- *«l'istantaneo non e' piu' quello di questa casa»* -- e allora va rifatto.

**Il confronto gira anche all'incontrario.** Cio' che noi rivendichiamo e Home
Assistant non pubblica e' l'altro difetto, e non e' teorico: e' cosi' che si e'
scoperto che `_CLASS_MEANING["damper"]` era irraggiungibile -- `damper` e' una
`CoverDeviceClass`, non una di `binary_sensor`, e quella riga non poteva
rispondere a nessuna entita' di nessuna casa.

**Dove sta il limite di questo censore, dichiarato invece che scoperto fra sei
mesi.** Il «rivendicato» degli stati include due tabelle CIECHE AL DOMINIO
(`topology._STATE_TRANSLATION` e `briefing._ACTIVE_STATES`): per loro `open` e'
rivendicato su `lock` esattamente come su `cover`, che e' il difetto che la
fetta 5 esiste per chiudere. Finche' ci sono, il censore le conta come
rivendicazioni -- e il giorno in cui spariranno il censore parlera' molto di
piu'. **E' voluto**: un censore che le ignorasse oggi direbbe che il prodotto
non sa niente di stati che invece rende da mesi.

Spec: `docs/design/2026-09-07-l-anagrafe-dei-tipi.md` §5.
"""
from __future__ import annotations

from enum import Enum
from types import MappingProxyType

from . import briefing, ha_vocabulary, historian, topology, type_vocabulary


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


SUBJECTS = tuple(Subject)


# --------------------------------------------------------------------------
# LA FORMA DELL'ISTANTANEO
# --------------------------------------------------------------------------
#
# Le chiavi sono ITALIANE come quelle degli altri contratti-dato di questo
# prodotto (`lette`, `risorse`, `letto`, `valore`): l'istantaneo lo legge anche
# una persona, che e' il motivo per cui e' versionato in chiaro invece che
# rigenerato al volo. Gli identificatori del codice restano inglesi.

SNAPSHOT_READ_ON = "letto_il"
SNAPSHOT_HA_VERSION = "versione_ha"
SNAPSHOT_LANGUAGE = "lingua"

#: Materia -> la chiave dell'istantaneo che la porta. Scritta una volta: una
#: chiave cercata con una stringa sbagliata risponderebbe «niente da
#: censurare» invece di sbagliare, ed e' il modo in cui una materia intera
#: smetterebbe di essere sorvegliata in silenzio.
SNAPSHOT_KEYS = MappingProxyType({
    Subject.DOMAIN: "domini",
    Subject.DEVICE_CLASS: "classi_per_dominio",
    Subject.STATE: "stati_per_tipo",
    Subject.STATE_CLASS: "valori_di_state_class",
    Subject.CAPABILITY_BIT: "bit_per_dominio",
    Subject.SWITCHABLE: "domini_accendibili",
})

#: Il trattino basso con cui Home Assistant scrive «questo vale per il dominio,
#: senza classe» nelle chiavi delle traduzioni. Nell'istantaneo resta quello --
#: JSON non ha una chiave `None` -- e si scioglie qui, in un posto solo.
NO_DEVICE_CLASS = "_"


def state_key(domain: str, device_class: str | None, state: str) -> str:
    """Il nome con cui il censore chiama uno stato. Un tipo con classe si
    nomina per intero: `binary_sensor.door=on` non e' `binary_sensor=on`."""
    if device_class:
        return f"{domain}.{device_class}={state}"
    return f"{domain}={state}"


def class_key(domain: str, device_class: str) -> str:
    return f"{domain}.{device_class}"


def bit_key(domain: str, bit: int) -> str:
    return f"{domain}={bit}"


# --------------------------------------------------------------------------
# CHI RIVENDICA, OGGI
# --------------------------------------------------------------------------
#
# **«Rivendicato» non vuol dire «giudicato bene»**: vuol dire che QUALCUNO nel
# prodotto quel soggetto l'ha guardato. E' il metro giusto per un censore --
# la domanda e' «e' mai stata posta?», non «e' stata posta bene?».
#
# Le liste qui sotto sono quelle che il piano (fetta 6) fara' sparire una per
# una dentro il vocabolario dei tipi. Finche' esistono, il censore le legge
# dove sono: leggerne meta' direbbe che il prodotto non sa cose che sa.
#
# **Si leggono col loro nome privato, e non e' una svista.** Dare a ciascuna
# una vista pubblica solo perche' il censore la guarda vorrebbe dire allargare
# l'API di due moduli per una lista che due fette piu' avanti non esistera'
# piu' -- e lasciarsi dietro una vista orfana e' esattamente il modo in cui in
# questo prodotto nasce il codice morto. Il censore e' un lettore dichiarato:
# quando la lista trasloca, trasloca anche questa riga.


def claimed_domains() -> frozenset[str]:
    """I domini che qualcuno ha guardato: il vocabolario dei tipi, i nomi
    leggibili del nucleo, i domini-evento."""
    return (type_vocabulary.declared_domains()
            | frozenset(briefing._DOMAIN_NAMES)
            | frozenset(briefing._EVENT_DOMAINS))


def claimed_device_classes() -> frozenset[str]:
    """Le coppie (dominio, classe) che qualcuno ha nominato, come chiavi."""
    claimed = {class_key(domain, device_class)
               for domain, device_class in ha_vocabulary.DEVICE_CLASS_MEANING}
    claimed |= {class_key(domain, device_class)
                for domain, device_class in type_vocabulary.declared_pairs()}
    claimed |= {class_key("binary_sensor", device_class)
                for device_class in topology._CLASS_MEANING}
    claimed |= {class_key("binary_sensor", device_class)
                for device_class in briefing._EVENT_CLASSES}
    return frozenset(claimed)


def claimed_states(domain: str, device_class: str | None) -> frozenset[str]:
    """Gli stati che, per questo tipo, qualcuno ha gia' guardato.

    Quattro provenienze diverse, e la differenza fra loro conta:

    - i **riposi** del vocabolario dei tipi -- l'unico giudizio per tipo;
    - **`unavailable`/`unknown`** e le due forme dell'assenza, che attraversano
      ogni tipo e per questo non stanno su nessuna riga;
    - gli **stati attivi** del nucleo e le **traduzioni** di `topology`, che
      sono CIECHE AL DOMINIO (vedi il docstring in testa a questo modulo);
    - i **modi** di un termostato, che valgono per `climate` e per nessun altro.
    """
    claimed = set(type_vocabulary.resting_states_of(domain, device_class))
    claimed |= set(type_vocabulary.unknown_states())
    claimed |= set(type_vocabulary.ABSENT_STATE_FORMS.value)
    claimed |= set(briefing._ACTIVE_STATES)
    claimed |= set(topology._STATE_TRANSLATION)
    if domain == "climate":
        claimed |= set(topology._READABLE_HVAC_MODE)
    return frozenset(claimed)


def claimed_state_classes() -> frozenset[str]:
    return (frozenset(ha_vocabulary.STATE_CLASS_MEANING)
            | frozenset(historian.STATE_CLASSES_WITH_STATISTICS))


def claimed_capability_bits(domain: str) -> frozenset[int]:
    table = type_vocabulary.capability_names(domain)
    return frozenset(table or ())


def claimed_switchable_domains() -> frozenset[str]:
    return type_vocabulary.operable_domains()


# --------------------------------------------------------------------------
# IL CONFRONTO
# --------------------------------------------------------------------------


def _as_set(value) -> set:
    return set(value) if isinstance(value, (list, tuple, set, frozenset)) else set()


def _as_map(value) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def published_but_unclaimed(snapshot) -> dict[Subject, tuple[str, ...]]:
    """Materia -> cio' che l'istantaneo porta e nessuno ha classificato.

    E' il censore vero e proprio. Ordinato, perche' un elenco che cambia ordine
    a ogni giro fa divergere due messaggi d'errore che dicono la stessa cosa.
    """
    snapshot = _as_map(snapshot)
    found: dict[Subject, set[str]] = {subject: set() for subject in SUBJECTS}

    for domain in _as_set(snapshot.get(SNAPSHOT_KEYS[Subject.DOMAIN])):
        if domain not in claimed_domains():
            found[Subject.DOMAIN].add(domain)

    claimed_classes = claimed_device_classes()
    for domain, classes in _as_map(snapshot.get(SNAPSHOT_KEYS[Subject.DEVICE_CLASS])).items():
        for device_class in _as_set(classes):
            if class_key(domain, device_class) not in claimed_classes:
                found[Subject.DEVICE_CLASS].add(class_key(domain, device_class))

    for domain, per_class in _as_map(snapshot.get(SNAPSHOT_KEYS[Subject.STATE])).items():
        for written_class, states in _as_map(per_class).items():
            device_class = None if written_class == NO_DEVICE_CLASS else written_class
            claimed = claimed_states(domain, device_class)
            for state in _as_set(states):
                if state not in claimed:
                    found[Subject.STATE].add(state_key(domain, device_class, state))

    for value in _as_set(snapshot.get(SNAPSHOT_KEYS[Subject.STATE_CLASS])):
        if value not in claimed_state_classes():
            found[Subject.STATE_CLASS].add(value)

    for domain, bits in _as_map(snapshot.get(SNAPSHOT_KEYS[Subject.CAPABILITY_BIT])).items():
        claimed = claimed_capability_bits(domain)
        for bit in _as_set(bits):
            if bit not in claimed:
                found[Subject.CAPABILITY_BIT].add(bit_key(domain, bit))

    for domain in _as_set(snapshot.get(SNAPSHOT_KEYS[Subject.SWITCHABLE])):
        if domain not in claimed_switchable_domains():
            found[Subject.SWITCHABLE].add(domain)

    return {subject: tuple(sorted(names)) for subject, names in found.items()}


def claimed_but_unpublished(snapshot) -> dict[Subject, tuple[str, ...]]:
    """Il confronto all'incontrario: cio' che rivendichiamo e questa casa non
    pubblica.

    **Solo dove il rovescio significa qualcosa.** Le classi del dispositivo lo
    fanno: le nostre tabelle dichiarano di venire dall'enumerazione di Home
    Assistant, quindi una classe che HA non pubblica e' una riga che nessuna
    entita' potra' mai raggiungere -- ed e' cosi' che si e' trovato `damper`.
    I bit no: il registro dei servizi dichiara solo i bit su cui FILTRA, e
    pretendere che li dichiari tutti farebbe gridare al buco su ogni tabella
    corretta. Uno stato nemmeno: `_STATE_TRANSLATION` e' cieca al dominio per
    costruzione, e il suo rovescio direbbe soltanto quello.

    **E i domini accendibili**, dove il rovescio e' meta' del mandato: la spec
    §4 dice che la derivazione sbaglia in ENTRAMBI i versi, e `vacuum` -- che
    HIRIS dichiara accendibile e Home Assistant comanda con `start`/`stop` --
    e' il caso che lo dimostra. Senza questo verso, l'eccezione scritta per
    `vacuum` non avrebbe nessun soggetto: sarebbe una riga che difende una
    scelta che nessuno vede piu' fare, cioe' la forma esatta del difetto
    `damper`.

    Un dominio che questa casa non ha caricato non conta: non e' sbagliato,
    e' assente. Il rovescio guarda **dentro cio' che l'istantaneo porta**.
    """
    snapshot = _as_map(snapshot)
    published = _as_map(snapshot.get(SNAPSHOT_KEYS[Subject.DEVICE_CLASS]))
    orphans = set()
    for key in claimed_device_classes():
        domain, _, device_class = key.partition(".")
        if domain not in published:
            continue
        if device_class not in _as_set(published.get(domain)):
            orphans.add(key)
    domains = _as_set(snapshot.get(SNAPSHOT_KEYS[Subject.DOMAIN]))
    derived = _as_set(snapshot.get(SNAPSHOT_KEYS[Subject.SWITCHABLE]))
    ours_only = {domain for domain in claimed_switchable_domains()
                 if domain in domains and domain not in derived}
    found = {subject: () for subject in SUBJECTS}
    found[Subject.DEVICE_CLASS] = tuple(sorted(orphans))
    found[Subject.SWITCHABLE] = tuple(sorted(ours_only))
    return found


# --------------------------------------------------------------------------
# LE ECCEZIONI: cio' che resta fuori, e PERCHE'
# --------------------------------------------------------------------------
#
# **Un'eccezione senza motivo scritto non passa** -- e non e' un buon proposito:
# `tests/test_type_census.py` legge questa tabella e boccia una ragione vuota.
# Ed e' vietato anche il rovescio: un'eccezione che non corrisponde piu' a
# niente di pubblicato e' una riga che dichiara di difendere una scelta che
# nessuno fa piu', ed e' l'esatta forma del difetto `damper`.

EXCEPTIONS: dict[tuple[Subject, str], str] = {
    # -- i domini accendibili: la derivazione SORVEGLIA il giudizio, non lo
    #    sostituisce (spec §4). Sedici derivati contro dieci nostri, e la
    #    differenza sta tutta qui sotto.
    (Subject.SWITCHABLE, "automation"): (
        "`on` significa «abilitata», non «accesa»: un'automazione attiva e' il "
        "riposo di quella casa, non un funzionamento in corso. Misurato -- con "
        "`automation`, `script` e `input_boolean` dentro, 18 entita' di questa "
        "casa erano riposo travestito da eccezione, ed e' la ragione gia' "
        "scritta in `briefing._EVENT_DOMAINS`."),
    (Subject.SWITCHABLE, "script"): (
        "Come `automation`: `on` dice che lo script e' abilitato -- e per la "
        "manciata di secondi in cui gira, che sta girando. Dichiararlo "
        "accendibile aprirebbe un episodio di funzionamento su ogni script "
        "abilitato della casa."),
    (Subject.SWITCHABLE, "input_boolean"): (
        "Come `automation`: e' un interruttore che l'utente crea per farci "
        "sopra delle condizioni, non un apparecchio che si accende."),
    (Subject.SWITCHABLE, "camera"): (
        "Gli stati che Home Assistant pubblica per `camera` sono `idle`, "
        "`recording` e `streaming` -- misurato: nessun `on`, nessun `off` da "
        "cui dedurre un riposo. `camera.turn_on` comanda la registrazione "
        "dell'integrazione, non un apparecchio di casa."),
    (Subject.SWITCHABLE, "homeassistant"): (
        "Non e' un dominio di ENTITA': e' il dominio dei servizi di sistema "
        "(`homeassistant.turn_on` e' il servizio universale). Misurato -- non "
        "compare ne' fra i domini che le traduzioni pubblicano ne' fra quelli "
        "vivi. Non c'e' nessun tipo da dichiarare accendibile."),
    (Subject.SWITCHABLE, "vacuum"): (
        "L'eccezione al contrario, ed e' NOSTRA: l'aspirapolvere si accende e "
        "si spegne eccome, ma Home Assistant lo comanda con "
        "`start`/`stop`/`return_to_base`, quindi la derivazione non lo vede. "
        "E' il caso che dimostra che il derivato non puo' sostituire il "
        "giudizio: sbaglia in ENTRAMBI i versi (spec §4)."),

    # -- i valori di `state_class`
    (Subject.STATE_CLASS, "measurement_angle"): (
        "Escluso di proposito e gia' documentato in due punti "
        "(`ha_vocabulary.STATE_CLASS_MEANING`, `historian`): zero entita' di "
        "questa casa lo usano, e la regola di quel vocabolario e' «si importa "
        "cio' che la casa usa davvero», non «tutto cio' che esiste». Il giorno "
        "in cui un'entita' lo porta, il censore lo rinomina."),

    # -- i bit di capacita'
    (Subject.CAPABILITY_BIT, "button=2"): (
        "Non esiste nessun `ButtonEntityFeature`, su nessuno dei due tag della "
        "finestra supportata (verificato `__init__.py` e `const.py`): non c'e' "
        "un nome da importare, e inventarlo sarebbe affermare una capacita' "
        "che il fornitore non dichiara. Il bit arriva da `reolink.ptz_move`, "
        "un servizio di integrazione che BERSAGLIA `button`."),

    # -- gli stati gia' giudicati altrove, con la ragione scritta li'
    (Subject.STATE, "media_player=buffering"): (
        "Gia' giudicato, e la ragione e' scritta nel vocabolario dei tipi: "
        "«sta per riprodurre, non e' un riposo». Resta fuori dai riposi di "
        "proposito -- metterlo dentro chiuderebbe l'episodio di un film che "
        "sta per ripartire."),
}

def _same_reason(subject: Subject, keys, reason: str) -> dict[tuple[Subject, str], str]:
    """Una ragione sola per piu' voci -- ma **ogni voce resta nominata**.

    Quindici stati del meteo escono dalla stessa decisione, e ripeterne la
    frase quindici volte non la renderebbe piu' vera. Cio' che NON si fa e'
    scusare il DOMINIO invece delle sue voci: un `weather` con uno stato nuovo
    domani tornerebbe muto, e il censore esiste per non lasciarlo passare.
    """
    return {(subject, key): reason for key in keys}


#: Gli stati che qualcuno ha gia' guardato e lasciato fuori DI PROPOSITO, con
#: la ragione scritta dov'e' stata presa la decisione. Un dominio che nessuno
#: ha mai guardato non sta qui: sta fra le domande aperte, ed e' esattamente la
#: differenza fra un'esclusione e una dimenticanza.
EXCEPTIONS.update(_same_reason(
    Subject.STATE,
    (state_key("alarm_control_panel", None, state) for state in
     ("armed", "arming", "disarmed", "disarming", "pending")),
    "Solo `triggered` e' notevole, e gli altri stati sono la routine "
    "quotidiana: ci si arma e ci si disarma piu' volte al giorno, come si "
    "accende e si spegne una luce. Non sono un'eccezione rispetto al riposo, "
    "SONO il riposo -- deciso e scritto sopra `briefing._ACTIVE_STATES`."))

EXCEPTIONS.update(_same_reason(
    Subject.STATE,
    (state_key("weather", None, state) for state in
     ("clear-night", "cloudy", "exceptional", "fog", "hail", "lightning",
      "lightning-rainy", "partlycloudy", "pouring", "rainy", "snowy",
      "snowy-rainy", "sunny", "windy", "windy-variant")),
    "`weather` e' una MISURA, non un evento: `rainy` e' com'e' il tempo, non "
    "qualcosa che qualcuno ha acceso, e non apre ne' chiude niente. Deciso e "
    "scritto sopra `briefing._EVENT_DOMAINS`, insieme a `sensor`, `number` e "
    "`sun`."))

EXCEPTIONS.update(_same_reason(
    Subject.STATE,
    (state_key("sun", None, state) for state in ("above_horizon", "below_horizon")),
    "Stessa ragione di `weather`, e la stessa riga di commento la dichiara: "
    "dove sta il sole e' una misura dell'universo, non un fatto della casa."))


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
    OpenQuestion(
        Subject.STATE,
        "Un boiler in `eco` (o `gas`, `electric`, `heat_pump`, `high_demand`, "
        "`performance`) sta FUNZIONANDO -- e l'episodio resta aperto finche' "
        "non va a `off` -- oppure quello e' il suo modo di stare fermo, e "
        "l'episodio va chiuso? `water_heater` e' dichiarato accendibile e il "
        "suo unico riposo e' `off`: se questi sei sono riposi vanno aggiunti, "
        "se sono funzionamento non serve toccare niente ma la domanda va "
        "chiusa. Oggi non morde (nessun boiler in questa casa), e mordera' il "
        "giorno in cui ne arriva uno.",
        {state_key("water_heater", None, state) for state in
         ("eco", "electric", "gas", "heat_pump", "high_demand", "performance")}),
    OpenQuestion(
        Subject.STATE,
        "Una tapparella (o una valvola) ferma a meta' corsa -- stato "
        "`stopped` -- e' a riposo o in funzionamento? Sono due domini "
        "dichiarati accendibili il cui unico riposo e' `closed`: oggi una "
        "tapparella lasciata a meta' tiene aperto per sempre l'episodio "
        "cominciato quando si e' mossa.",
        {state_key("cover", None, "stopped"), state_key("valve", None, "stopped")}),
    OpenQuestion(
        Subject.STATE,
        "Una serratura `jammed` (inceppata), `locking` o `unlocking` va "
        "annunciata come si annuncia `unlocked`? `lock` e' gia' un dominio di "
        "cui il nucleo annuncia lo stato attivo, e questi tre non sono ne' "
        "attivi ne' riposi ne' ignoti: oggi passano senza che nessuno li "
        "guardi. `jammed` in particolare e' un guasto.",
        {state_key("lock", None, state) for state in ("jammed", "locking", "unlocking")}),
    OpenQuestion(
        Subject.STATE,
        "`lawn_mower` e' il gemello di `vacuum` -- taglia, torna alla base, si "
        "mette in pausa, va in errore -- ma non e' mai stato guardato da "
        "nessuna lista. Va trattato come l'aspirapolvere (accendibile, con "
        "`docked`/`returning`/`error` a riposo e `mowing` attivo), oppure "
        "resta fuori?",
        {state_key("lawn_mower", None, state) for state in
         ("docked", "error", "mowing", "returning")}),
    OpenQuestion(
        Subject.STATE,
        "Quattro domini che nessuna lista di questo prodotto ha mai guardato: "
        "`assist_satellite` (sta ascoltando, sta rispondendo), `camera` (sta "
        "registrando), `timer` (attivo), `group` (`ok`). Hanno stati che il "
        "nucleo deve annunciare o su cui HIRIS deve aprire un episodio, o "
        "restano fuori come `sensor` e `weather`?",
        {state_key("assist_satellite", None, state) for state in
         ("idle", "listening", "processing", "responding")}
        | {state_key("camera", None, state) for state in ("idle", "recording", "streaming")}
        | {state_key("timer", None, state) for state in ("active", "idle")}
        | {state_key("group", None, "ok")}),

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

    # -- i domini accendibili ------------------------------------------------
    OpenQuestion(
        Subject.SWITCHABLE,
        "`remote` e `siren` Home Assistant li dichiara accendibili "
        "(`turn_on`+`turn_off`) e pubblica per entrambi `on`/`off`; HIRIS li "
        "tratta gia' come domini-evento -- `on` si annuncia -- ma non come "
        "accendibili, quindi non apre nessun episodio su una sirena che suona "
        "o su un telecomando acceso. Vanno dichiarati accendibili con `off` a "
        "riposo, o l'esclusione va confermata? **La spec §4 li elenca fra le "
        "sette esclusioni motivate da «`on` significa abilitata», e per questi "
        "due quella frase non regge**: `_EVENT_DOMAINS` li contiene entrambi, "
        "cioe' il prodotto quel `on` lo annuncia gia' come un'accensione.",
        {"remote", "siren"}),
)


def _exception_keys() -> frozenset[tuple[Subject, str]]:
    return frozenset(EXCEPTIONS)


def _open_keys() -> frozenset[tuple[Subject, str]]:
    return frozenset((question.subject, key)
                     for question in OPEN_QUESTIONS for key in question.keys)


def state_domain_of(key: str) -> str:
    """Il dominio di una chiave di stato -- `water_heater=eco` -> `water_heater`."""
    return key.split("=")[0].split(".")[0]


def undecided(snapshot) -> dict[Subject, tuple[str, ...]]:
    """Cio' che il censore nomina e che **nessuno ha ancora chiuso**: ne' col
    proprio giudizio nel vocabolario, ne' con un'eccezione motivata, ne' con
    una domanda aperta e formulata.

    E' la vista su cui la prova fallisce. Un elenco vuoto non vuol dire «tutto
    deciso»: vuol dire che ogni voce ha almeno un nome e un posto.
    """
    return {subject: tuple(sorted(name for name in names if not is_closed(subject, name)))
            for subject, names in findings(snapshot).items()}


def findings(snapshot) -> dict[Subject, tuple[str, ...]]:
    """Tutto cio' che il censore nomina, nei due versi messi insieme.

    I due versi restano due FUNZIONI (sono due difetti diversi, e si leggono
    separati), ma per chi deve chiudere le voci sono un elenco solo: una voce
    o e' chiusa o non lo e', qualunque verso l'abbia trovata.
    """
    both = published_but_unclaimed(snapshot)
    for subject, names in claimed_but_unpublished(snapshot).items():
        if names:
            both[subject] = tuple(sorted(set(both.get(subject, ())) | set(names)))
    return both


def is_closed(subject: Subject, name: str) -> bool:
    """Se questa voce ha gia' un posto: un'eccezione motivata, una domanda
    aperta e formulata."""
    return (subject, name) in EXCEPTIONS or (subject, name) in _open_keys()


def report(snapshot) -> str:
    """Cio' che resta da decidere, in parole -- il testo che una prova rossa
    mette davanti a chi deve deciderlo.

    Un elenco di chiavi senza la materia che le porta non dice a nessuno cosa
    fare: il messaggio d'errore e' l'unica interfaccia che questo censore ha.
    """
    blocks = []
    for subject, names in undecided(snapshot).items():
        if names:
            blocks.append(f"{subject.value}: " + ", ".join(names))
    if not blocks:
        return "niente da decidere"
    return ("cio' che Home Assistant pubblica e nessuno ha classificato -- ogni "
            "voce va chiusa col suo giudizio nel vocabolario, con un'eccezione "
            "motivata, o con una domanda aperta e formulata:\n  "
            + "\n  ".join(blocks))
