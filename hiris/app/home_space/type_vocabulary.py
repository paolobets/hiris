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

**Cosa questo modulo NON fa ancora.** Non chiede niente a Home Assistant: i
campi `Asked` esisteranno quando la lettura viva entrera' (piano, fetta 3), e
il censore che confronta cio' che HA pubblica con cio' che questo vocabolario
rivendica arriva dopo (fetta 4). La forma li regge gia' entrambi; il contenuto
no, ed e' dichiarato invece che simulato.

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

#: I nomi dei bit di `supported_features`, dominio per dominio.
CAPABILITY_NAMES = "capability_names"


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
# **Cio' che questa regola NON copre ancora, e va detto invece che
# sottinteso**: impone che un tipo accendibile abbia ALMENO un riposo, non che
# TUTTI i suoi stati canonici siano classificati. `water_heater` e' il caso
# vivo -- `eco`, `electric`, `gas`, `heat_pump`, `high_demand` non sono ne'
# riposi ne' ignoti, e un boiler in `eco` aprirebbe un episodio che non si
# chiude mai. Chiuderlo richiede l'enumerazione degli stati che HA pubblica
# (provenienza `chiesto`, fetta 3) e il censore che la confronta con questa
# vocabolario (fetta 4); deciderne il giudizio e' del proprietario, non di questa
# fetta. Oggi non morde perche' `water_heater` non ha una gamba e non entra
# nel pavimento -- ma «e' accendibile» e «entra nel pavimento» sono due
# metriche diverse dello stesso tipo, e devono poter divergere: allargare il
# pavimento per far tacere il censore sarebbe curare il sintomo sbagliato.
#
# `climate` e `cover` hanno gia' la loro riga sopra (portano una gamba): la
# seconda metrica si aggiunge alla stessa riga, non ne apre una seconda.

_vocabulary.extend("climate", operable=Ours(True), resting_states=Ours({"off"}))
_vocabulary.extend("cover", operable=Ours(True), resting_states=Ours({"closed"}))
_vocabulary.add("switch", operable=Ours(True), resting_states=Ours({"off"}))
_vocabulary.add("light", operable=Ours(True), resting_states=Ours({"off"}))
_vocabulary.add("fan", operable=Ours(True), resting_states=Ours({"off"}))
_vocabulary.add("water_heater", operable=Ours(True), resting_states=Ours({"off"}))
# `humidifier`: solo `on`/`off`, nessuno stato intermedio.
_vocabulary.add("humidifier", operable=Ours(True), resting_states=Ours({"off"}))
# `vacuum`: `docked` (in base, eventualmente in carica), `idle` (fermo, non in
# carica ne' in errore), `returning` (sta rientrando, non sta piu' pulendo),
# `error`. Solo `cleaning` e' acceso.
_vocabulary.add("vacuum", operable=Ours(True),
              resting_states=Ours({"docked", "returning", "error", "idle"}))
# `valve`: `open`, `opening`, `closing` sono TUTTI attivi, come per `cover`
# (con cui condivide `closed` come unico riposo) -- una valvola a meta'
# apertura non e' ferma, e `opening`/`closing` fra i riposi chiuderebbe
# l'oggetto a meta' transizione.
_vocabulary.add("valve", operable=Ours(True), resting_states=Ours({"closed"}))
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
              resting_states=Ours({"off", "idle", "standby"}))


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


def capability_tables() -> Mapping[str, Mapping[int, str]]:
    """Tutte le tabelle dei bit, per la prova che le riporta alla fonte. Non un
    secondo elenco: una vista sulle righe che gia' le portano."""
    return MappingProxyType({
        domain: _vocabulary.value(domain, None, CAPABILITY_NAMES)
        for domain in sorted(_vocabulary.domains())
        if _vocabulary.value(domain, None, CAPABILITY_NAMES) is not None})


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


_verify_operable_types_bring_their_rest()
