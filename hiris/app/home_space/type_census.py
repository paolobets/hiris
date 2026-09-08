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
scoperto che la riga `damper` era irraggiungibile -- `damper` e' una
`CoverDeviceClass`, non una di `binary_sensor`, e quella riga non poteva
rispondere a nessuna entita' di nessuna casa.

**Cos'e' successo il giorno in cui quelle tabelle sono sparite (08/09/2026,
fetta 5).** La versione precedente di questo modulo dichiarava un limite: il
«rivendicato» degli stati includeva due tabelle CIECHE AL DOMINIO
(`topology._STATE_TRANSLATION` e `briefing._ACTIVE_STATES`), per cui `open` era
rivendicato su `lock` esattamente come su `cover` -- e prevedeva che «il giorno
in cui spariranno il censore parlera' molto di piu'». **E' successo, ed e' stato
misurato**: 35 stati e 12 classi del dispositivo che nessuno aveva mai
guardato, `alarm_control_panel=triggered` compreso. Nessuna e' stata silenziata:
o e' entrata nel vocabolario col suo giudizio (`working_states`), o porta
un'eccezione motivata qui sotto.

**Il limite che RESTA**, e va detto invece che sottinteso: `briefing._ACTIVE_STATES`
e' ancora cieco al dominio, e rivendica `on`/`open`/`unlocked`/`playing`/`cleaning`
per qualunque tipo. Si vede in una sola eccezione -- quella di `group`, dove
tre voci sono eccettuate proprio perche' quella rivendicazione non vale come
giudizio.

Spec: `docs/design/2026-09-07-l-anagrafe-dei-tipi.md` §5.
"""
from __future__ import annotations

from enum import Enum
from types import MappingProxyType

from . import briefing, ha_vocabulary, historian, type_vocabulary


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
                for device_class in briefing._EVENT_CLASSES}
    return frozenset(claimed)


def claimed_states(domain: str, device_class: str | None) -> frozenset[str]:
    """Gli stati che, per questo tipo, qualcuno ha gia' guardato.

    Tre provenienze diverse, e la differenza fra loro conta:

    - i **riposi** e i **funzionamenti** del vocabolario dei tipi -- le due
      meta' dell'unico giudizio per tipo;
    - **`unavailable`/`unknown`** e le due forme dell'assenza, che attraversano
      ogni tipo e per questo non stanno su nessuna riga;
    - gli **stati attivi** del nucleo, che sono CIECHI AL DOMINIO.

    **Erano quattro fino all'08/09/2026**, e la quarta era la piu' larga:
    `topology._STATE_TRANSLATION` (cieca al dominio) e `_READABLE_HVAC_MODE`
    rivendicavano 24 stati per OGNI tipo, solo perche' qualcuno li traduceva.
    Quelle tabelle non esistono piu' (spec §6, fetta 5): le parole le dice Home
    Assistant. **Con loro e' caduta la rivendicazione, ed e' un guadagno, non
    una perdita** -- «qualcuno lo traduce» non era mai stato «qualcuno lo ha
    giudicato», e infatti la loro sparizione ha fatto emergere 35 stati che
    nessuno aveva mai guardato, `alarm_control_panel=triggered` compreso. Ogni
    voce e' stata chiusa: col giudizio nel vocabolario, o con un'eccezione
    motivata qui sotto.
    """
    claimed = set(type_vocabulary.resting_states_of(domain, device_class))
    claimed |= set(type_vocabulary.working_states_of(domain, device_class))
    claimed |= set(type_vocabulary.unknown_states())
    claimed |= set(type_vocabulary.ABSENT_STATE_FORMS.value)
    claimed |= set(briefing._ACTIVE_STATES)
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
    Uno stato nemmeno, e la ragione e' cambiata l'08/09/2026: fino a quel
    giorno il rovescio avrebbe soltanto ripetuto che `_STATE_TRANSLATION` era
    cieca al dominio; adesso i riposi e i funzionamenti sono giudizi NOSTRI su
    tipi che possono benissimo non essere in questa casa (nessun boiler, nessun
    tosaerba), e gridare al buco su ognuno di loro sarebbe chiedere di
    cancellare un giudizio corretto perche' il dispositivo non e' ancora
    arrivato.

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
    (Subject.SWITCHABLE, "lawn_mower"): (
        "Identica a `vacuum`, e non e' una coincidenza: il proprietario ha "
        "deciso l'08/09/2026 che il tosaerba si tratta come l'aspirapolvere -- "
        "stessa forma, `docked` a riposo. Home Assistant lo comanda allo stesso "
        "modo (`start_mowing`/`pause`/`dock`, non `turn_on`/`turn_off`), quindi "
        "la derivazione non lo vede, ed e' la SECONDA voce del verso opposto: "
        "il derivato sbaglia in entrambi i sensi, e sbaglia per la stessa "
        "ragione tutte le volte -- un apparecchio che si accende e si spegne "
        "ma che HA comanda con verbi propri."),

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

    # `media_player=buffering` STAVA qui, ed era gia' allora la voce piu'
    # debole dell'elenco: la sua ragione diceva «gia' giudicato, e la ragione e'
    # scritta nel vocabolario dei tipi» -- cioe' era un'eccezione che rimandava
    # a un giudizio, non un'esclusione. Dall'08/09/2026 quel giudizio ha un
    # campo dove stare (`type_vocabulary`, `working_states`: «sta per
    # riprodurre, non e' un riposo»), quindi la voce e' rivendicata e non
    # eccettuata. E' il movimento che il censore esiste per rendere possibile:
    # una voce esce dalle eccezioni ed entra nel vocabolario il giorno in cui
    # c'e' un posto per lei.
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

# -- le classi del dispositivo lasciate fuori DI PROPOSITO, con la ragione
#    scritta dov'e' stata presa la decisione.
#
# Emergono dall'08/09/2026, con la sparizione di `topology._CLASS_MEANING`
# (spec §6): quella tabella le rivendicava tutte e ventotto, e la
# rivendicazione era «qualcuno le traduce» -- non «qualcuno ha deciso se
# servono». Adesso le parole le dice Home Assistant, e la domanda vera (spec
# §7: serve a una delle sei gambe dell'obiettivo?) resta scoperta per le
# dodici che nessuna gamba raccoglie. **La risposta era gia' scritta nel
# prodotto**, sopra `briefing._EVENT_CLASSES`, ed e' quella: sono transitori e
# manutenzione, si vanno a chiedere e non si annunciano.

EXCEPTIONS.update(_same_reason(
    Subject.DEVICE_CLASS,
    (class_key("binary_sensor", device_class) for device_class in
     ("light", "moving", "plug", "power", "running", "sound", "vibration")),
    "Transitorio: dice com'e' un istante, non che sia successo qualcosa da "
    "osservare o da annunciare. Deciso e scritto sopra `briefing._EVENT_CLASSES` "
    "(«restano fuori i transitori»), e nessuna delle sei gambe dell'obiettivo lo "
    "raccoglie: `chi c'e'` ha gia' `motion`/`occupancy`/`presence`, che sono la "
    "stessa domanda posta bene."))

EXCEPTIONS.update(_same_reason(
    Subject.DEVICE_CLASS,
    (class_key("binary_sensor", device_class) for device_class in
     ("battery", "battery_charging", "connectivity", "update")),
    "Manutenzione: e' la gamba «buono stato», che pero' HIRIS la osserva dove "
    "il dato e' un NUMERO (`sensor.battery`, gia' nel vocabolario) e non dove e' "
    "un si'/no. Un `binary_sensor.battery` dice «carica bassa» e basta: non c'e' "
    "una soglia da confrontare ne' una tendenza da guardare, e annunciarlo "
    "riempirebbe il nucleo di righe che non cambiano per settimane. Deciso e "
    "scritto sopra `briefing._EVENT_CLASSES` («e la manutenzione»)."))

EXCEPTIONS[(Subject.DEVICE_CLASS, class_key("binary_sensor", "lock"))] = (
    "E' il DOPPIONE di un tipo che il vocabolario gia' porta: il dominio `lock` "
    "ha la sua riga, con la gamba «sicurezza» e i suoi riposi. Un "
    "`binary_sensor.lock` e' la stessa serratura vista da un'integrazione che "
    "non implementa il dominio, e dargli una riga propria vorrebbe dire due "
    "case per lo stesso soggetto. Se un giorno questa casa ne avesse uno, la "
    "risposta giusta e' collegarlo a quella riga, non aprirne una seconda.")


# -- gli stati emersi con la sparizione di `_STATE_TRANSLATION` (08/09/2026)
#
# Trentacinque voci, e nessuna e' nuova per Home Assistant: erano tutte
# rivendicate da una tabella che le traduceva senza guardare il dominio. Sotto
# ci sono quelle la cui decisione era GIA' PRESA e scritta altrove nel
# prodotto; le altre sono entrate nel vocabolario col loro giudizio
# (`type_vocabulary`, campo `working_states`).

EXCEPTIONS.update(_same_reason(
    Subject.STATE,
    (state_key("automation", None, "off"), state_key("script", None, "off"),
     state_key("input_boolean", None, "off"), state_key("schedule", None, "off")),
    "`off` qui significa «disabilitata», non «spenta»: e' il rovescio esatto "
    "dell'`on` per cui questi stessi domini sono esclusi dagli accendibili "
    "(vedi le loro eccezioni qui sopra). Non c'e' nessun apparecchio che si "
    "ferma, quindi non c'e' nessun episodio da chiudere. `schedule` non era "
    "nell'elenco degli accendibili -- Home Assistant non gli da' "
    "`turn_on`/`turn_off` -- ma e' la stessa famiglia e la stessa ragione."))

EXCEPTIONS.update(_same_reason(
    Subject.STATE,
    # I nomi si scrivono UNO PER UNO e dentro `state_key`, non come tupla di
    # domini: una tupla di domini letterale e' un vocabolario parallelo, e la
    # prova «un tipo ha una casa sola» la vede e ha ragione a vederla. Qui il
    # soggetto e' lo STATO di quel tipo, non il tipo.
    (state_key("calendar", None, "off"), state_key("sensor", None, "off"),
     state_key("update", None, "off")),
    "Sono i tre domini che HIRIS non giudica per stato: un `sensor` MISURA, un "
    "`calendar` dice se c'e' un evento in corso, un `update` se c'e' un "
    "aggiornamento. Nessuno dei tre e' una cosa che si accende, e per tutti e "
    "tre la decisione e' gia' scritta sopra `briefing._EVENT_DOMAINS`. **E "
    "`update=off` e' il caso che dimostra perche' la tabella cieca al dominio "
    "andava cancellata**: la rendeva «spento», mentre Home Assistant per quel "
    "dominio dice «Aggiornato»."))

EXCEPTIONS.update(_same_reason(
    Subject.STATE,
    (state_key("person", None, "home"), state_key("person", None, "not_home"),
     state_key("device_tracker", None, "home"),
     state_key("device_tracker", None, "not_home")),
    "Gia' giudicati, e il giudizio e' il genere «presenza» di "
    "`mind/facts.py::aggregate_day`: `home` E' il riposo (chiude l'episodio) e "
    "l'oggetto e' l'ASSENZA -- «fuori casa dalle 8:10 alle 17:34» -- non il "
    "rientro. Non stanno fra i riposi del vocabolario perche' quel ramo non "
    "passa da `_is_on`: confronta `home` da se', ed e' l'unico genere che lo fa. "
    "Il giorno in cui i due rami si unificassero, queste quattro voci "
    "diventerebbero due righe di vocabolario."))


# I quattro domini che il proprietario ha lasciato FUORI l'08/09/2026, quinta
# delle nove domande del censore: nessuno dei quattro e' una cosa che si accende
# nel senso che serve all'osservatore. **L'eccezione e' per VOCE, come tutte le
# altre**: un dominio scusato per intero resterebbe muto il giorno in cui Home
# Assistant gli aggiunge uno stato nuovo -- ed e' anche il motivo per cui i
# quattro nomi non stanno in un elenco loro, che sarebbe un vocabolario dei
# tipi parallelo a quello vero.

EXCEPTIONS.update(_same_reason(
    Subject.STATE,
    (state_key("assist_satellite", None, state)
     for state in ("idle", "listening", "processing", "responding")),
    "FUORI, deciso dal proprietario l'08/09/2026: un satellite che ascolta o "
    "risponde non e' una cosa che si accende nel senso che serve "
    "all'osservatore. E' la conversazione in corso con HIRIS stesso, dura "
    "secondi, e aprirci sopra un episodio riempirebbe la giornata di oggetti "
    "che raccontano l'assistente invece della casa."))

EXCEPTIONS.update(_same_reason(
    Subject.STATE,
    (state_key("camera", None, state)
     for state in ("idle", "recording", "streaming")),
    "FUORI, deciso dal proprietario l'08/09/2026, e coerente con l'esclusione "
    "gia' scritta fra gli accendibili: `recording`/`streaming` dicono cosa fa "
    "l'INTEGRAZIONE con quel flusso, non cosa fa un apparecchio di casa -- e "
    "non c'e' nessun `off` da cui dedurre un riposo."))

EXCEPTIONS.update(_same_reason(
    Subject.STATE,
    (state_key("timer", None, state) for state in ("active", "idle", "paused")),
    "FUORI, deciso dal proprietario l'08/09/2026: un timer attivo e' un conto "
    "alla rovescia che qualcuno ha impostato, non una cosa della casa che sta "
    "funzionando. Il fatto interessante e' cosa succede quando SCADE, e quello "
    "e' un evento dell'automazione che lo ascolta -- non uno stato di questo."))

EXCEPTIONS.update(_same_reason(
    Subject.STATE,
    (state_key("group", None, state) for state in
     ("closed", "home", "locked", "not_home", "off", "ok", "problem")),
    "FUORI, deciso dal proprietario l'08/09/2026: un gruppo non e' una cosa, e' "
    "un modo di guardarne molte -- il suo stato e' quello dei membri, gia' "
    "osservati uno per uno, e osservarlo di nuovo qui conterebbe due volte lo "
    "stesso fatto. **Sette dei dieci stati, non tutti**: `on`, `open` e "
    "`unlocked` restano rivendicati da `briefing._ACTIVE_STATES`, che e' CIECO "
    "AL DOMINIO -- l'ultimo residuo della stessa cecita' che questa fetta ha "
    "tolto alle traduzioni. Non si possono eccettuare: una prova chiama "
    "(giustamente) permesso-che-non-difende-niente un'eccezione su una voce "
    "che il censore non nomina. Restano dentro per una rivendicazione che non "
    "e' un giudizio, ed e' scritto qui perche' la fetta che togliera' quella "
    "cecita' sappia dove tornare."))


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
        "`genre_for(soggetto, gamba)` lo stato non lo riceve nemmeno, e un "
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
