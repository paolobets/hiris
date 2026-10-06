"""Il registro di cio' che HIRIS sa calcolare: chiuso, e versionato.

Spec `docs/design/2026-09-10-i-tre-attori.md` §6. **Nessun oggetto nuovo per
l'utente**: e' la fondazione delle ricette (Fetta 4), che sono sequenze di
passi con nomi e possono nominare solo cio' che sta qui dentro. Un registro
che si possa allargare da qualunque punto del programma non e' un registro: e'
un elenco di cose che qualcuno ha scritto.

## Perche' un risultato ha DUE forme e non un campo che puo' restare vuoto

O e' una `Measurement` -- e allora porta il numero, **la sua unita'** e **la sua
copertura** -- oppure e' un `NotComputable`, e allora porta il **perche'**. Non
c'e' nessun costruttore che produca un numero senza unita', ne' un'assenza
senza ragione: non e' un controllo a valle, e' la struttura. Il precedente
della disciplina e' `home_space/type_vocabulary.Field`, che non si puo'
costruire senza provenienza perche' la provenienza e' la CLASSE.

Il difetto che questa forma rende impossibile e' gia' stato pagato:
`mind/facts._difference` con un solo punto nel giorno restituiva `0.0`, cioe'
*«non e' cambiato niente»* travestito da dato -- corretto in `None` il
26/08/2026, e `None` e' meglio di zero ma non dice ancora **perche'**.

## La copertura, e perche' la soglia non e' un numero misurato

La copertura dice **quanta parte del periodo aveva dati**. E' cio' che rende il
set onesto: sotto una soglia il risultato diventa «non calcolabile, e perche'»,
mai un numero plausibile.

**Misurato sulla casa vera l'11/09/2026**, sulle 35 entita' con `state_class`
che l'osservatore teneva dentro QUEL GIORNO, sul giorno pieno del 10/09.

(La spec, §1, ne conta **45** il 10/09: non e' una contraddizione ed e' giusto
dirlo qui invece di lasciare due numeri scollegati. Lo scope non e' una lista
fissa -- l'osservatore se lo ridecide a ogni riconsiderazione -- e fra le due
misure ci sono una riconsiderazione e un rilascio. Il numero che conta per la
distribuzione qui sotto e' quello su cui la distribuzione e' stata presa: 35.)

```
24/24 punti  ->  32 entita'   (copertura piena)
19/24 punti  ->   1 entita'
 0/24 punti  ->   2 entita'   (sensor.gestione_carichi_power,
                               sensor.luci_di_natale_energia_totale)
```

La distribuzione e' **bimodale**: o piena, o vuota. Fra lo zero e il 79% su
questa casa **non c'e' niente**, quindi qualunque soglia scelta in quel tratto
si comporterebbe in modo identico sui dati veri: la misura non puo' dettare il
numero, puo' solo dire che il caso che morde davvero e' lo zero. La soglia qui
sotto e' quindi **scelta per il suo significato e dichiarata tale** -- non un
numero misurato, e non spacciato per tale.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType

from ..home_space.house import SOURCE_LIVE, SOURCE_STATES

#: Sotto questa copertura un risultato di periodo diventa «non calcolabile».
#: **Scelta, non misurata** (vedi il docstring del modulo): tre quarti del
#: periodo e' il punto oltre il quale un totale «del giorno» avrebbe piu' di
#: sei ore mancanti, e sei ore mancanti sono un altro giorno. Sulla casa vera
#: non rifiuta niente per parzialita' -- l'unica serie parziale misurata sta al
#: 79%, appena sopra -- e morde sulle due serie a zero, che e' il caso per cui
#: la regola esiste.
MINIMUM_COVERAGE = 0.75


class Period:
    """**Su quando** si calcola: un elenco di finestre, non un intervallo solo.

    Lo produce `episodio` (le finestre in cui un soggetto era in uno stato) e
    lo misura `tempo_in_stato`: e' la coppia che serve alla presenza -- quanto
    tempo qualcuno e' stato in casa -- ed e' la ragione per cui questa classe
    resta (decisione D7 del proprietario, 06/10/2026, piano degli attori
    strati 3-4). Nacque l'11/09/2026 per le sette domande del proprietario
    (`docs/design/2026-09-11-le-domande-del-proprietario.md`, oggi storia):
    le operazioni che restringevano un calcolo a un periodo sono uscite con
    quel cancello, il periodo no.

    **Le finestre si ordinano e si fondono quando si toccano.** Due episodi
    contigui dello stesso soggetto sono un periodo solo: lasciandoli separati
    la durata resterebbe giusta, ma un conteggio a cavallo del confine
    conterebbe due volte lo stesso evento.

    **Il confine destro e' escluso.** Due finestre adiacenti non devono
    contenere entrambe lo stesso istante, per la stessa ragione.
    """

    __slots__ = ("_windows",)

    def __init__(self, windows) -> None:
        clean = []
        for start, end in windows:
            if end < start:
                raise ValueError(
                    f"finestra che finisce prima di cominciare: ({start}, {end})")
            clean.append((float(start), float(end)))
        if not clean:
            raise ValueError(
                "un periodo senza finestre non e' «tutto il tempo» ne' «nessun "
                "tempo»: e' una domanda mal posta, e produrrebbe una copertura 0/0")
        clean.sort()
        merged = [clean[0]]
        for start, end in clean[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        self._windows = tuple(merged)

    @property
    def windows(self) -> tuple[tuple[float, float], ...]:
        return self._windows

    @property
    def duration_s(self) -> float:
        return sum(end - start for start, end in self._windows)

    def __eq__(self, other) -> bool:
        return type(self) is type(other) and self._windows == other._windows

    def __hash__(self) -> int:
        return hash(self._windows)

    def __repr__(self) -> str:
        return f"Period({list(self._windows)!r})"


class Result(ABC):
    """Cio' che un'operazione restituisce: **o una misura, o un rifiuto
    motivato**. Astratta apposta -- averla concreta vorrebbe dire poter
    restituire «un risultato» senza dire quale delle due cose sia."""

    __slots__ = ()

    @property
    @abstractmethod
    def computable(self) -> bool:
        """Se questo risultato porta un numero. Astratto: e' cio' che rende
        `Result` inutilizzabile da sola."""


class Measurement(Result):
    """Un numero **con la sua unita' e la sua copertura**, inseparabili.

    **Non tutto cio' che esce da un'operazione e' una grandezza fisica**, e le
    unita' lo dicono: `"periodo"` (`episodio`), `"coefficiente"`
    (`correlazione`), `"frazione"` (`quota`). Sono **etichette di specie, non
    unita' di misura**, e vale la pena dirlo invece di lasciar credere che kWh
    e «periodo» siano la stessa
    categoria di cosa. La struttura chiede comunque una parola perche'
    l'alternativa -- un campo che qualche volta si puo' lasciare vuoto -- e'
    precisamente come nasce il frammento: una porta che a volte si puo' non
    chiudere resta aperta.

    Le due non sono parametri che si possano dimenticare: sono obbligatorie
    per nome, e senza di esse l'oggetto non nasce. La prima fondamenta lo
    chiede alla lettera -- *«un valore senza la sua unita' e senza il suo
    significato non e' un oggetto: e' un frammento»* -- e questo progetto l'ha
    gia' pagata leggendo `72` senza sapere se fossero Celsius o Fahrenheit.
    """

    __slots__ = ("_coverage", "_unit", "_value")

    def __init__(self, value: float, *, unit: str, coverage: float) -> None:
        if not str(unit or "").strip():
            raise ValueError("una misura senza unita' non e' un oggetto: e' un frammento")
        if not 0.0 <= float(coverage) <= 1.0:
            raise ValueError(
                f"copertura fuori da [0, 1]: {coverage!r}. Non e' pedanteria -- "
                "e' un conto sbagliato a monte, e passerebbe in pagina come se "
                "qualcuno l'avesse verificato")
        self._value = value
        self._unit = str(unit).strip()
        self._coverage = float(coverage)

    @property
    def computable(self) -> bool:
        return True

    @property
    def value(self):
        return self._value

    @property
    def unit(self) -> str:
        return self._unit

    @property
    def coverage(self) -> float:
        return self._coverage

    def __eq__(self, other) -> bool:
        return (type(self) is type(other) and self._value == other._value
                and self._unit == other._unit
                and self._coverage == other._coverage)

    def __hash__(self) -> int:
        return hash((self._value, self._unit, self._coverage))

    def __repr__(self) -> str:
        return (f"Measurement({self._value!r}, unit={self._unit!r}, "
                f"coverage={self._coverage!r})")


# -- PERCHE' una misura non c'e': il vocabolario delle cause (B-26) -----------
#
# Attori, strato 1, Task 1.2 (05/10/2026). Fino ad allora il perche' era solo
# una FRASE: chi voleva contare le misure rifiutate per causa -- la batteria
# degli attori, l'analista, la riparazione delle ricette -- doveva leggere la
# prosa, e cinque frasi diverse dicevano cause che non coincidevano (B-26:
# «manca lo `state_class`» falso in 21 casi su 21). Ora la causa e' un campo,
# e il vocabolario e' UNO:
#
# - gli STATI DELLA FONTE (`House.source`, Tappa 3, Task 8), tutti tranne
#   «viva": dove la misura tace perche' la fonte tace, la causa e' la parola
#   della fonte, non un sinonimo;
# - le cause che la MISURA aggiunge, qui sotto, ognuna con la sua ragione.
#   E' una lista di AMMISSIONE: una parola nuova entra scritta qui, con la
#   ragione, o il costruttore di `NotComputable` la rifiuta.

#: La fonte parla, ma Home Assistant non tiene statistiche per lei.
NO_STATISTICS = "senza_statistiche"
#: L'id non lo conosce nessuno: ne' il registro ne' gli stati.
UNKNOWN_SOURCE = "assente"
#: Le statistiche esistono forse, ma non si sono potute leggere.
STATISTICS_UNREAD = "statistiche_non_lette"
#: I dati del giorno sono troppo pochi per un numero onesto.
COVERAGE_LOW = "copertura_bassa"
#: La ricetta chiede una cosa che non si puo' fare.
RECIPE_BROKEN = "ricetta_storta"
#: La fonte manda un valore che non si muove mentre dovrebbe.
FROZEN = "ferma"
#: Coi dati giusti, la domanda non ha risposta.
NO_ANSWER = "senza_risposta"

#: Le cause che la misura aggiunge agli stati della fonte, con la ragione.
MEASURE_CAUSES = MappingProxyType({
    NO_STATISTICS: (
        "la fonte parla, ma Home Assistant non la elenca fra le statistiche "
        "(`recorder/list_statistic_ids`): un dominio che non le compila, o un "
        "sensor senza `state_class`. Non e' uno stato della fonte -- `source` "
        "lo porta come campo, `statistiche` -- e quindi ha una parola sua"),
    UNKNOWN_SOURCE: (
        "`House.source` risponde `None`: l'id non e' ne' nel registro ne' "
        "negli stati. Non e' «sparita», che in `source` vuol dire «nel "
        "registro e senza stato»: chiamarla cosi' direbbe un fatto diverso"),
    STATISTICS_UNREAD: (
        "la lettura delle statistiche orarie e' fallita (S-28, trovato 7 "
        "della Tappa 3): non si sa se la serie ci sarebbe stata"),
    COVERAGE_LOW: (
        "la serie c'e' ma copre troppo poco del periodo per dare un numero "
        "(`MINIMUM_COVERAGE`), o non ha abbastanza punti per l'operazione"),
    RECIPE_BROKEN: (
        "la ricetta non si esegue o chiede l'impossibile: non e' valida, "
        "somma una misura istantanea, mescola unita', dichiara piu' parti di "
        "quante il periodo ne abbia. Si ripara riscrivendola, non coi dati"),
    FROZEN: (
        "la regola del dato fermo (attori, Task 1.1 e 1.3; D3 e D4 del "
        "proprietario, 03/10/2026): una misura su una fonte ferma si rifiuta. "
        "Ammessa qui perche' la riparazione delle ricette (Task 1.6) la sa gia' "
        "NON riparabile, e la batteria degli attori la conta per nome"),
    NO_ANSWER: (
        "i dati ci sono e sono giusti, ma la domanda non ha risposta: "
        "denominatore nullo, rapporto negativo, serie che non varia, nessun "
        "episodio. Non e' un guasto di nessuno, e dirlo con una delle altre "
        "parole lo farebbe sembrare tale"),
})

#: IL vocabolario delle cause: gli stati della fonte che tacciono, piu' quelli
#: della misura. Si compone, non si ricopia.
CAUSES = frozenset({state for state in SOURCE_STATES if state != SOURCE_LIVE}
                   | set(MEASURE_CAUSES))


class NotComputable(Result):
    """Un rifiuto **con la sua ragione e la sua causa**, e nessuna delle due
    e' facoltativa.

    La spec lo chiede alla lettera: il risultato diventa *«non calcolabile, E
    PERCHE'»*. Un rifiuto muto e' un silenzio, e un silenzio non e'
    distinguibile da un'assenza di problemi -- che e' il difetto che questo
    prodotto insegue in ogni sua parte.

    La **ragione** e' la frase, per chi legge; la **causa** e' la parola del
    vocabolario chiuso (`CAUSES`), per chi conta e per chi decide (B-26,
    attori Task 1.2): la riparazione delle ricette sceglie dalla causa, non
    dalla prosa.
    """

    __slots__ = ("_cause", "_reason")

    def __init__(self, reason: str, *, cause: str) -> None:
        if not str(reason or "").strip():
            raise ValueError(
                "un «non calcolabile» senza ragione e' un silenzio, non una risposta")
        if cause not in CAUSES:
            raise ValueError(
                f"causa fuori dal vocabolario: {cause!r}. Le cause sono "
                f"{', '.join(sorted(CAUSES))}; una nuova entra in "
                "`MEASURE_CAUSES`, con la sua ragione")
        self._reason = str(reason).strip()
        self._cause = cause

    @property
    def computable(self) -> bool:
        return False

    @property
    def reason(self) -> str:
        return self._reason

    @property
    def cause(self) -> str:
        return self._cause

    def __eq__(self, other) -> bool:
        return (type(self) is type(other) and self._reason == other._reason
                and self._cause == other._cause)

    def __hash__(self) -> int:
        return hash((self._reason, self._cause))

    def __repr__(self) -> str:
        return f"NotComputable({self._reason!r}, cause={self._cause!r})"


# ── Il registro ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Operation:
    """Una voce del registro: **cosa sa calcolare, e a quali condizioni**.

    Nessun campo ha un default, e non e' una scelta di stile: la spec §6 dice
    *«ogni operazione dichiara, e non si puo' costruire senza»*. Una voce muta
    sarebbe un nome in un elenco -- e una ricetta (Fetta 4) non potrebbe
    essere **rifiutata prima di eseguirla**, che e' l'unica cosa che rende le
    ricette un dato invece che codice.
    """

    name: str
    inputs: tuple[str, ...]
    returns: str
    refuses_when: tuple[str, ...]
    run: Callable[..., Result]
    #: Se una RICETTA puo' nominare questa operazione.
    #:
    #: **Il registro e le ricette non sono la stessa cosa.** Il registro ha
    #: voci che una ricetta non potrebbe mai portare, perche' vogliono un
    #: valore che il JSON non sa scrivere -- `episodio` vuole `is_on`, che e'
    #: una FUNZIONE.
    #:
    #: **Costava un difetto vero, il 14/09/2026.** Il catalogo mostrato al
    #: modello elencava ogni voce del registro; il modello ha scritto la sua
    #: prima ricetta con `episodio`; `validate()` guardava solo che il nome
    #: esistesse, e l'ha accettata; il resoconto l'ha eseguita e `TypeError` ha
    #: ucciso la riaggregazione di due giorni interi, a ogni riavvio.
    #:
    #: Niente valore di fabbrica, come gli altri campi: la spec §6 dice «ogni
    #: operazione dichiara, e non si puo' costruire senza», e un default
    #: `True` avrebbe rifatto esattamente il difetto alla prossima voce nuova.
    in_recipes: bool
    #: La FORMA di ogni ingresso, nell'ordine -- vedi le `SHAPE_*` qui sopra.
    #: Tante quante sono le cose che `run` prende per posizione, e un cancello
    #: lo verifica: una forma in meno lascerebbe un ingresso non controllato,
    #: che e' esattamente il buco da cui e' passato il difetto del
    #: 14/09/2026.
    takes: tuple[str, ...]

    @property
    def offerable(self) -> bool:
        """Se il catalogo puo' offrirla al modello.

        Non basta che una ricetta possa NOMINARLA (`in_recipes`): deve anche
        poterle consegnare cio' che vuole. Un'operazione che pretende un
        `Period`, le letture grezze o un elenco di misure non ha nessuna
        sorgente dentro una ricetta -- offrirla sarebbe metterla nell'elenco
        perche' il modello la usi e il validatore la rifiuti sempre, bruciando
        il giro e lasciando il dispositivo senza ricetta per sempre.
        """
        return self.in_recipes and all(f in RECIPE_SHAPES for f in self.takes)

    @property
    def required_params(self) -> tuple[str, ...]:
        """I parametri che una ricetta DEVE dare, letti dalla firma di `run`.

        **Derivati, non dichiarati**: un elenco scritto a mano accanto alla
        firma diverge dalla firma al primo ritocco, ed e' la classe di difetto
        che questo progetto ha gia' pagato piu' volte -- la ragione scritta
        accanto al codice smentita dal codice che cita.
        """
        import inspect

        return tuple(
            name for name, p in inspect.signature(self.run).parameters.items()
            if p.kind is p.KEYWORD_ONLY and p.default is p.empty)

    @property
    def input_range(self) -> tuple[int, int]:
        """Quanti ingressi accetta: `(minimo, massimo)`.

        Gli **ingressi** sono cio' che `run` prende per posizione -- le entita'
        e i passi che la ricetta consegna nell'ordine. `quota` ne prende due: con
        tre il motore solleverebbe `TypeError` a meta' giornata, che e'
        esattamente cio' che rifiutare-prima-di-eseguire esiste per impedire.

        Letti dalla firma, come `required_params`, e per la stessa ragione.
        """
        import inspect

        by_position = [p for p in inspect.signature(self.run).parameters.values()
                       if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        needed = sum(1 for p in by_position if p.default is p.empty)
        return needed, len(by_position)


#: **Le FORME**, cioe' cosa un'operazione si aspetta in ciascun ingresso.
#:
#: Nascono da un difetto misurato dal vivo il 14/09/2026. La 3.34.0 aveva
#: chiuso i nomi, i parametri e il numero di ingressi; restava la forma:
#: `tempo_in_stato` vuole un `Period`, una ricetta gli consegnava la serie di
#: un'entita' -- una lista -- e il motore moriva con
#: `AttributeError: 'list' object has no attribute 'windows'`.
#:
#: **Il punto non e' l'elenco, e' cosa una ricetta sa PRODURRE.** Dentro una
#: ricetta esistono due sole sorgenti: `@entita` da' la serie del periodo,
#: `$passo` da' il risultato di un passo precedente. Tutto il resto --
#: le letture grezze, un `Period` nudo -- nessuna ricetta lo sa scrivere, e
#: un'operazione che lo pretende non e' offribile al modello: gliela si
#: metterebbe nell'elenco perche' la usi, e il validatore la rifiuterebbe
#: sempre.
SHAPE_SERIES = "serie del periodo"
SHAPE_RESULT = "misura"
SHAPE_READINGS = "letture"
SHAPE_PERIOD = "periodo"

#: Le due forme che una ricetta sa consegnare. Un'operazione che ne vuole altre
#: resta nel registro ma fuori dal catalogo: oggi sono `episodio` e
#: `tempo_in_stato`, tenute per la presenza (D7, 06/10/2026) e senza ancora un
#: chiamante in produzione.
RECIPE_SHAPES = (SHAPE_SERIES, SHAPE_RESULT)


#: Quale versione del registro. Le ricette vivranno piu' a lungo del registro
#: che le esegue: senza un numero, una ricetta scritta oggi e riletta fra sei
#: mesi non saprebbe dire se le operazioni che nomina siano ancora quelle.
#:
#: **Lo legge `recipe_turn._still_valid`**, ed e' cio' che rende un rifiuto
#: non definitivo (decisione del proprietario, 13/09/2026): un dispositivo che
#: oggi il modello non sa misurare torna una domanda aperta il giorno in cui
#: il registro cambia. La riga che diceva «oggi nessuno lo legge, ed e'
#: voluto» e' rimasta qui dopo che il lettore era nato: falsa, corretta il
#: 15/09/2026 dalla revisione indipendente.
#:
#: **SI ALZA QUANDO CAMBIA CIO' CHE IL MODELLO PUO' CHIEDERE O SAPERE.** Non a
#: ogni rilascio: quando cambia il catalogo, le forme che una ricetta sa
#: consegnare, i rifiuti dichiarati, o le informazioni che la domanda porta.
#:
#: - **1** (12/09/2026) -- il registro nasce.
#: - **2** (15/09/2026) -- tre cambi, e nessuno dei tre aveva alzato il
#:   numero: `in_recipes` toglie dal catalogo cio' che una ricetta non puo'
#:   scrivere (3.34.0); le forme si separano e `primo_ultimo_differenza` esce
#:   dal catalogo (3.37.0); e la domanda dice **quali entita' abbiano una
#:   serie** (3.47.0). I 21 rifiuti archiviati erano stati decisi senza saperlo,
#:   e restavano validi per sempre: alzando il numero tornano domande aperte.
REGISTRY_VERSION = 2

_REGISTRY: dict[str, Operation] = {}


def _register(operation: Operation) -> Operation:
    """Aggiunge una voce **mentre il modulo si costruisce**, e solo allora.

    A modulo caricato il registro e' una vista di sola lettura
    (`MappingProxyType`): «chiuso» deve essere una proprieta', non una buona
    intenzione. Se un modulo qualunque potesse aggiungerci una voce a caldo,
    la validazione delle ricette direbbe di si' a qualcosa che nessuno ha
    rivisto -- ed e' esattamente il difetto che questo registro esiste per
    rendere impossibile.
    """
    if operation.name in _REGISTRY:
        raise ValueError(f"operazione gia' nel registro: {operation.name}")
    _REGISTRY[operation.name] = operation
    return operation


#: Il registro, in sola lettura. Si guarda per nome; non ci si scrive.
REGISTRY = MappingProxyType(_REGISTRY)


def _known_points(series, expected_parts: int | None = None) -> tuple[list, float]:
    """I punti che portano un valore, e la **copertura** che ne esce.

    Un punto con `valore: None` e' un'ora SENZA dato, non un'ora a zero: e' la
    regola che `mind/facts._dimension_points` applicava (uscita col bilancio il
    01/10/2026) -- *«mai uno zero inventato»* -- e qui produce anche il numero
    che dice quanto manca.

    **`expected_parts` e' il denominatore vero, e chi chiama deve darlo quando lo
    sa.** Senza, la copertura dice quanto del CAMPIONE si e' letto, non quanto
    del periodo -- e i due numeri divergono proprio dove fa male: Home
    Assistant **omette** le ore senza dati dalle statistiche orarie (correzione
    del 27/08/2026, pagata nel vecchio corpo del bilancio), per
    cui un giorno che consegna tre ore, tutte e tre con un valore, darebbe
    copertura 100% -- un numero non misurato con la faccia di uno misurato,
    che e' il difetto che questo modulo esiste per non fare. La distribuzione
    misurata sulla casa vera l'11/09/2026 e' su base 24, non sulla lunghezza
    della serie.
    """
    points = list(series or [])
    known = [p for p in points if isinstance(p, dict) and p.get("valore") is not None]
    expected = expected_parts if expected_parts else len(points)
    return known, (len(known) / expected if expected else 0.0)


def _instant_points(series, expected_parts: int | None = None) -> tuple[list, float]:
    """I punti di una misura **istantanea**, e la copertura che ne esce.

    Home Assistant distingue due generi di statistica oraria, e li manda con
    campi diversi: un **contatore** porta `change` (il nostro `valore`), una
    **misura istantanea** porta `mean`/`min`/`max` (`media`/`minimo`/
    `massimo`). Misurato sulla casa vera il 14/09/2026: 74 contatori e **56
    misure istantanee** -- ogni temperatura, umidita', CO2, rumore, segnale e
    potenza della casa.

    Ogni punto qui torna col suo `valore` messo alla MEDIA dell'ora, e i veri
    estremi dell'ora accanto. Un contatore non ha una media: allora `valore`
    resta quello che gia' era, e gli estremi sono il valore stesso -- cosi' «la
    media oraria del consumo» resta una domanda legittima invece di diventare
    un rifiuto.
    """
    points = []
    for p in list(series or []):
        if not isinstance(p, dict):
            continue
        middle = p.get("media")
        if middle is None:
            middle = p.get("valore")
        if middle is None:
            continue
        low = p.get("minimo")
        high = p.get("massimo")
        points.append({"valore": middle,
                       "minimo": middle if low is None else low,
                       "massimo": middle if high is None else high})
    expected = expected_parts if expected_parts else len(list(series or []))
    return points, (len(points) / expected if expected else 0.0)


def _looks_instantaneous(series) -> bool:
    """Se la serie e' fatta di ore che portano una MEDIA e nessun cambio.

    Si guarda la forma del dato, non un'etichetta: l'unica cosa che distingue i
    due generi e' quali campi Home Assistant ha mandato, e quella e' li' da
    leggere.
    """
    return any(isinstance(p, dict) and p.get("media") is not None
               and p.get("valore") is None for p in series or [])


#: Cosa si risponde a chi prova a sommare una misura istantanea. Prima usciva
#: «la serie e' vuota»: vero e inutile, perche' la serie non e' vuota affatto
#: -- e' di un ALTRO genere, e il modello riscriverebbe la stessa ricetta.
_INSTANTANEOUS_REASON = (
    "questa e' una misura ISTANTANEA (Home Assistant ne manda media, minimo e "
    "massimo per ogni ora), non un contatore con un cambio da sommare: "
    "sommarla darebbe la somma delle temperature di ventiquattro ore"
)


def _reject_for_coverage(coverage: float, known: int,
                         *, points: int | None = None) -> NotComputable | None:
    """Il rifiuto motivato, con **il numero dentro la frase**: «copertura 8%»
    dice a chi legge quanto mancava, mentre «non calcolabile» lo lascerebbe
    a indovinare.

    **E «vuota» si dice solo quando e' vuota.** `points` e' quanti punti la
    serie portava in tutto: se ce n'erano e nessuno era un numero, la serie
    non e' vuota affatto -- e' di ore che Home Assistant ha mandato senza
    dato, ed e' la stessa distinzione gia' fatta per le misure istantanee
    poche righe piu' su.

    **Questa distinzione non ha ancora mai fatto la differenza sulla casa
    vera, e va detto.** Nasce il 15/09/2026 da una diagnosi SBAGLIATA: le 28
    misure rifiutate del 14 dicevano «la serie e' vuota», e `light.abat_jour_
    sinistra` aveva cinque punti nella STORIA di Home Assistant -- da cui la
    conclusione, affrettata, che l'operazione li ricevesse. Non li riceve: le
    ricette leggono `HAClient.hourly_statistics()`, e le statistiche esistono
    solo per le entita' che dichiarano uno `state_class`. Misurato lo stesso
    giorno con `recorder/list_statistic_ids`: **130 entita' con statistiche
    sulla casa, tutte `sensor`** -- nessuno `switch`, `light`, `valve`. Per
    quelle la serie e' vuota davvero.

    Il ramo resta perche' il caso esiste (Home Assistant OMETTE le ore senza
    dato, ma nulla garantisce che non ne mandi con `valore` nullo) e perche'
    dire «vuota» di una serie piena sarebbe falso. Ma **zero occorrenze
    misurate**: non e' questo che spiega i rifiuti di questa casa.
    """
    if not known:
        if points:
            return NotComputable(
                f"la serie ha {points} punti nel periodo ma nessuno porta un "
                "numero: e' una successione di stati, non di misure", cause=RECIPE_BROKEN)
        return NotComputable(
            "nessun punto con un valore nel periodo: la serie e' vuota", cause=COVERAGE_LOW)
    if coverage > 1.0:
        # Piu' punti di quanti il periodo ne preveda: e' un errore di chi
        # chiama -- la serie e il periodo non parlano dello stesso tempo.
        # **Si rifiuta, non si solleva**: `Measurement` rifiuterebbe comunque
        # una copertura fuori da [0, 1], ma con un `ValueError` che dall'
        # aggregazione notturna e' un crash, non una risposta. Un'operazione
        # che sa dire «non lo so» non ha nessuna ragione di esplodere.
        return NotComputable(
            f"i punti con un valore sono piu' delle parti attese "
            f"(copertura {coverage:.0%}): la serie e il periodo non parlano "
            "dello stesso tempo", cause=RECIPE_BROKEN)
    if coverage < MINIMUM_COVERAGE:
        return NotComputable(
            f"copertura {coverage:.0%}, sotto il minimo di "
            f"{MINIMUM_COVERAGE:.0%}: un totale fatto di cosi' poche parti del "
            "periodo somiglia a un totale e non lo e'", cause=COVERAGE_LOW)
    return None


def _sum_period(series, *, unit: str, expected_parts: int | None = None) -> Result:
    """La somma delle parti conosciute del periodo, con la sua copertura.

    **Estratta da `mind/facts.build_balance_body`** (uscita il 01/10/2026),
    dove era «la somma delle ore CONOSCIUTE» e la copertura non usciva: un
    totale fatto di tre ore su ventiquattro aveva la stessa faccia di uno
    completo.
    """
    known, coverage = _known_points(series, expected_parts)
    if not known and _looks_instantaneous(series):
        return NotComputable(_INSTANTANEOUS_REASON, cause=RECIPE_BROKEN)
    refusal = _reject_for_coverage(coverage, len(known),
                                   points=len(series or []))
    if refusal is not None:
        return refusal
    return Measurement(round(sum(p["valore"] for p in known), 2),
                  unit=unit, coverage=coverage)


_register(Operation(
    name="somma_periodo",
    inputs=("una serie di punti con un valore", "l'unita' di quel valore",
              "quante parti il periodo doveva avere, quando chi chiama lo sa"),
    returns="il totale delle parti conosciute, con la sua unita' e la sua copertura",
    refuses_when=("l'entita' non ha statistiche in Home Assistant",
                   "la serie non ha nessun punto con un valore",
                "la copertura sta sotto il minimo"),
    takes=(SHAPE_SERIES,),
    in_recipes=True,
    run=_sum_period,
))


def _ratio(numerator: Result, denominator: Result) -> Result:
    """Un rapporto fra 0 e 1, arrotondato a tre decimali.

    **Prende due RISULTATI, non due numeri nudi**, e la ragione e' la ricetta
    della spec (§7): `quota(differenza_fra(consumata, prelevata), consumata)`.
    Con due numeri quella riga non si scrive -- e, peggio, la copertura dei
    totali a monte si perderebbe per strada: una quota calcolata su un totale
    coperto all'80% usciva dichiarando 100%, cioe' una certezza che nessuno
    aveva. Adesso **la copertura e' la peggiore delle due**, come in
    `differenza_fra`: un rapporto non e' piu' solido del piu' debole dei suoi
    due termini.

    **Estratta da `mind/facts._share`**, che aveva gia' le due regole giuste e
    le esprimeva con un `None`: qui il «non lo so» dice anche perche'.

    - **denominatore nullo -> non calcolabile**: «zero produzione» non significa
      «zero autoconsumo», significa che la domanda non ha risposta;
    - **rapporto negativo -> non calcolabile, e NON si clampa a zero**. Caso
      PREVISTO il 27/08/2026 e non ancora osservato su questa casa -- il
      docstring di `_share` in `mind/facts.py` lo diceva con precisione:
      *«oggi su questa casa il prelievo e' minimo e il caso non si vede;
      d'inverno si'»*. Succede quando la batteria si carica dalla rete. Zero
      affermerebbe «zero autosufficienza», e non lo sappiamo.
    """
    for r in (numerator, denominator):
        if not r.computable:
            return r
    if not denominator.value:
        return NotComputable(
            "il denominatore e' nullo: non e' «zero», e' una domanda senza risposta",
            cause=NO_ANSWER)
    try:
        value = float(numerator.value) / float(denominator.value)
    except (TypeError, ValueError, ZeroDivisionError):
        return NotComputable("i due numeri non si leggono come numeri", cause=RECIPE_BROKEN)
    if value < 0:
        return NotComputable(
            f"il rapporto e' negativo ({value:.3f}): non si clampa a zero, "
            "perche' zero affermerebbe una cosa che non sappiamo", cause=NO_ANSWER)
    return Measurement(round(value, 3), unit="frazione",
                       coverage=min(numerator.coverage, denominator.coverage))


_register(Operation(
    name="quota",
    inputs=("la misura del numeratore", "la misura del denominatore"),
    returns=("una frazione fra 0 e 1, con la copertura peggiore delle due: "
             "un rapporto non e' piu' solido del suo termine piu' debole"),
    refuses_when=("una delle due non e' calcolabile", "il denominatore e' nullo",
                  "il rapporto sarebbe negativo"),
    takes=(SHAPE_RESULT, SHAPE_RESULT),
    in_recipes=True,
    run=_ratio,
))


def _difference(first: Result, second: Result) -> Result:
    """`prima - seconda`, **con la stessa unita' e la copertura peggiore**.

    Estratta dal `consumo - prelievo` di `mind/facts._balance_moments`
    (uscita col bilancio il 01/10/2026).

    Tre regole, e nessuna e' pedanteria:
    - **il «non lo so» si propaga**: se uno dei due non si e' potuto calcolare,
      il risultato non e' un numero piu' incerto -- non c'e';
    - **unita' diverse non si sottraggono**: sottrarre kWh da gradi produce un
      numero, e quel numero e' una bugia (prima fondamenta);
    - **la copertura e' la PEGGIORE delle due**, non la media: un numero
      calcolato su due serie di cui una quasi vuota vale quanto la piu' debole.
    """
    for r in (first, second):
        if not r.computable:
            return r
    if first.unit != second.unit:
        return NotComputable(
            f"unita' diverse ({first.unit} e {second.unit}): la differenza "
            "sarebbe un numero senza significato", cause=RECIPE_BROKEN)
    return Measurement(round(first.value - second.value, 2), unit=first.unit,
                  coverage=min(first.coverage, second.coverage))


_register(Operation(
    name="differenza_fra",
    inputs=("una misura", "un'altra misura della stessa unita'"),
    returns="la loro differenza, con la copertura peggiore delle due",
    refuses_when=("una delle due non e' calcolabile", "le unita' sono diverse"),
    takes=(SHAPE_RESULT, SHAPE_RESULT),
    in_recipes=True,
    run=_difference,
))


def _average_min_max(series, *, unit: str,
                   expected_parts: int | None = None) -> Result:
    """La media, il minimo e il massimo delle parti conosciute.

    Tutti e tre insieme, non uno alla volta: una media senza gli estremi
    nasconde proprio cio' che si va a cercare -- una stanza che sta bene in
    media e tocca i 14 gradi alle sei del mattino.
    """
    known, coverage = _instant_points(series, expected_parts)
    refusal = _reject_for_coverage(coverage, len(known),
                                   points=len(series or []))
    if refusal is not None:
        return refusal
    values = [p["valore"] for p in known]
    # **Il minimo del giorno e' il piu' piccolo dei minimi ORARI, non il piu'
    # piccolo delle medie.** Home Assistant li manda gia' tutti e due, e il
    # docstring qui sopra dice perche' conta: una stanza che scende a 14 gradi
    # alle sei del mattino ha una media oraria di 16, e prendere il minimo
    # delle medie direbbe 16 -- nascondendo esattamente cio' che si cercava.
    return Measurement({"media": round(sum(values) / len(values), 2),
                   "minimo": min(p["minimo"] for p in known),
                   "massimo": max(p["massimo"] for p in known)},
                  unit=unit, coverage=coverage)


_register(Operation(
    name="media_min_max",
    inputs=("una serie di punti con un valore", "l'unita' di quel valore",
              "quante parti il periodo doveva avere, quando chi chiama lo sa"),
    returns="media, minimo e massimo insieme",
    refuses_when=("l'entita' non ha statistiche in Home Assistant",
                   "la serie e' vuota", "la copertura sta sotto il minimo"),
    takes=(SHAPE_SERIES,),
    in_recipes=True,
    run=_average_min_max,
))


def _per_hour(series, *, unit: str, expected_parts: int | None = None) -> Result:
    """Il profilo: **ogni punto porta la sua ORA**, non la sua posizione.

    Correzione gia' pagata il 27/08/2026 in `mind/facts.build_balance_body`
    (uscita il 01/10/2026): la
    forma era una lista NUDA di valori, e Home Assistant **omette** le ore senza
    dati -- quindi l'indice non era l'ora, e una giornata che comincia alle 7
    aveva il primo valore in posizione zero. L'oggetto, da solo, non sapeva piu'
    dire «alle 13», che e' l'unica ragione per cui la forma esiste.

    **Le ore senza dato restano, col loro `None`**: un profilo che le togliesse
    direbbe che la giornata e' piu' corta di com'e'.
    """
    points = [p for p in (series or []) if isinstance(p, dict)]
    _, coverage = _known_points(points, expected_parts)
    if not points:
        return NotComputable(
            "nessun punto nel periodo: non c'e' nessun profilo",
            cause=COVERAGE_LOW)
    return Measurement([{"ora": p.get("inizio"), "valore": p.get("valore")}
                   for p in points], unit=unit, coverage=coverage)


_register(Operation(
    name="per_ora",
    inputs=("una serie di punti orari", "l'unita' dei valori",
              "quante parti il periodo doveva avere, quando chi chiama lo sa"),
    returns="il profilo, ogni punto con la sua ora",
    refuses_when=("l'entita' non ha statistiche in Home Assistant",
                   "la serie non ha nessun punto",),
    takes=(SHAPE_SERIES,),
    in_recipes=True,
    run=_per_hour,
))


def _episode(readings, *, is_on, period_end: float) -> Result:
    """Le finestre in cui un soggetto era «acceso»: **un `Period`**.

    Estratta dal ciclo apri/chiudi degli episodi di `mind/facts`, che dal
    17/09/2026 vive in `build_episodes` e non piu' dentro `aggregate_day`
    (spec 2026-09-16 §6: **una** costruzione degli episodi, chiamata
    dall'aggregazione e dal ricalcolo). Restituisce
    un periodo e non una lista di coppie **perche' e' cio' che rende la
    restrizione una composizione**: le finestre che escono di qui entrano in
    qualunque altra operazione come «su quando» (vedi `Period`).

    `is_on` arriva da fuori -- il vocabolario dei tipi sa quali stati siano
    riposo, e questo modulo non lo sa ne' deve impararlo.

    **Un episodio ancora aperto arriva alla fine del periodo, non all'ultima
    lettura.** Cio' che a fine giornata e' ancora in corso e' un fatto:
    chiuderlo dove l'abbiamo visto l'ultima volta direbbe che e' finito quando
    invece non lo sappiamo.

    **I due capi non si trattano allo stesso modo, e non e' una svista.** In
    coda si va oltre l'ultima lettura perche' l'assenza di uno spegnimento e'
    essa stessa informazione: nessuno ha detto «finito». In testa non si va
    indietro rispetto alla prima lettura, perche' li' l'assenza non dice
    niente -- prima non stavamo guardando. Chi sa che era gia' acceso lo dice
    consegnando una lettura all'inizio del periodo: e' esattamente cio' che
    `mind/facts.aggregate_day` fa con lo stato ereditato dal giorno prima
    (fetta 1, 10/09/2026 -- otto termostati accesi tutto il tempo che
    producevano zero episodi).
    """
    windows = []
    start = None
    for instant, state in readings or []:
        if is_on(state):
            if start is None:
                start = float(instant)
        elif start is not None:
            windows.append((start, float(instant)))
            start = None
    if start is not None:
        windows.append((start, float(period_end)))
    if not windows:
        return NotComputable("nessun episodio nel periodo: non si e' mai acceso", cause=NO_ANSWER)
    return Measurement(Period(windows), unit="periodo", coverage=1.0)


_register(Operation(
    name="episodio",
    inputs=("le letture di un soggetto", "come si riconosce un riposo",
              "la fine del periodo"),
    returns="le finestre in cui era acceso, come un periodo",
    refuses_when=("non si e' mai acceso nel periodo",),
    # `is_on` e' una FUNZIONE: nessun JSON la porta, quindi nessuna
    # ricetta puo' nominare questa operazione. Resta nel registro per la
    # presenza (D7, 06/10/2026): non la chiama ancora nessuno.
    takes=(SHAPE_READINGS,),
    in_recipes=False,
    run=_episode,
))


def _time_in_state(period: Period) -> Result:
    """Quanto e' durato in tutto, in secondi.

    Si appoggia a `Period.duration_s`, che ha gia' fuso le finestre contigue:
    due episodi attaccati sono un tempo solo, e sommarli separati li
    conterebbe due volte al confine.
    """
    return Measurement(period.duration_s, unit="s", coverage=1.0)


_register(Operation(
    name="tempo_in_stato",
    inputs=("un periodo",),
    returns="la durata totale, in secondi",
    refuses_when=("il periodo non esiste: `Period` rifiuta un elenco vuoto",),
    takes=(SHAPE_PERIOD,),
    in_recipes=True,
    run=_time_in_state,
))


def _period_comparison(first: Result, later: Result) -> Result:
    """Lo stesso conto su due periodi: **di quanto e' cambiato, e di quanto in
    proporzione**.

    Nasce dalla domanda 2 del proprietario: *«si puo' ottimizzare gestendo la
    diversa produzione per mese?»* -- che e' lo stesso rapporto guardato su
    periodi diversi.

    **Da una base nulla non esce nessuna percentuale.** La differenza si', e si
    dice quella: una variazione percentuale su zero non e' un numero grande, e'
    un numero che non esiste.
    """
    for r in (first, later):
        if not r.computable:
            return r
    if first.unit != later.unit:
        return NotComputable(
            f"unita' diverse ({first.unit} e {later.unit}): i due periodi non "
            "misurano la stessa cosa", cause=RECIPE_BROKEN)
    difference = round(later.value - first.value, 2)
    variation = round(difference / first.value, 3) if first.value else None
    return Measurement({"differenza": difference, "variazione": variation},
                  unit=first.unit,
                  coverage=min(first.coverage, later.coverage))


_register(Operation(
    name="confronto_periodi",
    inputs=("la misura di un periodo", "la misura di un altro periodo"),
    returns="di quanto e' cambiato, e in che proporzione quando ha senso",
    refuses_when=("una delle due non e' calcolabile", "le unita' sono diverse"),
    takes=(SHAPE_RESULT, SHAPE_RESULT),
    in_recipes=True,
    run=_period_comparison,
))


def _trend_line(series, *, unit: str) -> Result:
    """Dove sta andando: **il verso, la pendenza, e su quanti punti**.

    *«Non si inventa una soglia: si archivia e si interpreta»* (decisione del
    proprietario, 09/09/2026). Questa operazione non giudica se la tendenza sia
    buona: dice cosa fa la serie e **quanto e' sottile la base** su cui lo
    dice -- con ventotto giorni di storia va detto che sono ventotto.

    **Due punti non sono una tendenza**: fanno sempre una retta perfetta, e
    chiamarla tendenza sarebbe un numero plausibile al posto di un «non lo so».
    """
    # Una tendenza si chiede soprattutto a una misura istantanea -- «la
    # temperatura sta salendo?» -- e quelle non hanno un `cambio`: prima
    # dell'14/09/2026 rifiutavano sempre, «ce ne sono 0».
    known, coverage = _instant_points(series)
    if len(known) < 3:
        return NotComputable(
            f"servono almeno 3 punti per una tendenza, ce ne sono {len(known)}: "
            "due fanno sempre una retta perfetta, e non e' una tendenza", cause=COVERAGE_LOW)
    values = [p["valore"] for p in known]
    n = len(values)
    mean_x = (n - 1) / 2
    mean_y = sum(values) / n
    numerator = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values))
    denominator = sum((i - mean_x) ** 2 for i in range(n))
    slope = numerator / denominator if denominator else 0.0
    direction = "in salita" if slope > 0 else ("in discesa" if slope < 0 else "piatta")
    return Measurement({"verso": direction, "pendenza": round(slope, 4), "punti": n},
                  unit=unit, coverage=coverage)


_register(Operation(
    name="tendenza",
    inputs=("una serie di punti", "l'unita' dei valori"),
    returns="il verso, la pendenza e su quanti punti si e' detto",
    refuses_when=("l'entita' non ha statistiche in Home Assistant",
                   "i punti con un valore sono meno di tre",),
    takes=(SHAPE_SERIES,),
    in_recipes=True,
    run=_trend_line,
))


def _correlation(first, second) -> Result:
    """Quanto due serie si muovono insieme, fra -1 e 1.

    Nasce dalla domanda 3: *«l'irrigazione sta gestendo bene il fabbisogno del
    prato?»*, che chiede di guardare l'irrigazione contro il tempo che faceva.

    **Non dice che una cosa CAUSA l'altra**, e la spec lo chiede
    esplicitamente (§10): l'autosufficienza crollata dal 99% al 61% e' spiegata
    dal meteo, ed e' una conferma, non una scoperta. Il coefficiente e' un
    fatto; la causa non lo e', e chi legge deve saperlo da qui.
    """
    a = [p.get("valore") for p in (first or []) if isinstance(p, dict)]
    b = [p.get("valore") for p in (second or []) if isinstance(p, dict)]
    if len(a) != len(b):
        return NotComputable(
            f"le due serie hanno lunghezza diversa ({len(a)} e {len(b)}): "
            "accoppiare punti che non si corrispondono produce un coefficiente "
            "che non parla di niente", cause=RECIPE_BROKEN)
    pairs = [(x, y) for x, y in zip(a, b, strict=True)
              if x is not None and y is not None]
    if len(pairs) < 3:
        return NotComputable(
            f"servono almeno 3 coppie di punti, ce ne sono {len(pairs)}", cause=COVERAGE_LOW)
    n = len(pairs)
    mean_x = sum(x for x, _ in pairs) / n
    mean_y = sum(y for _, y in pairs) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    den_x = sum((x - mean_x) ** 2 for x, _ in pairs)
    den_y = sum((y - mean_y) ** 2 for _, y in pairs)
    if not den_x or not den_y:
        return NotComputable(
            "una delle due serie non varia affatto: con una retta orizzontale "
            "la correlazione non e' definita", cause=NO_ANSWER)
    return Measurement(round(num / (den_x * den_y) ** 0.5, 3), unit="coefficiente",
                  coverage=n / len(a))


_register(Operation(
    name="correlazione",
    inputs=("una serie", "un'altra serie della stessa lunghezza"),
    returns=("quanto si muovono insieme, fra -1 e 1. NON dice che una "
                 "causa l'altra: la causa non e' un fatto che questo conto "
                 "possa produrre"),
    refuses_when=("l'entita' non ha statistiche in Home Assistant",
                   "le serie hanno lunghezza diversa", "le coppie sono meno di tre",
                "una delle due non varia affatto"),
    takes=(SHAPE_SERIES, SHAPE_SERIES),
    in_recipes=True,
    run=_correlation,
))
