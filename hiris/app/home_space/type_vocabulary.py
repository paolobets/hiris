"""Il vocabolario dei tipi: una casa sola per cio' che HIRIS giudica di un tipo
di entita' di Home Assistant.

**Il soggetto e' il TIPO, non il dominio.** Un tipo e' un dominio (`"light"`)
oppure una coppia dominio + classe del dispositivo (`("sensor", "energy")`).
Meta' di cio' che HIRIS sapeva dei tipi era indicizzato per coppia, non per
dominio: un vocabolario per solo dominio non l'avrebbe contenuto, e ne sarebbe
nata una lista in piu' accanto -- il difetto che questo modulo esiste per
chiudere.

**Le righe con classe PENDONO dal loro dominio.** `("sensor", "energy")` non
ripete cio' che la riga di `sensor` gia' dice: si collega, per identificatore,
come vuole la seconda fondamenta. Una coppia il cui dominio non ha una riga
non si puo' costruire: e' un errore di costruzione, non un buco che si scopre
leggendo.

**Tre domande, una casa.** Le tre metriche non sono tre elenchi: sono tre modi
di interrogare la stessa riga.

1. «Serve all'obiettivo?» -> `aspect_of` -- la gamba dell'osservatore
   (`chi c'e'`, `comfort`, `dispersione`, `energia`, `buono stato`,
   `sicurezza`) o niente. Prima viveva in `mind/baseline.py::aspect` e nelle
   sue otto costanti satellite.
2. «Si accende e si spegne, e qual e' il suo riposo?» -> `is_operable`,
   `resting_states_of`, `resting_states`. Prima erano `_OPERABLE`, `_RESTING`
   e `_UNKNOWN` in `mind/facts.py`.
3. «Cosa sa fare?» -> `capability_names`. Prima era `_FEATURE_NAMES` in
   `home_space/topology.py`.

**Ogni campo dichiara da dove viene, e non c'e' modo di scriverne uno che non
lo dichiari** -- vedi `Field` qui sotto. Le provenienze sono tre e non di piu'
(`Provenance`), perche' una riga mescola inevitabilmente fatti del fornitore e
giudizi nostri, e confonderli sarebbe il difetto ricorrente di questa codebase
-- due cose diverse dette con una parola sola -- alla sua scala piu' grande.

**Il confine con `ha_vocabulary.py`, scritto perche' non diventi un
doppione.** Sono due meta' della stessa famiglia, e la domanda «perche' non un
modulo solo?» va risposta invece che elusa. `ha_vocabulary.py` porta cio' che
Home Assistant DOCUMENTA e non manda mai in un payload -- il SIGNIFICATO in
parole di uno `state_class`, di un `device_class`, di un `entity_category`:
tutto `importato`, tutto citato dalla fonte con la sua versione. Questo modulo
porta cio' che Home Assistant NON PUO' dirci -- a quale gamba dell'obiettivo un
tipo serve, quale suo stato vale «a riposo»: tutto `nostro`. Le due meta' non
si sovrappongono in nessuna riga: nessun fatto vive di qua e di la'.

Restano separate **per questa fetta**, e non per sempre. L'argomento piu' forte
per unirle e' misurabile e va scritto: `DEVICE_CLASS_MEANING` e' indicizzato
per `(dominio, classe)` -- **la stessa chiave che qui e' il TIPO** -- quindi il
suo posto naturale e' un campo `meaning` sulle righe di questo modulo, con
provenienza `importato`. Farlo adesso vorrebbe dire toccare un modulo che
nessuna delle tre metriche di questa fetta legge; il piano lo prevede gia'
(fetta 6: «le tre di `ha_vocabulary.py` sono gia' nella forma giusta e vanno
COLLEGATE, non riscritte»). Fino ad allora il confine e' questo: **una frase
che spiega cosa significa un valore sta in `ha_vocabulary.py`; un giudizio su
cosa un tipo serve o quando ha finito sta qui.** Chi si trova a scrivere una
riga e non sa quale dei due, ha trovato il caso che scioglie la fetta 6.

**Cosa questo modulo NON fa, e chi lo fa al posto suo.** Non chiede niente a
Home Assistant: la lettura viva sta in `proxy/state_translations.py` e in
`action/registry.py` (piano, fetta 3), e **il censore che confronta cio' che HA
pubblica con cio' che questo vocabolario rivendica sta in `type_census.py`**
(fetta 4, 08/09/2026). Sono tre moduli e non uno apposta: un vocabolario che
leggesse la rete congelerebbe all'import un dato che e' «di adesso» per
definizione, e un censore dentro il vocabolario giudicherebbe se stesso.

**Cosa il censore ha gia' cambiato qui.** Prima le quattro tabelle di
capacita' di `lock`, `humidifier`, `lawn_mower` e `assist_satellite`, entrate
perche' lui le ha nominate: il registro dei servizi di questa casa dichiarava
bit per domini che non avevano nessuna tabella. Poi, l'08/09/2026, **le sei
decisioni del proprietario** sulle nove domande che aveva lasciato aperte: i sei
modi di `water_heater` sono funzionamento, lo `stopped` di `cover` e `valve` e'
riposo, `locking`/`unlocking` di `lock` sono funzionamento, `lawn_mower` si
tratta come `vacuum`, `remote` e `siren` sono accendibili con `off` a riposo, e
quattro domini (`assist_satellite`, `camera`, `timer`, `group`) restano fuori
con la ragione scritta nel censore.

Cio' che il censore nomina e che NON e' nostro decidere resta aperto in
`type_census.OPEN_QUESTIONS`, con la domanda scritta: **110 voci** -- 109 classi
del dispositivo mai nominate, e `lock=jammed`, che ha la decisione presa (e' un
GUASTO) e non ha ancora un posto dove scriverla, perche' il genere si decide
per soggetto e non per stato.

Spec: `docs/design/2026-09-07-l-anagrafe-dei-tipi.md`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from enum import Enum
from types import MappingProxyType


class Provenance(Enum):
    """Da dove viene un campo del vocabolario. Tre, e non di piu'.

    Il valore di ogni voce e' la parola italiana con cui la spec la nomina:
    e' cio' che una persona legge in un rapporto o in un messaggio d'errore, e
    non deve tradursi due volte fra il codice e la prosa.
    """

    #: Letto da questa casa adesso -- traduzioni, registro dei servizi. Non
    #: invecchia: e' il dato di adesso.
    ASKED = "chiesto"

    #: Copiato dal sorgente o dalla documentazione di Home Assistant, con la
    #: versione da cui viene. Invecchia: si data e si sorveglia.
    IMPORTED = "importato"

    #: Un giudizio che Home Assistant non puo' darci. Non invecchia, ma puo'
    #: restare indietro rispetto a cio' che esiste -- ed e' cio' che il
    #: censore misurera'.
    OURS = "nostro"


def _frozen(value):
    """Il valore di un campo, reso immodificabile.

    Un campo dichiarato e poi mutato da chi lo legge sarebbe una seconda casa
    aperta a runtime -- la fondamenta 2 aggirata senza che nessun diff la
    mostri. Si congela alla dichiarazione, dove la struttura puo' ancora
    imporlo.
    """
    if isinstance(value, (set, frozenset)):
        return frozenset(value)
    if isinstance(value, dict):
        return MappingProxyType(dict(value))
    if isinstance(value, list):
        return tuple(value)
    return value


class Field(ABC):
    """Un campo del vocabolario: un valore E la sua provenienza, inseparabili.

    **Un campo senza provenienza non si puo' costruire, e non e' un controllo
    a valle che lo impedisce: e' la struttura.** La provenienza non e' un
    parametro che si possa dimenticare, sbagliare o mettere a `None` -- e' la
    CLASSE. `Field` e' astratta (`provenance` e' astratta): `Field("x")`
    solleva `TypeError` prima ancora che l'oggetto esista. Gli unici modi di
    ottenerne uno sono `Asked`, `Imported` e `Ours`, e ciascuno porta la
    propria provenienza scritta addosso.

    Era la parte da fare bene: se la si potesse costruire senza dichiararla,
    prima o poi qualcuno lo farebbe -- e il vocabolario tornerebbe a essere un
    elenco che mescola i fatti del fornitore con i giudizi nostri.
    """

    __slots__ = ("_value",)

    def __init__(self, value) -> None:
        self._value = _frozen(value)

    @property
    def value(self):
        return self._value

    @property
    @abstractmethod
    def provenance(self) -> Provenance:
        """Da dove viene questo campo. Astratta apposta: e' cio' che rende
        `Field` inutilizzabile da sola."""

    def __eq__(self, other) -> bool:
        return (type(self) is type(other) and self._value == other._value
                and self.provenance is other.provenance)

    def __hash__(self) -> int:
        return hash((type(self).__name__, self._value))

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._value!r})"


class Asked(Field):
    """Letto da questa casa adesso.

    Nessun campo di questo tipo esiste ancora: la lettura viva e' la fetta
    successiva, e dichiararne uno oggi sarebbe un «dato di adesso» che nessuno
    ha chiesto. La classe c'e' lo stesso perche' la forma deve reggere tutte e
    tre le provenienze prima che la terza arrivi -- non dopo.
    """

    __slots__ = ()

    @property
    def provenance(self) -> Provenance:
        return Provenance.ASKED


class Imported(Field):
    """Copiato dal sorgente o dalla documentazione di Home Assistant.

    **La versione non e' facoltativa.** Un fatto importato senza la versione da
    cui viene non si sa vecchio, e un fatto che non si sa vecchio si continua a
    credere per sempre: e' misurato, non temuto -- lo stesso bit (64) e' stato
    rimosso in due domini indipendenti fra `2024.7.0` e `2026.9.1`. Il
    costruttore la esige, come `Field` esige la provenienza.
    """

    __slots__ = ("_ha_version", "_source")

    def __init__(self, value, *, ha_version: str, source: str) -> None:
        if not ha_version or not source:
            raise ValueError(
                "un campo importato senza versione o senza fonte non si sa "
                "vecchio, e un fatto che non si sa vecchio si crede per sempre")
        super().__init__(value)
        self._ha_version = ha_version
        self._source = source

    @property
    def provenance(self) -> Provenance:
        return Provenance.IMPORTED

    @property
    def ha_version(self) -> str:
        return self._ha_version

    @property
    def source(self) -> str:
        return self._source

    def __eq__(self, other) -> bool:
        return (super().__eq__(other) and self._ha_version == other.ha_version
                and self._source == other.source)

    def __hash__(self) -> int:
        return hash((type(self).__name__, self._value, self._ha_version))


class Ours(Field):
    """Un giudizio che Home Assistant non puo' darci: a quale gamba
    dell'obiettivo un tipo serve, quale suo stato vale «a riposo». Nessuna API
    di HA lo dice, e non lo dira' mai."""

    __slots__ = ()

    @property
    def provenance(self) -> Provenance:
        return Provenance.OURS


#: Le tre provenienze, e le tre classi che le portano. Scritte qui perche' una
#: prova possa contarle: una quarta provenienza nata di nascosto e' esattamente
#: il modo in cui «da dove viene questo dato» tornerebbe a essere un'opinione.
PROVENANCES = frozenset(Provenance)
FIELD_KINDS = (Asked, Imported, Ours)


class TypeRow:
    """La riga di UN tipo: un dominio, oppure una coppia dominio + classe.

    I campi stanno in una mappa nome -> `Field`, e non c'e' modo di metterci
    dentro un valore nudo: il costruttore rifiuta cio' che non e' un `Field`,
    quindi una riga con un campo senza provenienza non arriva mai a esistere.
    Il rifiuto e' nel costruttore e non in una prova a valle apposta -- una
    prova dice che oggi nessuno l'ha fatto, il costruttore dice che non si puo'
    fare.
    """

    __slots__ = ("device_class", "domain", "fields")

    def __init__(self, domain: str, device_class: str | None,
                 fields: Mapping[str, Field]) -> None:
        if not isinstance(domain, str) or not domain:
            raise ValueError("una riga senza dominio non e' un tipo")
        for name, field in fields.items():
            if not isinstance(field, Field):
                raise TypeError(
                    f"il campo `{name}` di `{domain}` non dichiara la propria "
                    f"provenienza: e' un {type(field).__name__} nudo, non un "
                    "`Asked`/`Imported`/`Ours`")
        object.__setattr__(self, "domain", domain)
        object.__setattr__(self, "device_class", device_class)
        object.__setattr__(self, "fields", MappingProxyType(dict(fields)))

    def __setattr__(self, name, value):
        raise AttributeError(
            "una riga del vocabolario non si modifica dopo la dichiarazione")

    @property
    def key(self) -> tuple[str, str | None]:
        return (self.domain, self.device_class)

    def __repr__(self) -> str:
        return f"TypeRow{self.key!r}"


class TypeVocabulary:
    """Il vocabolario: le righe, e come si interrogano.

    **Una coppia orfana non si costruisce.** Aggiungere `("sensor", "energy")`
    senza una riga per `sensor` solleva: il collegamento per identificatore e'
    una condizione di costruzione, non una speranza.
    """

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str | None], TypeRow] = {}

    # -- la costruzione ----------------------------------------------------

    def add(self, domain: str, device_class: str | None = None,
            **fields: Field) -> TypeRow:
        key = (domain, device_class)
        if key in self._rows:
            raise ValueError(
                f"il tipo {key!r} ha gia' una riga: un tipo ha una casa sola")
        if device_class is not None and (domain, None) not in self._rows:
            raise KeyError(
                f"la coppia {key!r} non si puo' collegare: il dominio "
                f"`{domain}` non ha una riga da cui pendere")
        row = TypeRow(domain, device_class, fields)
        self._rows[key] = row
        return row

    def add_all(self, domain: str, device_classes: Iterable[str],
                **fields: Field) -> None:
        """Le coppie di uno stesso dominio che condividono gli stessi campi.

        Non e' una scorciatoia di scrittura: e' cio' che impedisce che
        `("binary_sensor", "smoke")` e `("binary_sensor", "gas")` finiscano per
        divergere sul giudizio che li ha messi insieme.
        """
        for device_class in device_classes:
            self.add(domain, device_class, **fields)

    def extend(self, domain: str, device_class: str | None = None,
               **fields: Field) -> TypeRow:
        """Campi IN PIU' su una riga che esiste gia'.

        Le tre metriche si dichiarano in tre punti diversi di questo modulo --
        si leggono meglio cosi' -- ma restano tre campi della STESSA riga: un
        secondo `TypeRow` per lo stesso tipo sarebbe la seconda casa che
        il vocabolario esiste per non avere. Un campo gia' presente non si
        sovrascrive: sarebbe un giudizio che ne cancella un altro in silenzio.
        """
        key = (domain, device_class)
        row = self._rows.get(key)
        if row is None:
            raise KeyError(f"il tipo {key!r} non ha una riga da estendere")
        for name in fields:
            if name in row.fields:
                raise ValueError(
                    f"il campo `{name}` di {key!r} e' gia' dichiarato: "
                    "sovrascriverlo cancellerebbe un giudizio in silenzio")
        merged = dict(row.fields)
        merged.update(fields)
        self._rows[key] = TypeRow(domain, device_class, merged)
        return self._rows[key]

    # -- la lettura --------------------------------------------------------

    def rows(self) -> tuple[TypeRow, ...]:
        return tuple(self._rows.values())

    def row(self, domain: str, device_class: str | None = None) -> TypeRow | None:
        return self._rows.get((domain, device_class))

    def domains(self) -> frozenset[str]:
        return frozenset(domain for domain, device_class in self._rows
                         if device_class is None)

    def pairs(self) -> frozenset[tuple[str, str]]:
        return frozenset((domain, device_class)
                         for domain, device_class in self._rows
                         if device_class is not None)

    def field(self, domain: str, device_class: str | None, name: str) -> Field | None:
        """Il campo `name` per questo tipo -- **prima la coppia, poi il dominio
        da cui pende**.

        E' qui che «si collega invece di copiare» diventa un comportamento e
        non una buona intenzione: la coppia non ripete i campi del dominio, li
        eredita, e il giorno in cui il dominio cambia non resta una seconda
        copia indietro.
        """
        if device_class:
            row = self._rows.get((domain, device_class))
            if row is not None and name in row.fields:
                return row.fields[name]
        row = self._rows.get((domain, None))
        if row is not None and name in row.fields:
            return row.fields[name]
        return None

    def value(self, domain: str, device_class: str | None, name: str, default=None):
        field = self.field(domain, device_class, name)
        return default if field is None else field.value


# --------------------------------------------------------------------------
# I nomi dei campi. Scritti una volta: un campo cercato con una stringa
# sbagliata risponderebbe «non lo so» invece di sbagliare, ed e' il modo in cui
# una metrica smetterebbe di funzionare in silenzio.
# --------------------------------------------------------------------------

#: La gamba dell'obiettivo a cui questo tipo serve.
ASPECT = "aspect"

#: `(attributo, valore atteso)`: la gamba vale solo se l'entita' porta quel
#: valore in quell'attributo. Oggi esiste per `device_tracker` e solo per lui.
ASPECT_GUARD = "aspect_guard"

#: Se questo tipo «funziona»: si accende e si spegne, si apre e si chiude.
OPERABLE = "operable"

#: Gli stati che, per questo tipo, valgono «ha finito».
RESTING_STATES = "resting_states"

#: Gli stati che, per questo tipo, valgono «sta funzionando»: non un riposo,
#: non un «non lo so». Il valore e' `stato -> ragione scritta`, come per gli
#: attributi scartati -- un giudizio senza ragione non si dichiara.
#:
#: **Perche' esiste un campo, e non basta «tutto cio' che non e' riposo».**
#: `_is_on` risponde gia' cosi', e continuera' a rispondere cosi': questo campo
#: non cambia il comportamento di nessun lettore. Cambia **chi ha guardato**.
#: Fino all'08/09/2026 sei stati di `water_heater` e tre di `lock` non erano ne'
#: riposi ne' ignoti, e nessuno poteva dire se fosse una decisione o una
#: dimenticanza: il censore li ha nominati proprio perche' nessuna riga li
#: rivendicava. Dichiararli qui e' la risposta «li abbiamo guardati, e
#: funzionano» -- l'altra meta' del riposo, senza la quale la metrica 2 sa dire
#: soltanto quando una cosa ha finito.
WORKING_STATES = "working_states"

#: I nomi dei bit di `supported_features`, dominio per dominio.
CAPABILITY_NAMES = "capability_names"

#: I nomi degli attributi che, per questo dominio, dicono COSA L'ENTITA' PUO'
#: FARE -- il campo di manovra: `hvac_modes`, `min_temp`, `effect_list`.
CAPABILITY_ATTRIBUTES = "capability_attributes"

#: I nomi degli attributi che, per questo dominio, dicono COM'E' ADESSO --
#: `current_temperature`, `brightness`, `media_title`.
STATE_ATTRIBUTES = "state_attributes"

#: Attributi che Home Assistant classifica come capacita' e che qui NON lo
#: sono. Il valore e' `nome -> ragione scritta`: un'eccezione senza ragione
#: non si dichiara.
CAPABILITY_ATTRIBUTES_DROPPED = "capability_attributes_dropped"

#: Attributi che Home Assistant NON elenca fra le capacita' del dominio e che
#: qui lo sono. Stessa forma, stessa regola: `nome -> ragione scritta`.
CAPABILITY_ATTRIBUTES_ADDED = "capability_attributes_added"

#: Attributi che Home Assistant classifica come capacita' e che dicono cosa
#: quell'entita' puo' ASSUMERE, non cosa le si puo' IMPORRE. Stessa forma
#: delle due sopra: `nome -> ragione scritta`.
ASSUMABLE_ATTRIBUTES = "assumable_attributes"

#: Per un parametro di servizio, quale attributo di QUESTA entita' porta il
#: suo limite vero. Il valore e' `parametro -> {"min": ..., "max": ...}`
#: oppure `parametro -> {"options": ...}`.
PARAMETER_LIMITS = "parameter_limits"


# --------------------------------------------------------------------------
# La fonte dei campi importati.
# --------------------------------------------------------------------------

FEATURE_SOURCE_HA_VERSION = "2026.9.1"

FEATURE_SOURCE = (
    "home-assistant/core, tag 2024.7.0 e 2026.9.1 -- "
    "homeassistant/components/<dominio>/const.py (o __init__.py) per ogni "
    "`*EntityFeature`, scaricati e confrontati riga per riga sui DUE tag, mai "
    "su `dev`. Vedi `tests/test_feature_tables_pinned_to_source.py`, che "
    "riporta i bit alla fonte invece di importarli da qui."
)


# --------------------------------------------------------------------------
# LA COSTRUZIONE DELL'ANAGRAFE
# --------------------------------------------------------------------------
#
# L'ordine di dichiarazione non conta per la lettura (`field` risolve per
# chiave, non per posizione): conta per chi legge, e segue le tre metriche.

_vocabulary = TypeVocabulary()


# -- metrica 1: la gamba ----------------------------------------------------
#
# **Il pavimento non e' una lista scritta a mano.** Si deriva da cio' che Home
# Assistant dichiara gia' su ogni entita' -- dominio, classe del dispositivo,
# `source_type` -- perche' una lista a mano invecchia col primo dispositivo
# nuovo e nessuno se ne accorge. **Non `state_class`** (correzione di parole
# della review, mandato «il bilancio dell'energia», punto 7, 27/08/2026):
# resta grezzo conservato nell'archivio (`mind/store.py`), non un criterio del
# pavimento.
#
# **Perche' esiste un pavimento.** Il prompt dell'obiettivo decide cosa entra
# nelle osservazioni, quindi e' un punto singolo che puo' ACCECARE
# l'osservatore -- e cio' che non e' stato osservato non esiste piu':
# riscrivere il prompt fra tre mesi non fa ricomparire i tre mesi mancanti. Il
# pavimento e' cio' che il prompt non puo' togliere. Sopra di esso allarga;
# sotto, mai.

ASPECTS = ("chi c'e'", "comfort", "dispersione", "energia", "buono stato",
           "sicurezza")

_vocabulary.add("person", aspect=Ours("chi c'e'"))

# MISURATO il 26/08/2026: 65 dei 73 tracker di questa casa sono `router` --
# l'NVR, Alexa, un Echo, una TV, una lampada. Dicono «questo apparecchio e'
# connesso al wifi», non «c'e' qualcuno in casa». I 4 `gps` sono i telefoni, e
# sono le fonti dietro le due `person`. Non e' volume (i 65 fanno 114 cambi al
# giorno, lo zero per cento): e' che non significano niente per l'obiettivo.
#
# **E' l'unica riga con una GUARDIA**, e la guardia sta nella riga proprio
# perche' non finisca in un ramo scritto a mano dentro il lettore: la
# condizione fa parte del giudizio, non del codice che lo legge. Nel dubbio si
# sta fuori -- un tracker che non dichiara il proprio `source_type` non e' una
# persona finche' non lo dice.
_vocabulary.add("device_tracker",
              aspect=Ours("chi c'e'"),
              aspect_guard=Ours(("source_type", "gps")))

_vocabulary.add("climate", aspect=Ours("comfort"))
_vocabulary.add("cover", aspect=Ours("dispersione"))

# La sesta gamba, aggiunta il 26/08/2026 dalla review del primo task: la prima
# stesura non conteneva gli allarmi -- ne' fumo, ne' gas, ne' monossido, ne'
# allagamento, ne' serrature, ne' pannello dell'allarme -- ed era il buco
# peggiore possibile, sulla categoria di dati che conta piu' di tutte
# (`docs/design/2026-08-26-l-osservatore.md` §4).
#
# Il vocabolario gemello vive in `home_space/briefing.py::_EVENT_DOMAINS` e
# `_EVENT_CLASSES`, e resta fuori da questo vocabolario **dichiaratamente**
# (piano, fetta 6): `briefing.py` risponde a «cosa e' notevole ADESSO» (un
# evento da annunciare), il vocabolario a «cosa si osserva SEMPRE» -- due domande
# i cui elenchi possono divergere per ragioni proprie. Chi tocca uno dei due
# guardi anche l'altro.
_vocabulary.add("lock", aspect=Ours("sicurezza"),
              resting_states=Ours({"locked"}))
# «Un allarme si INSERISCE per stare a riposo, non il contrario» -- correzione
# al rovesciamento della review, punto 3b: `disarmed` e `triggered` NON sono
# riposi, per quanto suoni controintuitivo a chi legge in fretta.
_vocabulary.add("alarm_control_panel", aspect=Ours("sicurezza"),
              resting_states=Ours({"armed_home", "armed_away", "armed_night",
                                   "armed_vacation", "armed_custom_bypass"}))
_vocabulary.add("siren", aspect=Ours("sicurezza"), resting_states=Ours({"off"}))

# `binary_sensor` e `sensor`: il dominio da solo non porta nessuna gamba -- il
# giudizio vive sulle COPPIE qui sotto, che dal dominio ereditano il riposo
# invece di ripeterlo.
_vocabulary.add("binary_sensor", resting_states=Ours({"off"}))
_vocabulary.add("sensor")

_vocabulary.add_all("binary_sensor", ("presence", "occupancy", "motion"),
                  aspect=Ours("chi c'e'"))
_vocabulary.add_all("binary_sensor", ("door", "window", "opening", "garage_door"),
                  aspect=Ours("dispersione"))
# Trappola gia' documentata nel prodotto: la classe si chiama
# `carbon_monoxide`, NON `co`. E trappola seconda: `gas` compare anche fra i
# sensori dell'energia qui sotto, ma e' un'altra entita' -- il rilevatore di
# fuga su `binary_sensor`, non il contatore su `sensor`. Le coppie le separano
# per costruzione: un elenco per sola classe le fonderebbe.
_vocabulary.add_all("binary_sensor",
                  ("smoke", "gas", "carbon_monoxide", "moisture", "safety",
                   "tamper", "problem", "heat", "cold"),
                  aspect=Ours("sicurezza"))

_vocabulary.add_all("sensor", ("temperature", "humidity"), aspect=Ours("comfort"))
# Qualita' dell'aria: la gamba «comfort» promette «che aria si respira», non
# solo temperatura e umidita'. `carbon_monoxide` NON e' qui: e' una
# concentrazione di un gas letale, non comfort -- sta in «sicurezza», sotto.
_vocabulary.add_all("sensor",
                  ("carbon_dioxide", "pm1", "pm10", "pm25",
                   "volatile_organic_compounds",
                   "volatile_organic_compounds_parts", "nitrogen_dioxide",
                   "nitrogen_monoxide", "nitrous_oxide", "ozone",
                   "sulphur_dioxide"),
                  aspect=Ours("comfort"))
_vocabulary.add("sensor", "carbon_monoxide", aspect=Ours("sicurezza"))
# `battery` e' `diagnostic`, e le entita' di servizio sono 604 su 1226 in
# questa casa. Il filtro e' per CLASSE, non per categoria: escludere
# `diagnostic` in blocco toglierebbe «buono stato».
_vocabulary.add("sensor", "battery", aspect=Ours("buono stato"))
# DEBITO DICHIARATO il 26/08/2026, CHIUSO A LIVELLO DI EPISODIO il 27/08/2026
# (mandato «le direzioni dell'energia»): Home Assistant usa `device_class:
# energy` (e `power`) sia per l'energia PRODOTTA da un fotovoltaico sia per
# quella PRELEVATA dalla rete -- la classe da sola non separa le due
# direzioni, e indovinarle dal NOME del sensore si romperebbe sul prossimo
# inverter. **Questa gamba resta un'unica «energia»**, vera per tutti e 15 i
# sensori di questa casa, produzione compresa; la direzione vive DENTRO
# l'episodio (`mind/facts.py::aggregate_day`, parametro `direzioni`), non e'
# una gamba nuova.
#
# **`state_class: total_increasing` da solo NON basta per «energia»**
# (correzione del 27/08/2026): prima di quella correzione un contatore
# sempre-crescente qualunque finiva qui -- i gigabyte del router
# (`device_class: data_size`) erano archiviati come energia e producevano un
# episodio ogni notte. Solo le classi dichiarate qui sotto sono energia.
_vocabulary.add_all("sensor", ("energy", "power", "gas", "water"),
                  aspect=Ours("energia"))


# -- metrica 2: accendibile, e il suo riposo --------------------------------
#
# **LA REGOLA (spec §6, corretta il 26 agosto): un tipo accendibile porta i
# suoi stati di riposo NELLA STESSA MODIFICA.** Non e' piu' una
# raccomandazione in un commento: `_verify_operable_types_bring_their_rest()`
# in fondo a questo modulo la impone all'importazione, e
# `tests/test_type_vocabulary.py` la prova. E' la terza volta che lo stesso
# difetto nasce dal separarle -- l'allarme rovesciato, l'energia che non
# chiudeva mai, e i quattro domini aggiunti senza guardare i loro riposi (il
# vacuum che torna alla base e il media_player fermo restavano oggetti aperti
# per sempre). Un tipo dimenticato cade in silenzio; un tipo aggiunto a meta'
# produce oggetti che non si chiudono mai -- lo stesso costo, dai due lati
# opposti dello stesso elenco.
#
# **Cio' che questa regola NON copriva, ed e' stato chiuso l'08/09/2026**: la
# regola impone che un tipo accendibile abbia ALMENO un riposo, non che TUTTI i
# suoi stati canonici siano classificati. `water_heater` era il caso vivo --
# `eco`, `electric`, `gas`, `heat_pump`, `high_demand`, `performance` non erano
# ne' riposi ne' ignoti, e un boiler in `eco` avrebbe aperto un episodio che non
# si chiude mai. Il censore (fetta 4) li ha nominati, il proprietario li ha
# decisi (fetta 5), e la risposta e' scritta sulla riga di `water_heater` qui
# sotto: sono **funzionamento**, e il campo `working_states` e' il posto dove
# «li abbiamo guardati» smette di essere indistinguibile da «nessuno ci ha mai
# pensato».
#
# **Il riposo e il funzionamento sono le due meta' della stessa metrica.** Il
# riposo cambia il comportamento (`_is_on` chiude un episodio); il funzionamento
# no -- e' gia' cio' che `_is_on` risponde per esclusione. Dichiararlo lo stesso
# non e' un doppione: e' cio' che distingue una decisione da un silenzio, ed e'
# l'unica forma in cui il censore puo' vedere la differenza.
#
# `climate` e `cover` hanno gia' la loro riga sopra (portano una gamba): la
# seconda metrica si aggiunge alla stessa riga, non ne apre una seconda.

# I sei modi operativi di un termostato acceso. Non sono sei riposi travestiti:
# `heat_cool` e `auto` sono precisamente il termostato che LAVORA senza che
# nessuno gli dica come. Il suo unico riposo resta `off`.
_vocabulary.extend("climate", operable=Ours(True), resting_states=Ours({"off"}),
                 working_states=Ours({
                     "heat": "il termostato sta riscaldando o e' impostato per farlo",
                     "cool": "il termostato sta raffrescando o e' impostato per farlo",
                     "heat_cool": "decide da se' quale delle due: e' acceso, non fermo",
                     "auto": "come `heat_cool` -- il modo automatico e' un modo, non una pausa",
                     "dry": "sta deumidificando: e' un modo operativo, non una pausa",
                     "fan_only": "muove aria e basta, ma il ventilatore gira",
                 }))
# `stopped` e' un RIPOSO -- decisione del proprietario dell'08/09/2026, e il
# censore l'aveva trovato al primo giro (non era nel capitolato). Una tapparella
# ferma a meta' corsa non si sta muovendo: mezza aperta e' uno stato, non un
# guasto e non una corsa in sospeso. Prima di questa riga il suo unico riposo
# era `closed`, quindi una tapparella lasciata a meta' teneva aperto per sempre
# l'episodio cominciato quando si e' mossa.
_vocabulary.extend("cover", operable=Ours(True),
                 resting_states=Ours({"closed", "stopped"}),
                 working_states=Ours({
                     "open": "una tapparella aperta e' cio' che disperde: e' il fatto da osservare",
                     "opening": "si sta muovendo: la corsa e' in atto, non finita",
                     "closing": "si sta muovendo: la corsa e' in atto, non finita",
                 }))
_vocabulary.add("switch", operable=Ours(True), resting_states=Ours({"off"}))
_vocabulary.add("light", operable=Ours(True), resting_states=Ours({"off"}))
_vocabulary.add("fan", operable=Ours(True), resting_states=Ours({"off"}))
# **I sei modi del boiler sono FUNZIONAMENTO** -- decisione del proprietario,
# 08/09/2026, sulla prima delle nove domande del censore. Sono modi OPERATIVI,
# non pause: un boiler in `eco` scalda, solo con meno foga. Il suo unico riposo
# resta `off`, ed e' l'unico stato in cui non sta facendo niente.
_vocabulary.add("water_heater", operable=Ours(True), resting_states=Ours({"off"}),
              working_states=Ours({
                  "eco": "modo operativo a consumo ridotto: scalda, con meno foga",
                  "gas": "sta scaldando a gas -- la fonte, non una pausa",
                  "electric": "sta scaldando con la resistenza elettrica",
                  "heat_pump": "sta scaldando con la pompa di calore",
                  "high_demand": "modo per i grandi prelievi: scalda di piu', non di meno",
                  "performance": "modo a piena potenza",
              }))
# `humidifier`: solo `on`/`off`, nessuno stato intermedio.
_vocabulary.add("humidifier", operable=Ours(True), resting_states=Ours({"off"}))
# `vacuum`: `docked` (in base, eventualmente in carica), `idle` (fermo, non in
# carica ne' in errore), `returning` (sta rientrando, non sta piu' pulendo),
# `error`, `off`. Solo `cleaning` e' acceso.
#
# `off` e' entrato l'08/09/2026 con la sparizione di `_STATE_TRANSLATION`: la
# tabella cieca al dominio lo rivendicava per tutti, e quando e' sparita il
# censore ha nominato `vacuum=off` -- un aspirapolvere spento e' fermo, e non
# c'e' niente da decidere. Non cambia niente di osservabile (`off` era gia'
# nell'unione dei riposi, che e' cio' che `_is_on` legge): cambia che adesso un
# tipo lo rivendica.
_vocabulary.add("vacuum", operable=Ours(True),
              resting_states=Ours({"docked", "returning", "error", "idle", "off"}),
              working_states=Ours({
                  "cleaning": "sta pulendo: e' l'unico stato in cui l'aspirapolvere lavora",
                  "paused": "un'attivita' SOSPESA, non finita -- vedi `media_player` sotto",
              }))
# `valve`: `open`, `opening`, `closing` sono TUTTI attivi, come per `cover`
# (con cui condivide `closed` fra i riposi) -- una valvola a meta' apertura non
# e' ferma, e `opening`/`closing` fra i riposi chiuderebbe l'oggetto a meta'
# transizione. `stopped` invece SI', dall'08/09/2026 e per la stessa decisione
# del proprietario che l'ha dato a `cover`: fermata a meta' corsa e' uno stato,
# non una corsa in sospeso.
_vocabulary.add("valve", operable=Ours(True),
              resting_states=Ours({"closed", "stopped"}),
              working_states=Ours({
                  "open": "una valvola aperta e' cio' che lascia passare: e' il fatto",
                  "opening": "si sta muovendo: la corsa e' in atto, non finita",
                  "closing": "si sta muovendo: la corsa e' in atto, non finita",
              }))
# `lawn_mower`: **si tratta come `vacuum`** -- decisione del proprietario
# dell'08/09/2026, quarta delle nove domande. Stessa forma, stesso giudizio:
# `docked` e' la base, `returning` non e' piu' taglio, `error` e' fermo, e solo
# `mowing` e' acceso. Nessuna lista di questo prodotto lo aveva mai guardato:
# l'ha nominato il censore.
_vocabulary.add("lawn_mower", operable=Ours(True),
              resting_states=Ours({"docked", "returning", "error"}),
              working_states=Ours({
                  "mowing": "sta tagliando: e' l'unico stato in cui il tosaerba lavora",
                  "paused": "un taglio SOSPESO, non finito -- come la pausa del vacuum",
              }))
# `remote` e `siren`: **accendibili**, con `off` a riposo -- decisione del
# proprietario dell'08/09/2026, nona delle nove domande. Home Assistant li
# dichiara accendibili (`turn_on`+`turn_off`) e pubblica per entrambi `on`/`off`;
# la spec §4 li metteva fra le sette esclusioni motivate da «li' `on` significa
# 'abilitata', non 'accesa' -- il difetto che `briefing._EVENT_DOMAINS`
# documenta di aver gia' pagato», e **per questi due quella frase era smentita
# dal codice che citava**: `_EVENT_DOMAINS` li CONTIENE entrambi, cioe' il
# prodotto quel `on` lo annunciava gia' come un'accensione mentre l'esclusione
# affermava il contrario. L'esclusione cade.
#
# `siren` ha gia' la sua riga sopra (porta la gamba «sicurezza» e il riposo
# `off`): qui si aggiunge la sola meta' che le mancava.
_vocabulary.add("remote", operable=Ours(True), resting_states=Ours({"off"}))
_vocabulary.extend("siren", operable=Ours(True))
# `media_player`: `idle` (acceso ma non riproduce nulla), `standby` (deprecato
# verso `off`/`idle` dalla 2026.8, ma ancora prodotto da alcune integrazioni --
# questa casa ce l'ha). `on` resta acceso, e cosi' `buffering` (sta per
# riprodurre, non e' un riposo).
#
# **`paused` NON e' un riposo, ne' qui ne' per il vacuum** (giro di pulizia del
# 26 agosto, punto 3 -- deciso ALLORA, contro il mandato precedente che
# l'aveva messo fra i riposi). Un riposo e' «ha finito»: il robot e' tornato
# alla base, la TV non riproduce piu' nulla. Una pausa e' un'attivita'
# SOSPESA, non finita -- il film torna dove si era fermato, la pulizia
# riprende da dove si era interrotta. Trattarla come un riposo spezzava un
# episodio solo in due.
_vocabulary.add("media_player", operable=Ours(True),
              resting_states=Ours({"off", "idle", "standby"}),
              working_states=Ours({
                  "playing": "sta riproducendo: c'e' qualcosa in corso",
                  "paused": "un'attivita' SOSPESA, non finita: il film riparte "
                            "da dove si era fermato",
                  "buffering": "sta per riprodurre -- chiuderlo spezzerebbe "
                               "l'episodio di un film che sta per ripartire",
                  "on": "acceso senza dire altro: non e' spento, ed e' tutto cio' che si sa",
              }))

# -- le due meta' del funzionamento su tipi che NON sono accendibili ---------
#
# `lock` e `alarm_control_panel` non sono dichiarati accendibili -- una
# serratura non si «accende» -- ma portano la gamba «sicurezza», e la gamba
# «sicurezza» apre e chiude episodi con la STESSA forma del funzionamento
# (`mind/facts.py`, ramo `sicurezza`: «il genere e' diverso, la forma no»).
# Quindi anche loro hanno stati che valgono «sta succedendo», e finche' nessuno
# li dichiarava il censore non poteva distinguerli da una dimenticanza.
#
# **`locking` e `unlocking` sono FUNZIONAMENTO** -- decisione del proprietario
# dell'08/09/2026, terza delle nove domande: la serratura si sta muovendo.
# `open`/`opening` sono la stessa cosa per una serratura che sa aprire davvero
# la porta (`LockEntityFeature.OPEN`).
#
# **`jammed` NON e' qui, ed e' una decisione presa e non ancora eseguibile.**
# Il proprietario l'ha giudicato un GUASTO -- «e' inceppata, non sta
# lavorando» -- e un guasto e' un GENERE, non uno stato di funzionamento. Il
# genere oggi si decide per SOGGETTO (`facts.genre_for(soggetto, gamba)`, che
# lo stato non lo riceve nemmeno), quindi non c'e' nessun posto in cui `jammed`
# possa entrare senza mentire: metterlo qui direbbe «sta funzionando», che e'
# esattamente cio' che il proprietario ha escluso. Resta **aperto e nominato**
# in `type_census.OPEN_QUESTIONS`, con la decisione gia' presa e cio' che
# manca per eseguirla scritto accanto. Meglio una voce aperta di una infilata
# nel posto sbagliato.
_vocabulary.extend("lock", working_states=Ours({
    "unlocked": "sbloccata: e' il fatto che la gamba sicurezza esiste per osservare",
    "locking": "si sta chiudendo: la serratura sta lavorando",
    "unlocking": "si sta aprendo: la serratura sta lavorando",
    "open": "aperta davvero, non solo sbloccata (`LockEntityFeature.OPEN`)",
    "opening": "sta aprendo la porta, non solo il chiavistello",
}))
# `triggered` e' l'allarme SCATTATO: il solo stato di questo dominio che la
# gamba «sicurezza» esiste per osservare. Non e' un riposo (i riposi sono gli
# `armed_*`: «un allarme si INSERISCE per stare a riposo, non il contrario»), e
# fino all'08/09/2026 lo rivendicava soltanto la tabella cieca al dominio che
# questa fetta ha cancellato.
_vocabulary.extend("alarm_control_panel", working_states=Ours({
    "triggered": "l'allarme e' scattato: e' il fatto piu' notevole che questa casa possa produrre",
}))


#: Gli stati che valgono riposo per QUALUNQUE tipo, e per questo non stanno su
#: nessuna riga: non sono il riposo di un dominio, sono le due forme in cui
#: Home Assistant scrive «qui non c'e' nessuno stato». Attribuirle a una riga
#: qualsiasi darebbe a un tipo un fatto che non e' suo.
ABSENT_STATE_FORMS = Ours({"none", ""})

#: Stati «non lo so», non stati della casa. Un riavvio di Home Assistant fa
#: attraversare questi due a OGNI entita', di ogni tipo: come sopra, non sono
#: di nessuno in particolare. **Non sono riposi** (correzione punto 2 del
#: secondo giro di review): la versione precedente li metteva li' dentro, e un
#: riavvio a episodio in corso CHIUDEVA l'oggetto, mentre il ritorno dello
#: stato vero ne APRIVA un secondo -- ogni riavvio spezzava in due un
#: riscaldamento acceso, o una casa lasciata disarmata. La semantica giusta e'
#: la TERZA, non «e' finito» ne' «e' cominciato»: una riga con questo stato si
#: SALTA, e l'episodio in corso resta aperto ATTRAVERSO il buco.
UNKNOWN_STATES = Ours({"unavailable", "unknown"})


# -- metrica 3: cosa sa fare ------------------------------------------------
#
# **I nomi dei bit sono IMPORTATI, e questa e' l'unica metrica che non e'
# nostra.** Home Assistant non li pubblica da nessuna API -- sono `IntFlag`
# nel sorgente -- quindi ogni tabella porta la versione da cui viene, e il
# tipo `Imported` la esige: un fatto importato senza la versione non si sa
# vecchio, e un fatto che non si sa vecchio si continua a credere per sempre.
# La prova che i bit sono quelli veri non importa da qui: li riporta alla
# fonte (`tests/test_feature_tables_pinned_to_source.py`), cosi' una mutazione
# di questa tabella non muove anche il proprio metro.
#
# Il commento che segue viene da `home_space/topology.py`, dov'e' nato: si e'
# spostato con le tabelle che giustifica, invece di restare orfano accanto a
# una funzione che non le contiene piu'.
#
# `supported_features` -- COSA UN'ENTITA' SA FARE -- e' un intero A BIT il
# cui significato dipende dal DOMINIO: Home Assistant lo dichiara come un
# `IntFlag` per ognuno (`LightEntityFeature`, `UpdateEntityFeature`, ...).
# Misurato sull'impianto del proprietario il 06/09/2026: 181 entita' su 834
# lo dichiarano, e prima di questa fetta la conoscenza non lo citava in
# NESSUN punto -- il fornitore dice cosa un'entita' sa fare, e HIRIS lo
# buttava.
#
# CORREZIONE del 06/09/2026, misurata (non dedotta): la prima versione di
# questa tabella copriva gli STESSI domini di
# `proxy/entity_cache.py::_DOMAIN_ATTRS` (una lista fatta per un'ALTRA
# ragione -- quali attributi di STATO mostrare, non quali domini dichiarano
# `supported_features` qui) piu' `weather`. Dedurre da li' era dedurre, non
# misurare -- e la deduzione era sbagliata: contate le 181 entita' vere per
# dominio, la distribuzione e'
#
#     update 53, light 50, button 16, notify 11, camera 9, climate 8,
#     media_player 7, valve 4, siren 4, device_tracker 4, switch 4,
#     todo 4, remote 2, calendar 2, conversation 1, alarm_control_panel 1,
#     weather 1
#
# -- e i quattro domini della prima versione (`cover`, `fan`,
# `water_heater`, `vacuum`) valgono TUTTI zero su questa casa: tabelle
# corrette, ma scelte guardando un elenco sbagliato, non questa casa.
#
# Ogni tabella qui sotto e' verificata sul SORGENTE di Home Assistant, non a
# memoria e non su `dev`: ai DUE estremi della finestra che questo add-on
# dichiara di supportare -- il tag piu' vecchio, `2024.7.0`
# (`hiris/config.yaml: homeassistant`), e `2026.9.1`, il piu' recente
# rilasciato al momento di questa fetta. Un dominio senza i due tag
# verificati resta FUORI: non si inventa una tabella. `button` e' il caso
# concreto: 16 entita' su questa casa dichiarano `supported_features`, ma
# NESSUNA versione del sorgente (verificato `__init__.py` e `const.py` su
# entrambi i tag) definisce un `ButtonEntityFeature` -- il dominio non ha
# bit da decodificare, quindi resta fuori per MANCANZA DI FONTE, non per
# dimenticanza. Lo stesso vale per `automation`.
#
# SECONDA CORREZIONE, stesso giorno: la review indipendente ha confermato le
# dodici tabelle di allora bit per bit (fonte scaricata e confrontata contro
# ogni `*EntityFeature`, zero voci in tabella assenti dalla fonte e zero
# voci di fonte assenti dalla tabella) e ha misurato che CINQUE degli otto
# domini rimasti fuori hanno in realta' una fonte stabile e identica sui due
# tag -- lo stesso lavoro delle altre, semplicemente non ancora fatto:
# `siren`, `todo`, `alarm_control_panel`, `calendar`, `remote`. Verificate
# qui e aggiunte. Un sesto, `conversation`, e' un caso NUOVO e diverso: il
# suo `ConversationEntityFeature` non esiste affatto a `2024.7.0` (nessuna
# classe, verificato su `const.py`) e NASCE prima di `2026.9.1` (`CONTROL =
# 1`) -- non rimosso, non rinominato, NATO dentro la finestra supportata.
# Aggiunto comunque, con la stessa logica dei bit aggiunti piu' sotto: su
# una casa ferma a `2024.7.0` quell'entita' non dichiarerebbe mai
# `supported_features` per cominciare (la property di base torna `None`
# finche' l'integrazione non imposta il bit), quindi non c'e' nessun valore
# vecchio con cui `CONTROL=1` possa confliggere.
#
# Restano fuori per MANCANZA DI FONTE (verificato su entrambi i tag,
# `__init__.py` e `const.py`, nessuna traccia di un `EntityFeature`):
# `button`, `device_tracker`, `switch` -- e `automation`, gia' citato sopra.
# `button` e' quello che il censore continua a nominare, e la sua ragione va
# letta fino in fondo: questa casa dichiara `supported_features: [2]` su
# `button`, ma il bit non viene dal dominio -- viene da `reolink.ptz_move`,
# un servizio di integrazione che BERSAGLIA `button`. Non esiste nessun
# `ButtonEntityFeature` da cui prendere il nome di quel bit, quindi
# decodificarlo vorrebbe dire inventarlo. Resta fuori, e l'eccezione e'
# scritta in `type_census.py`.
#
# COPERTURA IN NUMERI -- TRE fatti diversi, misurati sulla casa vera
# (`/api/states`) il 06/09/2026, non a parole e non confusi l'uno con
# l'altro (il primo giro di questa fetta li aveva confusi: vedi git log):
#
#   181  entita' dichiarano `supported_features` -- il totale.
#   157  (87%) sono in un dominio con una tabella qui sotto: update 53 +
#        light 50 + notify 11 + camera 9 + climate 8 + media_player 7 +
#        valve 4 + siren 4 + todo 4 + remote 2 + calendar 2 +
#        conversation 1 + alarm_control_panel 1 + weather 1 = 157, piu' i
#        quattro a zero entita' qui (`cover`/`fan`/`water_heater`/
#        `vacuum`) che non aggiungono nulla al numeratore.
#   104  producono DAVVERO una `capacita'` non vuota -- non 157: dei 157 in
#        un dominio coperto, 53 hanno `supported_features == 0` (nessun bit
#        acceso: light 44, notify 7, remote 2), quindi 157 - 53 = 104.
#    24  restano fuori per MANCANZA DI FONTE (`button` 16,
#        `device_tracker` 4, `switch` 4) -- tracciate in `docs/BACKLOG.md`.
#
# PERCHE' sono tre numeri e non uno: "dominio coperto" (157) dice se QUESTA
# funzione sa leggere il dominio, "capacita' dette" (104) dice quante
# entita' hanno DAVVERO ricevuto un bit da un'integrazione. Un
# `supported_features == 0` non e' un dato mancante -- e' un'entita' che
# DICHIARA di non saper fare niente di speciale, e la legge di questo
# sprint (una chiave senza niente da dire non esce) lo rispetta lasciando
# `capacita'` assente anche li'. Scambiare 157 con 104 -- o con 181 --
# sarebbe la stessa confusione fra dichiarato e vero che questo sprint
# combatte ovunque altrove; chi legge fra sei mesi deve trovare tutti e tre
# scritti, non doverli dedurre o rimisurare.
#
# Due bit sono ESCLUSI di proposito, perche' il sorgente mostra che il loro
# significato NON regge per l'intera finestra supportata -- rimossi fra i
# due tag, non solo rinominati. **Rilevante per il Task 4** (un vocabolario
# importato che invecchia): e' la prova, misurata e non ipotizzata, che «da
# quale versione viene» un fatto su Home Assistant non e' una formalita' --
# lo stesso bit (64) e' stato rimosso in DUE domini indipendenti fra
# `2024.7.0` e `2026.9.1`:
# - `ClimateEntityFeature.AUX_HEAT` (64): presente a `2024.7.0`
#   (`components/climate/const.py`), sparito a `2026.9.1` (lo stesso file
#   non lo dichiara piu');
# - `VacuumEntityFeature.BATTERY` (64): stessa sorte, stesso file
#   (`components/vacuum/const.py`, prima `__init__.py`).
# Decodificare quei due bit avrebbe affermato un significato che il
# fornitore, per meta' della finestra che HIRIS dichiara di supportare, non
# garantisce piu' -- esattamente il difetto che questo sprint combatte.
#
# I bit aggiunti fra i due tag (`CoverEntityFeature.SPEED`,
# `FanEntityFeature.TURN_ON`/`TURN_OFF`,
# `ClimateEntityFeature.SWING_HORIZONTAL_MODE`,
# `MediaPlayerEntityFeature.SEARCH_MEDIA`, `VacuumEntityFeature.CLEAN_AREA`)
# restano DENTRO: non collidono con nessun valore piu' vecchio dello stesso
# dominio (verificato riga per riga), quindi decodificarli non afferma
# niente di falso su una casa ferma a `2024.7.0` -- semplicemente quel bit
# non vi comparira' mai.

_FEATURE_TABLES: dict[str, dict[int, str]] = {
    # I due domini piu' numerosi su questa casa (53 + 50 = 103/181).
    "update": {
        1: "installazione", 2: "versione_specifica",
        4: "avanzamento_installazione", 8: "backup", 16: "note_di_rilascio",
    },
    "light": {4: "effetti", 8: "flash", 32: "transizione"},
    # `notify`/`camera`: prossimi per numero (11 + 9), verificati alla fonte
    # come gli altri -- non «piccoli quindi meno importanti», solo dopo
    # update/light nell'ordine di quante entita' li usano qui.
    "notify": {1: "titolo"},
    "camera": {1: "accensione", 2: "streaming"},
    "climate": {
        1: "temperatura_target", 2: "intervallo_temperatura",
        4: "umidita_target", 8: "modo_ventola", 16: "preset",
        32: "oscillazione", 128: "spegnimento", 256: "accensione",
        512: "oscillazione_orizzontale",
    },
    "media_player": {
        1: "pausa", 2: "avanzamento", 4: "volume", 8: "muto",
        16: "traccia_precedente", 32: "traccia_successiva", 128: "accensione",
        256: "spegnimento", 512: "riproduzione_media", 1024: "volume_a_passi",
        2048: "selezione_sorgente", 4096: "stop", 8192: "svuota_playlist",
        16384: "play", 32768: "shuffle", 65536: "modo_audio",
        131072: "sfoglia_media", 262144: "ripeti", 524288: "raggruppamento",
        1048576: "annuncio", 2097152: "accoda", 4194304: "ricerca_media",
    },
    # `valve`: 4 entita' su questa casa. `cover`, `fan`, `water_heater`,
    # `vacuum` sotto: ZERO entita' su questa casa (misurato il 06/09/2026) --
    # tabelle verificate e corrette, tenute perche' una casa diversa le avra',
    # ma NON scelte guardando questa: il numero e' scritto qui apposta, cosi'
    # chi legge sa che «zero» e' una misura, non una svista.
    "valve": {1: "apertura", 2: "chiusura", 4: "posizione", 8: "stop"},
    "cover": {  # 0/181 su questa casa, 06/09/2026
        1: "apertura", 2: "chiusura", 4: "posizione", 8: "stop",
        16: "apertura_lamelle", 32: "chiusura_lamelle", 64: "stop_lamelle",
        128: "posizione_lamelle", 256: "velocita",
    },
    "fan": {  # 0/181 su questa casa, 06/09/2026
        1: "velocita", 2: "oscillazione", 4: "direzione", 8: "preset",
        16: "spegnimento", 32: "accensione",
    },
    "water_heater": {  # 0/181 su questa casa, 06/09/2026
        1: "temperatura_target", 2: "modo_operativo", 4: "modo_assenza",
        8: "accensione_spegnimento",
    },
    "vacuum": {  # 0/181 su questa casa, 06/09/2026
        1: "accensione", 2: "spegnimento", 4: "pausa", 8: "stop",
        16: "rientro_alla_base", 32: "velocita_aspirazione",
        128: "stato_dettagliato", 256: "comando_diretto",
        512: "localizzazione", 1024: "pulizia_puntuale", 2048: "mappa",
        4096: "riporta_stato", 8192: "avvio", 16384: "pulizia_area",
    },
    "weather": {  # 1/181 su questa casa, 06/09/2026
        1: "previsioni_giornaliere", 2: "previsioni_orarie",
        4: "previsioni_due_volte_al_giorno",
    },
    # I cinque domini della seconda correzione: fonte stabile e identica sui
    # due tag, stesso lavoro delle otto tabelle sopra.
    "siren": {  # 4/181
        1: "accensione", 2: "spegnimento", 4: "toni", 8: "volume",
        16: "durata",
    },
    "todo": {  # 4/181
        1: "crea_elemento", 2: "elimina_elemento", 4: "aggiorna_elemento",
        8: "sposta_elemento", 16: "scadenza_data", 32: "scadenza_data_ora",
        64: "descrizione_elemento",
    },
    "alarm_control_panel": {  # 1/181
        1: "armato_in_casa", 2: "armato_fuori_casa", 4: "armato_notte",
        8: "allarme", 16: "armato_bypass", 32: "armato_vacanza",
    },
    "calendar": {  # 2/181
        1: "crea_evento", 2: "elimina_evento", 4: "aggiorna_evento",
    },
    "remote": {  # 2/181
        1: "apprendimento_comando", 2: "elimina_comando", 4: "attivita",
    },
    # `conversation`: caso NUOVO, non nella misura degli otto domini fuori --
    # `ConversationEntityFeature` non esiste a `2024.7.0`, nasce prima di
    # `2026.9.1` (`CONTROL = 1`). Su una casa ferma a `2024.7.0` quell'entita'
    # non dichiarerebbe mai `supported_features` per cominciare, quindi non
    # c'e' nessun valore vecchio con cui `CONTROL=1` possa confliggere.
    "conversation": {1: "controllo"},  # 1/181
    # I QUATTRO domini della fetta del censore (08/09/2026). Non sono arrivati
    # da una lettura del sorgente fatta per hobby: li ha NOMINATI il censore,
    # confrontando i bit che questa casa dichiara nel registro dei servizi con
    # i domini che avevano una tabella. Erano cinque; il quinto (`button`)
    # resta fuori, e la sua ragione e' scritta piu' sotto.
    #
    # Zero entita' di questi domini su questa casa -- come `cover`, `fan`,
    # `water_heater` e `vacuum` qui sopra: il numero e' scritto apposta perche'
    # chi legge sappia che «zero» e' una misura, non una svista. Cio' che NON
    # e' zero e' il registro dei servizi: Home Assistant dichiara quei bit
    # anche senza un'entita' che li porti, ed e' da li' che il censore li vede.
    "lock": {1: "apertura"},  # LockEntityFeature.OPEN, identica ai due tag
    "humidifier": {1: "modi"},  # HumidifierEntityFeature.MODES, identica ai due tag
    "lawn_mower": {  # LawnMowerEntityFeature, identica ai due tag
        1: "avvio_taglio", 2: "pausa", 4: "rientro_alla_base",
    },
    # `assist_satellite`: caso NUOVO, lo stesso di `conversation` qui sopra --
    # il componente non esiste affatto a `2024.7.0` (verificato: ne'
    # `const.py` ne' `__init__.py`, 404 su entrambi), e nasce prima di
    # `2026.9.1`. Su una casa ferma al tag vecchio non esiste nessuna entita'
    # di questo dominio, quindi non c'e' nessun valore vecchio con cui questi
    # due bit possano confliggere.
    "assist_satellite": {1: "annuncio", 2: "avvio_conversazione"},
}

for _domain, _bits in _FEATURE_TABLES.items():
    _table = Imported(_bits, ha_version=FEATURE_SOURCE_HA_VERSION,
                      source=FEATURE_SOURCE)
    if _vocabulary.row(_domain) is None:
        _vocabulary.add(_domain, capability_names=_table)
    else:
        # Il dominio ha gia' una riga (`light`, `climate`, `cover`, ...): la
        # capacita' e' un campo IN PIU' sulla stessa riga, non una riga nuova
        # accanto. E' la fondamenta 2 applicata al vocabolario stessa.
        _vocabulary.extend(_domain, capability_names=_table)

del _domain, _bits, _table


# -- metrica 4: quali attributi dicono cosa puo' fare, e quali com'e' adesso -
#
# **La separazione e' di Home Assistant, non nostra, e non c'era niente da
# inventare.** `Entity` tiene le due meta' separate e le fonde in un
# dizionario piatto solo all'ultimo momento, quando scrive lo stato:
#
#   helpers/entity.py:787-794   `capability_attributes`  -- «Attributes that
#                                explain the capabilities of an entity»
#   helpers/entity.py:810-828   `state_attributes` / `extra_state_attributes`
#   helpers/entity.py:1109-1124 `attr = capability_attr.copy()`, poi
#                               `if available:` prima di fondere le altre due
#
# Da quelle righe discendono i tre fatti che questa metrica esiste per
# conservare, e nessuno dei tre e' un'opinione:
#
# 1. **«Attributo» e' UNA parola per DUE cose**, e la fusione avviene sul filo.
#    Il difetto ricorrente di questa codebase -- due cose diverse dette con una
#    parola sola -- qui NON nasce in HIRIS: nasce in Home Assistant, e HIRIS lo
#    ereditava intero. Si separa alla fonte, cioe' in `entity_cache._to_minimal`,
#    che e' il punto in cui un payload grezzo diventa cio' che ogni lettore vede.
# 2. **Le capacita' sopravvivono all'indisponibilita'.** `state_attributes` ed
#    `extra_state_attributes` entrano SOLO `if available`; le capacita' no. Una
#    lampadina staccata dice ancora cosa saprebbe fare.
# 3. **La meta' «valore corrente» e' APERTA per costruzione.**
#    `extra_state_attributes` e', testualmente, «Implemented by platform
#    classes»: qualunque integrazione ci mette dentro quello che vuole. Una
#    lista di AMMESSI su quella meta' non potra' mai essere completa -- ed e'
#    esattamente il modo in cui `proxy/entity_cache._DOMAIN_ATTRS` era nata
#    sbagliata (nove domini su trenta, e per quei nove i soli valori correnti).
#
# **Quindi le due tabelle qui sotto NON sono una lista di ammessi**: nessun
# attributo viene buttato perche' non compare qui. Sono un DIZIONARIO -- dicono
# di quali nomi Home Assistant pubblica il significato. Cio' che non e' in
# nessuna delle due esce lo stesso, sotto l'etichetta dei NON INTERPRETATI:
# «non so cosa sia» e «so cosa sia» sono due fatti diversi, e nessuno dei due
# e' «non esiste».
#
# Trascritte dal sorgente vero al tag `2026.9.1` -- lo stesso che la casa
# esegue, mai `dev` -- scaricando ogni `components/<dominio>/const.py` e
# leggendo le classi `StrEnum` che HA dedica alla distinzione. La prova che
# riporta ogni riga alla fonte, e che fallisce quando divergono, e'
# `tests/test_attribute_tables_pinned_to_source.py`, che riscrive gli elenchi
# a mano invece di importarli da qui: una mutazione di questa tabella non deve
# poter muovere anche il proprio metro.
#
# DUE SCADENZE GIA' NOTE, scritte accanto alle righe invece che scoperte fra un
# anno: `climate.temperature` e' deprecata in favore di `TARGET_TEMPERATURE`
# con rimozione annunciata per `2027.2.0` (`components/climate/const.py:159-166`),
# e `water_heater.temperature` per `2027.3.0` (`components/water_heater/const.py:19-26`).
# I due nomi restano qui perche' a `2026.9.1` sono ancora quelli che arrivano
# nel payload; il giorno in cui spariscono, la prova pinnata lo dice.

CAPABILITY_ATTRIBUTE_SOURCE_HA_VERSION = "2026.9.1"

CAPABILITY_ATTRIBUTE_SOURCE = (
    "home-assistant/core, tag 2026.9.1 -- "
    "homeassistant/components/<dominio>/const.py, classi "
    "`<Dominio>EntityCapabilityAttribute` e `<Dominio>EntityStateAttribute` "
    "(`WaterHeaterCapabilityAttribute`/`WaterHeaterStateAttribute` senza "
    "`Entity` nel nome, `ScannerEntityStateAttribute`/`TrackerEntityStateAttribute` "
    "accanto a quella di `device_tracker`), piu' homeassistant/const.py:464-483 "
    "per le due classi valide su OGNI entita'. Scaricate al tag, mai su `dev`."
)

#: Le capacita' di QUALUNQUE entita': `homeassistant/const.py:464-467`,
#: `EntityCapabilityAttribute`. Una sola voce, ed e' il gruppo.
UNIVERSAL_CAPABILITY_ATTRIBUTES = Imported(
    {"group_entities"},
    ha_version=CAPABILITY_ATTRIBUTE_SOURCE_HA_VERSION,
    source=CAPABILITY_ATTRIBUTE_SOURCE)

#: Il giudizio nostro accanto alla trascrizione, e non dentro di essa: a
#: `2026.9.1` un gruppo esce ancora sotto `entity_id`, la forma vecchia, e
#: `components/group/entity.py:43-45` le nomina ENTRAMBE nello stesso insieme
#: (`_unrecorded_attributes = frozenset({ATTR_ENTITY_ID,
#: EntityCapabilityAttribute.GROUP_ENTITIES})`). Misurato sulla casa vera il
#: 07/09/2026: `light.lampadario_sala_da_pranzo` porta `entity_id`, non
#: `group_entities`. Una tabella costruita solo dagli enum nuovi perderebbe
#: quel gruppo IN SILENZIO.
UNIVERSAL_CAPABILITY_ATTRIBUTES_ADDED = Ours({
    "entity_id": (
        "la forma vecchia di `group_entities`, che a 2026.9.1 e' ancora quella "
        "che arriva davvero: `components/group/entity.py:43-45` nomina "
        "entrambe, e sulla casa vera il gruppo esce solo sotto questo nome"),
})

#: Gli attributi di stato di QUALUNQUE entita': `homeassistant/const.py:470-483`,
#: `EntityStateAttribute`.
UNIVERSAL_STATE_ATTRIBUTES = Imported(
    {"assumed_state", "attribution", "device_class", "entity_picture",
     "friendly_name", "icon", "latitude", "longitude", "restored",
     "supported_features", "unit_of_measurement"},
    ha_version=CAPABILITY_ATTRIBUTE_SOURCE_HA_VERSION,
    source=CAPABILITY_ATTRIBUTE_SOURCE)


_CAPABILITY_ATTRIBUTE_TABLES: dict[str, frozenset[str]] = {
    "automation": frozenset({"id"}),
    "climate": frozenset({
        "hvac_modes", "min_temp", "max_temp", "target_temp_step",
        "min_humidity", "max_humidity", "target_humidity_step", "fan_modes",
        "preset_modes", "swing_modes", "swing_horizontal_modes"}),
    "cover": frozenset({"supported_speeds"}),
    "device_tracker": frozenset({"tracking_type"}),
    "event": frozenset({"event_types"}),
    "fan": frozenset({"preset_modes"}),
    "humidifier": frozenset({
        "min_humidity", "max_humidity", "target_humidity_step",
        "available_modes"}),
    "light": frozenset({
        "min_color_temp_kelvin", "max_color_temp_kelvin", "effect_list",
        "supported_color_modes"}),
    "media_player": frozenset({"source_list", "sound_mode_list"}),
    # `mode` e' nella fonte, ed esce per giudizio nostro: vedi
    # `_CAPABILITY_ATTRIBUTES_DROPPED` sotto.
    "number": frozenset({"min", "max", "step", "mode"}),
    "select": frozenset({"options"}),
    "sensor": frozenset({"state_class", "options"}),
    "siren": frozenset({"available_tones"}),
    "text": frozenset({"mode", "min", "max", "pattern"}),
    "vacuum": frozenset({"fan_speed_list"}),
    "water_heater": frozenset({
        "min_temp", "max_temp", "target_temp_step", "operation_list"}),
}


# I DUE GIUDIZI NOSTRI, dichiarati come nostri e non nascosti nella
# trascrizione. Sono la ragione per cui le tabelle importate sopra restano
# fedeli alla fonte riga per riga -- se avessi tolto `number.mode` di la', la
# prova pinnata avrebbe dovuto mentire con me.
#
# `number.mode` ESCE, contro la classificazione di Home Assistant, con DUE
# fonti indipendenti che dicono la stessa cosa:
#   - la documentazione: «Defines how the number should be displayed in the
#     UI» (`docs/core/entity/number.md:17`);
#   - la casa stessa, che ne traduce i valori in `Automatico`/`Input field`/
#     `Cursore` (`frontend/get_translations`, `entity_component`, misurato il
#     07/09/2026).
# E' resa grafica, non campo di manovra. Resta comunque un attributo
# DICHIARATO -- passa fra i valori correnti, non fra i non interpretati:
# scavalcare HA sulla presentazione non ci autorizza a dire che non sappiamo
# cosa sia.
#
# `alarm_control_panel.code_format`/`code_arm_required` restano invece fra i
# valori, SEGUENDO Home Assistant (`components/alarm_control_panel/const.py`,
# `AlarmControlPanelEntityStateAttribute`) anche se funzionalmente sono limiti
# («serve un codice per inserire?») che non cambiano mai. Stessa forma del
# caso sopra, esito opposto, e la differenza e' la sola che conta: li' avevo
# due fonti indipendenti contro HA, qui non ne ho nessuna. **Il fornitore
# comanda sulla classificazione finche' non e' smentito da una fonte, non
# finche' non e' smentito dal mio senso.**
_CAPABILITY_ATTRIBUTES_DROPPED: dict[str, dict[str, str]] = {
    "number": {
        "mode": (
            "resa grafica, non campo di manovra: «Defines how the number "
            "should be displayed in the UI» (docs/core/entity/number.md:17), e "
            "la casa ne traduce i valori in Automatico/Input field/Cursore"),
    },
    "text": {
        "mode": (
            "stessa ragione di `number.mode`: `TextMode` vale `text`/`password` "
            "e dice come DISEGNARE il controllo, non cosa l'entita' accetta -- "
            "il campo di manovra di un `text` sono `min`/`max`/`pattern`"),
    },
}


# «COSA PUO' ASSUMERE» NON E' «COSA LE SI PUO' IMPORRE» -- il terzo giudizio
# nostro, e il piu' pericoloso dei tre perche' il nome non lo tradisce.
#
# `SensorEntityCapabilityAttribute.OPTIONS` e
# `SelectEntityCapabilityAttribute.OPTIONS` si chiamano tutti e due `options`,
# Home Assistant li classifica tutti e due come capacita', e finche' li si
# legge sono davvero la stessa sfumatura. **Per chi comanda non lo sono
# affatto**: su un `select` quei valori si impongono
# (`select.select_option`), su un `sensor` descrivono soltanto cosa lo `state`
# potra' valere -- e un sensore non si comanda, non esiste nessun servizio che
# gli imponga niente.
#
# Si separa QUI, alla fonte, e non a valle: chi legge la cesta del campo di
# manovra non deve sapere che su un dominio quella parola significa un'altra
# cosa. La cesta e' un'altra (`entity_cache.ASSUMABLE`), il nome che il
# modello legge e' un altro, e la trascrizione importata resta intatta -- come
# per `_CAPABILITY_ATTRIBUTES_DROPPED`, il giudizio sta accanto alla fonte,
# mai dentro.
#
# **Due voci e non una, perche' una regola applicata a un caso solo non e' una
# regola** (la stessa lezione di `text.mode` accanto a `number.mode`). Il
# criterio e' scritto e verificabile: sono i domini che **nessun servizio
# comanda** -- `sensor` ha il solo `sensor.set_display_precision`, che tocca
# la resa e non lo stato, e `event` non ha nessun servizio affatto (misurato
# su `/api/services` di questa casa, 07/09/2026). Cio' che li' si chiama
# «capacita'» non e' un campo di manovra: e' l'elenco di cio' che si potra'
# leggere.
_ASSUMABLE_ATTRIBUTES: dict[str, dict[str, str]] = {
    "event": {
        "event_types": (
            "i tipi di evento che questa entita' potra' RIPORTARE, non quelli "
            "che le si possono chiedere: il dominio `event` non ha nessun "
            "servizio, quindi non c'e' niente da imporgli"),
    },
    "sensor": {
        "options": (
            "i valori che lo STATO di questo sensore puo' assumere, non quelli "
            "che gli si possono imporre -- un sensore non si comanda. Stesso "
            "nome di `select.options`, che invece si impone davvero con "
            "`select.select_option`: e' la stessa parola per due domande, e "
            "per chi comanda e' la differenza fra un'azione possibile e una "
            "impossibile"),
    },
}


# I LIMITI VERI SONO QUELLI DELL'ENTITA', NON QUELLI DEL SELETTORE.
#
# Misurato il 07/09/2026: il selettore che Home Assistant pubblica per
# `light.turn_on.color_temp_kelvin` dichiara **2000-6500 K**, e
# `light.alberello` dichiara `min_color_temp_kelvin: 1500`,
# `max_color_temp_kelvin: 9000`. **Vince l'entita'**: il selettore descrive il
# campo di un cursore generico -- lo stesso per ogni lampadina della casa --
# non il dispositivo. Chi si fermasse al selettore negherebbe una temperatura
# che quella lampadina sa fare davvero.
#
# Questa tabella dice, per un parametro di servizio, QUALE attributo
# dell'entita' porta il limite vero. Due forme sole:
#
# - `{"min": ..., "max": ...}` -- un intervallo (`color_temp_kelvin`,
#   `temperature`, `humidity`, `value`);
# - `{"options": ...}` -- un elenco di valori legali (`effect`, `hvac_mode`,
#   `option`, `source`).
#
# **Non e' una lista di nomi inventati, ed e' cio' che la rende sorvegliabile**:
# ogni attributo nominato qui dev'essere una capacita' DICHIARATA da Home
# Assistant per quel dominio (`_CAPABILITY_ATTRIBUTE_TABLES`), e una prova lo
# verifica riga per riga. Un refuso non diventa un limite che non esiste: fa
# arrossire.
#
# Provenienza `nostro` e non `importato`: HA pubblica gli attributi e pubblica
# i selettori, ma non pubblica da nessuna parte QUALE attributo corrisponda a
# quale parametro -- lo sa il codice del dominio, che clampa, e lo sa il
# frontend, che riempie il cursore. Il collegamento e' un giudizio, e sta qui
# dichiarato come tale.
_PARAMETER_LIMITS: dict[str, dict[str, dict[str, str]]] = {
    "climate": {
        "temperature": {"min": "min_temp", "max": "max_temp"},
        "target_temp_high": {"min": "min_temp", "max": "max_temp"},
        "target_temp_low": {"min": "min_temp", "max": "max_temp"},
        "humidity": {"min": "min_humidity", "max": "max_humidity"},
        "hvac_mode": {"options": "hvac_modes"},
        "fan_mode": {"options": "fan_modes"},
        "preset_mode": {"options": "preset_modes"},
        "swing_mode": {"options": "swing_modes"},
        "swing_horizontal_mode": {"options": "swing_horizontal_modes"},
    },
    "fan": {
        "preset_mode": {"options": "preset_modes"},
    },
    "humidifier": {
        "humidity": {"min": "min_humidity", "max": "max_humidity"},
        "mode": {"options": "available_modes"},
    },
    "light": {
        "color_temp_kelvin": {"min": "min_color_temp_kelvin",
                              "max": "max_color_temp_kelvin"},
        "kelvin": {"min": "min_color_temp_kelvin",
                   "max": "max_color_temp_kelvin"},
        "effect": {"options": "effect_list"},
    },
    "media_player": {
        "source": {"options": "source_list"},
        "sound_mode": {"options": "sound_mode_list"},
    },
    "number": {
        "value": {"min": "min", "max": "max"},
    },
    "select": {
        "option": {"options": "options"},
    },
    "siren": {
        "tone": {"options": "available_tones"},
    },
    "vacuum": {
        "fan_speed": {"options": "fan_speed_list"},
    },
    "water_heater": {
        "temperature": {"min": "min_temp", "max": "max_temp"},
        "operation_mode": {"options": "operation_list"},
    },
}


_STATE_ATTRIBUTE_TABLES: dict[str, frozenset[str]] = {
    "alarm_control_panel": frozenset({
        "code_format", "changed_by", "code_arm_required"}),
    "automation": frozenset({"last_triggered", "mode", "current", "max"}),
    "calendar": frozenset({
        "message", "all_day", "start_time", "end_time", "location",
        "description"}),
    "camera": frozenset({
        "access_token", "model_name", "brand", "motion_detection"}),
    # `temperature` deprecata verso `TARGET_TEMPERATURE`, rimozione 2027.2.0.
    "climate": frozenset({
        "current_temperature", "temperature", "target_temp_high",
        "target_temp_low", "current_humidity", "humidity", "fan_mode",
        "hvac_action", "preset_mode", "swing_mode", "swing_horizontal_mode"}),
    "cover": frozenset({"is_closed", "current_position", "current_tilt_position"}),
    # Tre classi per un dominio solo: `DeviceTrackerEntityStateAttribute`,
    # `ScannerEntityStateAttribute` (ip/mac/host_name) e
    # `TrackerEntityStateAttribute` (le tre di posizione, in migrazione verso
    # `EntityStateAttribute`, `components/device_tracker/const.py:57-60`).
    "device_tracker": frozenset({
        "source_type", "in_zones", "ip", "mac", "host_name", "latitude",
        "longitude", "gps_accuracy"}),
    "event": frozenset({"event_type"}),
    "fan": frozenset({
        "direction", "oscillating", "percentage", "percentage_step",
        "preset_mode"}),
    "humidifier": frozenset({"action", "current_humidity", "humidity", "mode"}),
    "image": frozenset({"access_token"}),
    "input_boolean": frozenset({"editable"}),
    "input_number": frozenset({"initial", "editable"}),
    "input_select": frozenset({"editable"}),
    "input_text": frozenset({"editable"}),
    "light": frozenset({
        "effect", "color_mode", "brightness", "color_temp_kelvin", "hs_color",
        "rgb_color", "xy_color", "rgbw_color", "rgbww_color"}),
    "lock": frozenset({"changed_by", "code_format"}),
    "media_player": frozenset({
        "volume_level", "is_volume_muted", "media_content_id",
        "media_content_type", "media_duration", "media_position",
        "media_position_updated_at", "media_title", "media_artist",
        "media_album_name", "media_album_artist", "media_track",
        "media_series_title", "media_season", "media_episode", "media_channel",
        "media_playlist", "app_id", "app_name", "source", "sound_mode",
        "shuffle", "repeat", "group_members", "entity_picture_local"}),
    "person": frozenset({
        "editable", "id", "device_trackers", "in_zones", "gps_accuracy",
        "source", "user_id"}),
    "remote": frozenset({"activity_list", "current_activity"}),
    # `script` non ha una classe `StrEnum`: i cinque nomi si leggono dove li
    # scrive, `components/script/__init__.py:591-604`, e vengono da
    # `components/script/const.py:7-8` (`last_action`, `last_triggered`),
    # `helpers/script.py:135-136` (`current`, `max`) e
    # `homeassistant/const.py:388` (`mode`).
    "script": frozenset({"last_action", "last_triggered", "mode", "current", "max"}),
    "sensor": frozenset({"last_reset"}),
    # `sun` nemmeno: nove costanti `STATE_ATTR_*` in
    # `components/sun/const.py:35-43`. Sono DICHIARATE, e questo basta -- che
    # la forma sia un enum o una costante non cambia chi le pubblica.
    "sun": frozenset({
        "azimuth", "elevation", "rising", "next_dawn", "next_dusk",
        "next_midnight", "next_noon", "next_rising", "next_setting"}),
    "tag": frozenset({"tag_id", "last_scanned_by_device_id"}),
    "update": frozenset({
        "auto_update", "display_precision", "installed_version", "in_progress",
        "latest_version", "release_summary", "release_url", "skipped_version",
        "title", "update_percentage"}),
    "vacuum": frozenset({"fan_speed"}),
    "valve": frozenset({"is_closed", "current_position"}),
    "water_heater": frozenset({
        "current_temperature", "temperature", "target_temp_high",
        "target_temp_low", "operation_mode", "away_mode"}),
    "weather": frozenset({
        "temperature", "apparent_temperature", "dew_point", "temperature_unit",
        "humidity", "ozone", "cloud_coverage", "uv_index", "pressure",
        "pressure_unit", "wind_bearing", "wind_gust_speed", "wind_speed",
        "wind_speed_unit", "visibility", "visibility_unit",
        "precipitation_unit"}),
    "zone": frozenset({"radius", "passive", "persons", "editable"}),
}


for _domain in sorted(set(_CAPABILITY_ATTRIBUTE_TABLES)
                      | set(_STATE_ATTRIBUTE_TABLES)
                      | set(_ASSUMABLE_ATTRIBUTES) | set(_PARAMETER_LIMITS)):
    _new_fields: dict[str, Field] = {}
    if _domain in _CAPABILITY_ATTRIBUTE_TABLES:
        _new_fields[CAPABILITY_ATTRIBUTES] = Imported(
            _CAPABILITY_ATTRIBUTE_TABLES[_domain],
            ha_version=CAPABILITY_ATTRIBUTE_SOURCE_HA_VERSION,
            source=CAPABILITY_ATTRIBUTE_SOURCE)
    if _domain in _STATE_ATTRIBUTE_TABLES:
        _new_fields[STATE_ATTRIBUTES] = Imported(
            _STATE_ATTRIBUTE_TABLES[_domain],
            ha_version=CAPABILITY_ATTRIBUTE_SOURCE_HA_VERSION,
            source=CAPABILITY_ATTRIBUTE_SOURCE)
    if _domain in _CAPABILITY_ATTRIBUTES_DROPPED:
        _new_fields[CAPABILITY_ATTRIBUTES_DROPPED] = Ours(
            _CAPABILITY_ATTRIBUTES_DROPPED[_domain])
    if _domain in _ASSUMABLE_ATTRIBUTES:
        _new_fields[ASSUMABLE_ATTRIBUTES] = Ours(_ASSUMABLE_ATTRIBUTES[_domain])
    if _domain in _PARAMETER_LIMITS:
        _new_fields[PARAMETER_LIMITS] = Ours(_PARAMETER_LIMITS[_domain])
    if _vocabulary.row(_domain) is None:
        _vocabulary.add(_domain, **_new_fields)
    else:
        _vocabulary.extend(_domain, **_new_fields)

del _domain, _new_fields


# --------------------------------------------------------------------------
# LE TRE METRICHE, in forma di domanda
# --------------------------------------------------------------------------

def _text(value) -> str:
    """Un attributo di Home Assistant -> stringa confrontabile.

    Gli attributi arrivano da fuori: possono mancare, essere `None`, o avere un
    tipo inatteso. Un'eccezione qui fermerebbe l'osservatore su un evento solo,
    e l'osservatore gira per sempre.
    """
    return value.strip() if isinstance(value, str) else ""


def aspect_of(entity_id, attributes) -> str | None:
    """**Metrica 1** -- a quale gamba dell'obiettivo serve questa entita', o
    `None`.

    L'obiettivo e' «ottimizzare la casa e renderla confortevole», e ha tre
    gambe -- efficiente, confortevole, in buono stato -- che qui diventano sei
    domande: chi c'e', che aria si respira, cosa disperde, quanta energia si
    muove, cosa si sta rompendo, cosa minaccia la sicurezza.

    **«Quanta energia si muove» e non «cosa consuma»** (correzione del
    26/08/2026): questa gamba cattura energia PRODOTTA e PRELEVATA nella stessa
    classe HA, e «consuma» affermerebbe il contrario per una buona meta' dei 15
    sensori che un fotovoltaico con accumulo porta qui.

    La coppia vince sul dominio, e la guardia -- dove c'e' -- vale sull'una come
    sull'altro: e' la riga a dire a quale condizione il suo giudizio tiene, non
    il codice che la legge.
    """
    attributes = attributes if isinstance(attributes, dict) else {}
    domain = str(entity_id).split(".")[0]
    device_class = _text(attributes.get("device_class"))
    aspect = _vocabulary.value(domain, device_class, ASPECT)
    if aspect is None:
        return None
    guard = _vocabulary.value(domain, device_class, ASPECT_GUARD)
    if guard is not None:
        attribute_name, expected = guard
        if _text(attributes.get(attribute_name)) != expected:
            return None
    return aspect


def is_operable(domain: str) -> bool:
    """**Metrica 2, prima meta'** -- se questo tipo «funziona»: si accende e si
    spegne, si apre e si chiude. Sono i protagonisti degli oggetti di
    funzionamento."""
    return bool(_vocabulary.value(domain, None, OPERABLE, False))


def operable_domains() -> frozenset[str]:
    """I domini accendibili. Scritto una volta perche' una prova possa
    contarli: `_OPERABLE` ne elencava dieci di cui il pavimento ne ammetteva
    due, e le due metriche sono diverse -- il vocabolario le tiene distinte invece
    di far coincidere per sbaglio l'una con l'altra."""
    return frozenset(domain for domain in _vocabulary.domains()
                     if is_operable(domain))


def resting_states_of(domain: str, device_class: str | None = None) -> frozenset[str]:
    """Gli stati che chiudono un episodio di QUESTO tipo, piu' le due forme
    dell'assenza di stato che valgono per tutti.

    Una coppia che non ne dichiara di suoi eredita quelli del dominio: e' il
    collegamento per identificatore, non una copia rimasta indietro.
    """
    own = _vocabulary.value(domain, device_class, RESTING_STATES, frozenset())
    return frozenset(own) | ABSENT_STATE_FORMS.value


def resting_states() -> frozenset[str]:
    """**Metrica 2, seconda meta'** -- l'unione di tutti i riposi dichiarati.

    **Un solo insieme, non due che si sovrappongono**: e' letto da piu' rami
    (funzionamento e sicurezza). Non e' un insieme esclusivo per tipo in senso
    stretto -- `idle` chiude sia il vacuum sia il media_player -- ma resta
    senza ambiguita': ogni valore ha lo stesso significato («questo episodio e'
    finito») in qualunque tipo compaia. Cio' che il vocabolario aggiunge e' che
    ogni valore ha ora un tipo che lo RIVENDICA, invece di stare in un elenco
    piatto di cui nessuno sa piu' chi vi abbia aggiunto cosa.

    **`unavailable`/`unknown` NON stanno qui**: vedi `unknown_states`.
    """
    states = set(ABSENT_STATE_FORMS.value)
    for row in _vocabulary.rows():
        field = row.fields.get(RESTING_STATES)
        if field is not None:
            states |= set(field.value)
    return frozenset(states)


def working_states_of(domain: str, device_class: str | None = None) -> frozenset[str]:
    """Gli stati che, per QUESTO tipo, valgono «sta funzionando».

    L'altra meta' della metrica 2. Non cambia il comportamento di nessun
    lettore -- `_is_on` risponde gia' per esclusione dai riposi -- e serve a
    una cosa sola, che nessun'altra riga sa dire: **distinguere una decisione
    da un silenzio**. Un tipo che non ne dichiara nessuno non e' un tipo i cui
    stati sono tutti riposi: e' un tipo che nessuno ha ancora guardato, ed e'
    esattamente cio' che il censore deve poter nominare.

    Come per i riposi, una coppia che non ne dichiara di suoi eredita quelli
    del dominio: si collega, non copia.
    """
    own = _vocabulary.value(domain, device_class, WORKING_STATES, {})
    return frozenset(own)


def declared_working_states() -> Mapping[str, Mapping[str, str]]:
    """Dominio -> `stato -> ragione`, per la prova che boccia un giudizio
    senza ragione scritta. Stessa forma di `dropped_capability_attributes`."""
    return MappingProxyType({
        domain: _vocabulary.value(domain, None, WORKING_STATES)
        for domain in sorted(_vocabulary.domains())
        if _vocabulary.value(domain, None, WORKING_STATES) is not None})


def unknown_states() -> frozenset[str]:
    """Gli stati «non lo so»: non un riposo, non un fatto sulla casa. Una riga
    con questo stato si salta, e l'episodio in corso resta aperto attraverso il
    buco -- che e' la verita', non sappiamo che sia finito."""
    return UNKNOWN_STATES.value


def capability_names(domain: str) -> Mapping[int, str] | None:
    """**Metrica 3** -- i nomi dei bit di `supported_features` per questo
    dominio, o `None` se non ne abbiamo una tabella verificata alla fonte.

    `None` e non un dizionario vuoto: «non lo so» e «so che non ne ha» sono due
    fatti diversi, e questo vocabolario oggi puo' dire solo il primo.
    """
    return _vocabulary.value(domain, None, CAPABILITY_NAMES)


def declared_domains() -> frozenset[str]:
    """I domini per cui questo vocabolario ha una riga -- qualunque cosa quella
    riga dica.

    Serve al censore (`type_census.py`): «rivendicato» non vuol dire «giudicato
    bene», vuol dire che questo vocabolario quel dominio l'ha guardato. Chi
    vuole sapere COSA ne dice chiede il campo, non questa vista.
    """
    return _vocabulary.domains()


def declared_pairs() -> frozenset[tuple[str, str]]:
    """Le coppie (dominio, classe) per cui questo vocabolario ha una riga."""
    return _vocabulary.pairs()


def capability_tables() -> Mapping[str, Mapping[int, str]]:
    """Tutte le tabelle dei bit, per la prova che le riporta alla fonte. Non un
    secondo elenco: una vista sulle righe che gia' le portano."""
    return MappingProxyType({
        domain: _vocabulary.value(domain, None, CAPABILITY_NAMES)
        for domain in sorted(_vocabulary.domains())
        if _vocabulary.value(domain, None, CAPABILITY_NAMES) is not None})


def capability_attributes(domain: str) -> frozenset[str]:
    """**Metrica 4, prima meta'** -- i nomi degli attributi che, per questo
    dominio, dicono COSA L'ENTITA' PUO' FARE.

    Le voci valide su ogni entita' (`group_entities`, piu' la forma vecchia
    `entity_id` che il giudizio nostro aggiunge) ci sono sempre: un gruppo e'
    un gruppo su qualunque dominio, e senza di loro la casa perderebbe il
    gruppo di luci in silenzio.

    Un insieme vuoto NON e' un'assenza di risposta: la maggior parte dei
    domini -- `switch`, `button`, `binary_sensor`, `camera`, `update`... --
    non ha capacita' dichiarate affatto, e lo si e' verificato file per file
    al tag (l'assenza dell'enum, non l'assenza del file). Cio' che quei domini
    sanno fare viaggia in `supported_features`, che ha la sua metrica.
    """
    own = _vocabulary.value(domain, None, CAPABILITY_ATTRIBUTES, frozenset())
    dropped = _vocabulary.value(domain, None, CAPABILITY_ATTRIBUTES_DROPPED, {})
    return ((frozenset(own) - frozenset(dropped) - assumable_attributes(domain))
            | UNIVERSAL_CAPABILITY_ATTRIBUTES.value
            | frozenset(UNIVERSAL_CAPABILITY_ATTRIBUTES_ADDED.value))


def assumable_attributes(domain: str) -> frozenset[str]:
    """**Metrica 4, terza meta'** -- i nomi degli attributi che, per questo
    dominio, dicono cosa l'entita' puo' ASSUMERE: non un campo di manovra, ma
    l'elenco di cio' che si potra' leggere.

    Non e' una sfumatura di `capability_attributes`, e' il suo opposto per chi
    comanda: `sensor.options` e `select.options` hanno lo stesso nome e sono
    la differenza fra un'azione possibile e una impossibile. Vedi
    `_ASSUMABLE_ATTRIBUTES` per la ragione, scritta voce per voce.
    """
    return frozenset(_vocabulary.value(domain, None, ASSUMABLE_ATTRIBUTES, {}))


def declared_assumable_attributes() -> Mapping[str, Mapping[str, str]]:
    """Gli attributi che Home Assistant chiama capacita' e che qui dicono
    «cosa puo' assumere», **con la ragione scritta di ognuno**. Un'eccezione
    senza ragione non passa la prova che legge questa vista."""
    return MappingProxyType({
        domain: _vocabulary.value(domain, None, ASSUMABLE_ATTRIBUTES)
        for domain in sorted(_vocabulary.domains())
        if _vocabulary.value(domain, None, ASSUMABLE_ATTRIBUTES) is not None})


def parameter_limits(domain: str, parameter: str) -> Mapping[str, str] | None:
    """**Metrica 5** -- quale attributo di QUESTA entita' porta il limite vero
    di un parametro di servizio, o `None` se non lo sappiamo.

    Due forme sole: `{"min": ..., "max": ...}` per un intervallo,
    `{"options": ...}` per un elenco di valori legali. Vedi
    `_PARAMETER_LIMITS`: **vince l'entita' sul selettore**, e il selettore
    generico di `light.turn_on.color_temp_kelvin` (2000-6500 K) contro
    l'Alberello (1500-9000 K) e' la misura che lo dice.

    `None` e non un dizionario vuoto: «non lo so» e «so che non ne ha» sono
    due fatti diversi, e su cio' che non si sa non si restringe niente.
    """
    per_domain = _vocabulary.value(domain, None, PARAMETER_LIMITS)
    if per_domain is None:
        return None
    return per_domain.get(parameter)


def declared_parameter_limits() -> Mapping[str, Mapping[str, Mapping[str, str]]]:
    """Tutti i collegamenti parametro -> attributo, per la prova che verifica
    che ogni attributo nominato sia una capacita' DICHIARATA da Home Assistant
    per quel dominio. Un refuso non diventa un limite che non esiste."""
    return MappingProxyType({
        domain: _vocabulary.value(domain, None, PARAMETER_LIMITS)
        for domain in sorted(_vocabulary.domains())
        if _vocabulary.value(domain, None, PARAMETER_LIMITS) is not None})


def state_attributes(domain: str) -> frozenset[str]:
    """**Metrica 4, seconda meta'** -- i nomi degli attributi che, per questo
    dominio, dicono COM'E' ADESSO.

    **Non e' una lista di ammessi, ed e' la differenza che regge tutto il
    disegno**: `extra_state_attributes` e' aperta per costruzione
    (`helpers/entity.py:820-828`, «Implemented by platform classes»), quindi
    un elenco completo di cio' che un'integrazione puo' mandare non esiste e
    non esistera' mai. Questo insieme dice solo di quali nomi Home Assistant
    PUBBLICA il significato; cio' che ne resta fuori non viene buttato --
    viene etichettato come non interpretato.

    Gli attributi tolti dalle capacita' per giudizio nostro rientrano da qui:
    `number.mode` non e' un campo di manovra, ma resta un attributo che HA
    dichiara, e dirne «non so cosa sia» sarebbe falso.
    """
    own = _vocabulary.value(domain, None, STATE_ATTRIBUTES, frozenset())
    dropped = _vocabulary.value(domain, None, CAPABILITY_ATTRIBUTES_DROPPED, {})
    return (frozenset(own) | frozenset(dropped)
            | UNIVERSAL_STATE_ATTRIBUTES.value)


def capability_attribute_tables() -> Mapping[str, frozenset[str]]:
    """Le trascrizioni delle capacita', dominio per dominio, **come sono nella
    fonte** -- il giudizio nostro non le tocca. Per la prova che le riporta al
    sorgente di Home Assistant."""
    return MappingProxyType({
        domain: frozenset(_vocabulary.value(domain, None, CAPABILITY_ATTRIBUTES))
        for domain in sorted(_vocabulary.domains())
        if _vocabulary.value(domain, None, CAPABILITY_ATTRIBUTES) is not None})


def state_attribute_tables() -> Mapping[str, frozenset[str]]:
    """Come sopra, per la meta' «com'e' adesso»."""
    return MappingProxyType({
        domain: frozenset(_vocabulary.value(domain, None, STATE_ATTRIBUTES))
        for domain in sorted(_vocabulary.domains())
        if _vocabulary.value(domain, None, STATE_ATTRIBUTES) is not None})


def dropped_capability_attributes() -> Mapping[str, Mapping[str, str]]:
    """Gli attributi che Home Assistant chiama capacita' e questo vocabolario
    no, **con la ragione scritta di ognuno**. Un'eccezione senza ragione non
    passa la prova che legge questa vista."""
    return MappingProxyType({
        domain: _vocabulary.value(domain, None, CAPABILITY_ATTRIBUTES_DROPPED)
        for domain in sorted(_vocabulary.domains())
        if _vocabulary.value(domain, None, CAPABILITY_ATTRIBUTES_DROPPED) is not None})


# --------------------------------------------------------------------------
# LA REGOLA, imposta alla costruzione
# --------------------------------------------------------------------------

def _verify_operable_types_bring_their_rest() -> None:
    """Un tipo accendibile porta i suoi stati di riposo, **nella stessa
    modifica**.

    Gira all'importazione del modulo: chi aggiunge un tipo accendibile senza il
    suo riposo non fa passare nemmeno un `import`, tantomeno una prova. E' la
    differenza fra una regola scritta in un commento -- che e' cio' che era
    fino a oggi, e che si e' lasciata violare tre volte -- e una regola che la
    struttura impone.
    """
    incomplete = sorted(
        domain for domain in _vocabulary.domains()
        if is_operable(domain)
        and not _vocabulary.value(domain, None, RESTING_STATES, frozenset()))
    if incomplete:
        raise ValueError(
            "tipi dichiarati accendibili senza i loro stati di riposo: "
            f"{', '.join(incomplete)}. Un tipo aggiunto a meta' produce "
            "oggetti che non si chiudono mai -- il riposo si dichiara nella "
            "stessa modifica, non in quella dopo")


def _verify_no_state_is_both_rest_and_work() -> None:
    """Nessuno stato di un tipo vale insieme «ha finito» e «sta funzionando».

    Gira all'importazione, come la regola qui sopra e per la stessa ragione: le
    due meta' della metrica 2 si scrivono in due punti diversi del modulo, ed e'
    esattamente la distanza in cui una contraddizione passa inosservata. Uno
    stato in tutt'e due direbbe a `mind/facts.py` di chiudere l'episodio e al
    censore che quel tipo lo tiene aperto -- due risposte alla stessa domanda,
    che e' il difetto che questo vocabolario esiste per non avere.
    """
    contradictions = sorted(
        f"{row.domain}={state}"
        for row in _vocabulary.rows()
        for state in (row.fields[WORKING_STATES].value if WORKING_STATES in row.fields else ())
        if state in resting_states_of(row.domain, row.device_class))
    if contradictions:
        raise ValueError(
            "stati dichiarati insieme a riposo e in funzionamento: "
            f"{', '.join(contradictions)}. Un tipo non puo' rispondere due volte "
            "alla stessa domanda")


_verify_operable_types_bring_their_rest()
_verify_no_state_is_both_rest_and_work()
