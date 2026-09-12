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

import datetime as dt
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType

#: Sotto questa copertura un risultato di periodo diventa «non calcolabile».
#: **Scelta, non misurata** (vedi il docstring del modulo): tre quarti del
#: periodo e' il punto oltre il quale un totale «del giorno» avrebbe piu' di
#: sei ore mancanti, e sei ore mancanti sono un altro giorno. Sulla casa vera
#: non rifiuta niente per parzialita' -- l'unica serie parziale misurata sta al
#: 79%, appena sopra -- e morde sulle due serie a zero, che e' il caso per cui
#: la regola esiste.
MINIMUM_COVERAGE = 0.75

#: L'unita' che **non si sa**, detta invece che taciuta.
#:
#: `Measurement` rifiuta un'unita' vuota, e ha ragione: un numero nudo e' un
#: frammento. Ma c'e' un posto, oggi, dove l'unita' non si sa davvero --
#: l'oggetto di energia di `mind/facts.aggregate_day`, che nasce dal grezzo
#: (`mind/store.py`, tabella `cambi`), e **quella tabella non ha una colonna
#: per l'unita'**: registra `device_class`, `state_class`, `source_type`,
#: `domain`, `title`, `friendly_name`, e butta via `unit_of_measurement`, che
#: Home Assistant dichiara per ogni entita'. E' esattamente la tesi della spec
#: dei tre attori -- *«Home Assistant dichiara gia' tutto, la copia lo butta»*
#: -- su un attributo che nessuna fetta ha ancora raccolto (a backlog,
#: 12/09/2026).
#:
#: Finche' dura, qui si dice «non dichiarata» invece di inventare `kWh`: un
#: contatore di quella tabella puo' essere in Wh, in kWh o in m3, e sceglierne
#: uno sarebbe una motivazione falsa scritta accanto al codice. **Non e' un
#: permesso generico**: chi ha l'unita' la passa, e `Measurement` continua a
#: rifiutare il vuoto.
UNKNOWN_UNIT = "non dichiarata"


class Period:
    """**Su quando** si calcola: un elenco di finestre, non un intervallo solo.

    E' la decisione di disegno che le domande del proprietario hanno imposto
    (`docs/design/2026-09-11-le-domande-del-proprietario.md`). Tre domande su
    sette chiedono di restringere un calcolo ai momenti in cui qualcosa era
    vero -- *«quando si accende il riscaldamento e porta la casa in
    temperatura, poi qualcuno e' in casa o meno?»*, *«a livello di comfort la
    casa e' sana quando c'e' qualcuno in casa?»*. Con un intervallo solo
    servirebbe un'operazione in piu' per ciascuna di quelle restrizioni; con
    un elenco di finestre, `episodio` ne produce e ogni altra operazione le
    accetta: **la restrizione e' composizione**, e il registro resta piu'
    piccolo di quanto sarebbe con un'operazione dedicata per ogni restrizione.

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

    def contains(self, instant: float) -> bool:
        return any(start <= instant < end for start, end in self._windows)

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
    unita' lo dicono: `"periodo"` (`episodio`, `dentro`), `"gruppi"`
    (`raggruppa_per`), `"ora del giorno"` (`quando_succede`), `"volte"`
    (`quante_volte`), `"coefficiente"` (`correlazione`), `"frazione"`
    (`quota`). Sono **etichette di specie, non unita' di misura**, e vale la
    pena dirlo invece di lasciar credere che kWh e «gruppi» siano la stessa
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


class NotComputable(Result):
    """Un rifiuto **con la sua ragione**, e la ragione non e' facoltativa.

    La spec lo chiede alla lettera: il risultato diventa *«non calcolabile, E
    PERCHE'»*. Un rifiuto muto e' un silenzio, e un silenzio non e'
    distinguibile da un'assenza di problemi -- che e' il difetto che questo
    prodotto insegue in ogni sua parte.
    """

    __slots__ = ("_reason",)

    def __init__(self, reason: str) -> None:
        if not str(reason or "").strip():
            raise ValueError(
                "un «non calcolabile» senza ragione e' un silenzio, non una risposta")
        self._reason = str(reason).strip()

    @property
    def computable(self) -> bool:
        return False

    @property
    def reason(self) -> str:
        return self._reason

    def __eq__(self, other) -> bool:
        return type(self) is type(other) and self._reason == other._reason

    def __hash__(self) -> int:
        return hash(self._reason)

    def __repr__(self) -> str:
        return f"NotComputable({self._reason!r})"


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


#: Quale versione del registro. Le ricette vivranno piu' a lungo del registro
#: che le esegue: senza un numero, una ricetta scritta oggi e riletta fra sei
#: mesi non saprebbe dire se le operazioni che nomina siano ancora quelle.
#:
#: **Oggi nessuno lo legge, ed e' voluto**: le ricette sono la fetta 4, e il
#: numero esiste perche' la prima ricetta scritta possa gia' dichiarare contro
#: quale registro e' stata scritta. Un numero introdotto insieme al primo
#: lettore sarebbe arrivato dopo le ricette che avrebbe dovuto datare. Se la
#: fetta 4 non lo legge, questa costante e' codice morto e si cancella.
REGISTRY_VERSION = 1

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
    regola che `mind/facts._dimension_points` gia' applicava -- *«mai uno zero
    inventato»* -- e qui produce anche il numero che dice quanto manca.

    **`expected_parts` e' il denominatore vero, e chi chiama deve darlo quando lo
    sa.** Senza, la copertura dice quanto del CAMPIONE si e' letto, non quanto
    del periodo -- e i due numeri divergono proprio dove fa male: Home
    Assistant **omette** le ore senza dati dalle statistiche orarie (fatto gia'
    scritto in `mind/facts.build_balance_body`, correzione del 27/08/2026), per
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


def _reject_for_coverage(coverage: float, known: int) -> NotComputable | None:
    """Il rifiuto motivato, con **il numero dentro la frase**: «copertura 8%»
    dice a chi legge quanto mancava, mentre «non calcolabile» lo lascerebbe
    a indovinare."""
    if not known:
        return NotComputable(
            "nessun punto con un valore nel periodo: la serie e' vuota")
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
            "dello stesso tempo")
    if coverage < MINIMUM_COVERAGE:
        return NotComputable(
            f"copertura {coverage:.0%}, sotto il minimo di "
            f"{MINIMUM_COVERAGE:.0%}: un totale fatto di cosi' poche parti del "
            "periodo somiglia a un totale e non lo e'")
    return None


def _sum_period(series, *, unit: str, expected_parts: int | None = None) -> Result:
    """La somma delle parti conosciute del periodo, con la sua copertura.

    **Estratta da `mind/facts.build_balance_body`**, dove era «la somma delle
    ore CONOSCIUTE» e la copertura non usciva: un totale fatto di tre ore su
    ventiquattro aveva la stessa faccia di uno completo.
    """
    known, coverage = _known_points(series, expected_parts)
    refusal = _reject_for_coverage(coverage, len(known))
    if refusal is not None:
        return refusal
    return Measurement(round(sum(p["valore"] for p in known), 2),
                  unit=unit, coverage=coverage)


_register(Operation(
    name="somma_periodo",
    inputs=("una serie di punti con un valore", "l'unita' di quel valore",
              "quante parti il periodo doveva avere, quando chi chiama lo sa"),
    returns="il totale delle parti conosciute, con la sua unita' e la sua copertura",
    refuses_when=("la serie non ha nessun punto con un valore",
                "la copertura sta sotto il minimo"),
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
            return NotComputable(r.reason)
    if not denominator.value:
        return NotComputable(
            "il denominatore e' nullo: non e' «zero», e' una domanda senza risposta")
    try:
        value = float(numerator.value) / float(denominator.value)
    except (TypeError, ValueError, ZeroDivisionError):
        return NotComputable("i due numeri non si leggono come numeri")
    if value < 0:
        return NotComputable(
            f"il rapporto e' negativo ({value:.3f}): non si clampa a zero, "
            "perche' zero affermerebbe una cosa che non sappiamo")
    return Measurement(round(value, 3), unit="frazione",
                       coverage=min(numerator.coverage, denominator.coverage))


_register(Operation(
    name="quota",
    inputs=("la misura del numeratore", "la misura del denominatore"),
    returns=("una frazione fra 0 e 1, con la copertura peggiore delle due: "
             "un rapporto non e' piu' solido del suo termine piu' debole"),
    refuses_when=("una delle due non e' calcolabile", "il denominatore e' nullo",
                  "il rapporto sarebbe negativo"),
    run=_ratio,
))


def _difference(first: Result, second: Result) -> Result:
    """`prima - seconda`, **con la stessa unita' e la copertura peggiore**.

    Estratta dal `consumo - prelievo` di `mind/facts._balance_moments`.

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
            return NotComputable(r.reason)
    if first.unit != second.unit:
        return NotComputable(
            f"unita' diverse ({first.unit} e {second.unit}): la differenza "
            "sarebbe un numero senza significato")
    return Measurement(round(first.value - second.value, 2), unit=first.unit,
                  coverage=min(first.coverage, second.coverage))


_register(Operation(
    name="differenza_fra",
    inputs=("una misura", "un'altra misura della stessa unita'"),
    returns="la loro differenza, con la copertura peggiore delle due",
    refuses_when=("una delle due non e' calcolabile", "le unita' sono diverse"),
    run=_difference,
))


def _average_min_max(series, *, unit: str,
                   expected_parts: int | None = None) -> Result:
    """La media, il minimo e il massimo delle parti conosciute.

    Tutti e tre insieme, non uno alla volta: una media senza gli estremi
    nasconde proprio cio' che si va a cercare -- una stanza che sta bene in
    media e tocca i 14 gradi alle sei del mattino.
    """
    known, coverage = _known_points(series, expected_parts)
    refusal = _reject_for_coverage(coverage, len(known))
    if refusal is not None:
        return refusal
    values = [p["valore"] for p in known]
    return Measurement({"media": round(sum(values) / len(values), 2),
                   "minimo": min(values), "massimo": max(values)},
                  unit=unit, coverage=coverage)


_register(Operation(
    name="media_min_max",
    inputs=("una serie di punti con un valore", "l'unita' di quel valore",
              "quante parti il periodo doveva avere, quando chi chiama lo sa"),
    returns="media, minimo e massimo insieme",
    refuses_when=("la serie e' vuota", "la copertura sta sotto il minimo"),
    run=_average_min_max,
))


def _per_hour(series, *, unit: str, expected_parts: int | None = None) -> Result:
    """Il profilo: **ogni punto porta la sua ORA**, non la sua posizione.

    Correzione gia' pagata il 27/08/2026 in `mind/facts.build_balance_body`: la
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
        return NotComputable("nessun punto nel periodo: non c'e' nessun profilo")
    return Measurement([{"ora": p.get("inizio"), "valore": p.get("valore")}
                   for p in points], unit=unit, coverage=coverage)


_register(Operation(
    name="per_ora",
    inputs=("una serie di punti orari", "l'unita' dei valori",
              "quante parti il periodo doveva avere, quando chi chiama lo sa"),
    returns="il profilo, ogni punto con la sua ora",
    refuses_when=("la serie non ha nessun punto",),
    run=_per_hour,
))


def _first_last_difference(series, *, unit: str) -> Result:
    """Quanto e' salito un contatore: `ultima - prima`.

    **Estratta da `mind/facts._difference`**, ed e' il difetto fondativo di
    questa fetta: con un solo punto nel periodo, la prima e l'ultima lettura
    sono la STESSA riga, il conto tornava `0.0` -- «non e' cambiato niente»
    travestito da dato -- e fu corretto in `None` il 26/08/2026. `None` era
    meglio di zero; questo dice anche perche'.

    **Prende una SERIE**, come tutte le altre operazioni che leggono nel tempo:
    una forma sola in tutto il registro. La conversione dal grezzo -- dove un
    contatore scrive stringhe, `"1234.5"` -- avviene al confine, cioe' dove
    l'archivio si legge, non qui dentro.
    """
    known, coverage = _known_points(series)
    if not known:
        return NotComputable("nessuna lettura con un valore nel periodo")
    if len(known) < 2:
        return NotComputable(
            "c'e' un solo punto nel periodo: la prima e l'ultima lettura sono la "
            "stessa, e la differenza direbbe «non e' cambiato niente» senza saperlo")
    return Measurement(round(known[-1]["valore"] - known[0]["valore"], 2),
                  unit=unit, coverage=coverage)


_register(Operation(
    name="primo_ultimo_differenza",
    inputs=("la serie di un contatore nel periodo", "l'unita' del contatore"),
    returns="di quanto e' salito fra la prima e l'ultima",
    refuses_when=("non c'e' nessuna lettura con un valore", "ce n'e' una sola"),
    run=_first_last_difference,
))


def _episode(readings, *, is_on, period_end: float) -> Result:
    """Le finestre in cui un soggetto era «acceso»: **un `Period`**.

    Estratta dal ciclo apri/chiudi di `mind/facts.aggregate_day`. Restituisce
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
        return NotComputable("nessun episodio nel periodo: non si e' mai acceso")
    return Measurement(Period(windows), unit="periodo", coverage=1.0)


_register(Operation(
    name="episodio",
    inputs=("le letture di un soggetto", "come si riconosce un riposo",
              "la fine del periodo"),
    returns="le finestre in cui era acceso, come un periodo",
    refuses_when=("non si e' mai acceso nel periodo",),
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
    run=_time_in_state,
))


def _how_many_times(period: Period) -> Result:
    """Quante volte e' cominciato: **le finestre, non le letture**.

    Contare le letture darebbe un numero enorme e falso -- gli otto termostati
    di questa casa producevano 6.446 righe al giorno per otto cambi veri
    (misurato il 10/09/2026).
    """
    return Measurement(len(period.windows), unit="volte", coverage=1.0)


_register(Operation(
    name="quante_volte",
    inputs=("un periodo",),
    returns="quante volte e' cominciato",
    refuses_when=("il periodo non esiste",),
    run=_how_many_times,
))


def _when_it_happens(period: Period, *, zone: dt.tzinfo) -> Result:
    """A che ore del giorno comincia, **sul fuso della casa**.

    Serve alla domanda 1 del proprietario -- *«quando si accende il
    riscaldamento...»* -- e alla 4bis, sulle automazioni
    (`docs/design/2026-09-11-le-domande-del-proprietario.md`, dove la glossa
    della tabella la chiama «a che ora capita di solito»). L'ora si legge sul
    fuso della CASA e non su quello di chi guarda: un riscaldamento che parte
    «alle 15:30» letto in UTC diventa «alle 13:30», e la risposta varrebbe per
    un'altra casa.

    **Il fuso arriva GIA' RISOLTO, come oggetto**, e non come la stringa
    `"Europe/Rome"`: risolverlo qui vorrebbe dire importare
    `home_space.historian`, cioe' far conoscere la casa a un modulo che deve
    saper calcolare e basta. E' la stessa regola che `raggruppa_per` applica
    alla chiave d'un gruppo -- il registro non sa cos'e' un piano, e non sa
    nemmeno dove sta la casa. Chi chiama traduce, con `home_space_zone`.
    """
    hours = sorted({dt.datetime.fromtimestamp(start, zone).hour
                  for start, _ in period.windows})
    return Measurement(hours, unit="ora del giorno", coverage=1.0)


_register(Operation(
    name="quando_succede",
    inputs=("un periodo", "il fuso della casa, gia' risolto in un oggetto"),
    returns="le ore del giorno in cui comincia",
    refuses_when=("il periodo non esiste",),
    run=_when_it_happens,
))


def _measurements_in_period(readings, *, period: Period, unit: str) -> Result:
    """Cosa ha fatto una grandezza **mentre** il periodo durava: la serie
    ristretta a quelle finestre.

    Estratta dalle `measurements` dei comprimari di `mind/facts.aggregate_day`, dove
    la regola era gia' scritta: una misura presa PRIMA che l'episodio
    cominciasse e' il clima di prima, non l'effetto di quell'episodio.

    **Restituisce una SERIE, non «da 18 a 21».** La prima stesura tornava i due
    estremi, e il cancello delle sette domande ha fatto emergere che cosi' non
    si componeva con niente: `media_min_max` e `primo_ultimo_differenza`
    restavano orfane perche' parlavano un'altra forma. Restituendo la serie
    ristretta, la domanda 1 ci mette sopra `primo_ultimo_differenza` (di quanto
    e' salita) e la 4 `media_min_max` (com'e' stata mentre c'era qualcuno) --
    ed e' la stessa composizione, non due.
    """
    inside = [(t, v) for t, v in (readings or []) if period.contains(float(t))]
    if not inside:
        return NotComputable(
            "nessuna misura dentro le finestre del periodo: la grandezza non e' "
            "stata osservata mentre succedeva")
    points = []
    for instant, value in inside:
        try:
            points.append({"inizio": float(instant), "valore": float(value)})
        except (TypeError, ValueError):
            points.append({"inizio": float(instant), "valore": None})
    if all(p["valore"] is None for p in points):
        return NotComputable("le misure non si leggono come numeri")
    return Measurement(points, unit=unit,
                  coverage=sum(p["valore"] is not None for p in points) / len(points))


_register(Operation(
    name="misure_durante",
    inputs=("le letture di una grandezza", "un periodo", "l'unita'"),
    returns="la serie ristretta alle finestre del periodo",
    refuses_when=("non c'e' nessuna misura dentro le finestre",
                "le misure non sono numeri"),
    run=_measurements_in_period,
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
            return NotComputable(r.reason)
    if first.unit != later.unit:
        return NotComputable(
            f"unita' diverse ({first.unit} e {later.unit}): i due periodi non "
            "misurano la stessa cosa")
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
    known, coverage = _known_points(series)
    if len(known) < 3:
        return NotComputable(
            f"servono almeno 3 punti per una tendenza, ce ne sono {len(known)}: "
            "due fanno sempre una retta perfetta, e non e' una tendenza")
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
    refuses_when=("i punti con un valore sono meno di tre",),
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
            "che non parla di niente")
    pairs = [(x, y) for x, y in zip(a, b, strict=True)
              if x is not None and y is not None]
    if len(pairs) < 3:
        return NotComputable(
            f"servono almeno 3 coppie di punti, ce ne sono {len(pairs)}")
    n = len(pairs)
    mean_x = sum(x for x, _ in pairs) / n
    mean_y = sum(y for _, y in pairs) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    den_x = sum((x - mean_x) ** 2 for x, _ in pairs)
    den_y = sum((y - mean_y) ** 2 for _, y in pairs)
    if not den_x or not den_y:
        return NotComputable(
            "una delle due serie non varia affatto: con una retta orizzontale "
            "la correlazione non e' definita")
    return Measurement(round(num / (den_x * den_y) ** 0.5, 3), unit="coefficiente",
                  coverage=n / len(a))


_register(Operation(
    name="correlazione",
    inputs=("una serie", "un'altra serie della stessa lunghezza"),
    returns=("quanto si muovono insieme, fra -1 e 1. NON dice che una "
                 "causa l'altra: la causa non e' un fatto che questo conto "
                 "possa produrre"),
    refuses_when=("le serie hanno lunghezza diversa", "le coppie sono meno di tre",
                "una delle due non varia affatto"),
    run=_correlation,
))


def _sum_entities(measurements) -> Result:
    """Piu' entita' in un totale solo.

    Nasce dalla domanda 5: *«dammi il totale delle ore irrigate»* -- tutte le
    zone insieme.

    **Chi non si e' potuto calcolare non sparisce: paga sulla copertura.** Una
    somma che ignorasse in silenzio una zona senza dati direbbe un totale piu'
    piccolo con la faccia di uno completo.

    **La copertura e' una frazione sola, non due moltiplicate.** La prima
    stesura faceva `min(copertura) * quota di entita' calcolabili`: chi leggeva
    0,6 non poteva sapere se fosse 0,9 di tempo su due terzi delle zone o 0,6
    di tempo su tutte -- due cose diverse dette con un numero solo, che e'
    esattamente il difetto che questo progetto insegue. Adesso ogni entita'
    porta la SUA copertura e chi manca porta zero: la somma di quelle, divisa
    per quante erano, e' *«quanta parte di cio' che serviva si e' avuta»* --
    la definizione che la spec da' alla parola (§6), una sola.
    """
    all_given = list(measurements or [])
    if not all_given:
        return NotComputable("nessuna entita' da sommare")
    computables = [m for m in all_given if m.computable]
    if not computables:
        return NotComputable(
            "nessuna delle entita' e' calcolabile: il totale sarebbe uno zero "
            "che non significa zero")
    unit = {m.unit for m in computables}
    if len(unit) > 1:
        return NotComputable(
            f"unita' diverse fra le entita' ({', '.join(sorted(unit))}): "
            "sommarle produrrebbe un numero senza significato")
    return Measurement(round(sum(m.value for m in computables), 2),
                  unit=computables[0].unit,
                  coverage=sum(m.coverage for m in computables) / len(all_given))


_register(Operation(
    name="somma_entita",
    inputs=("le misure di piu' entita', della stessa unita'",),
    returns="il loro totale, con la copertura che paga chi manca",
    refuses_when=("non c'e' nessuna entita'", "nessuna e' calcolabile",
                "le unita' sono diverse"),
    run=_sum_entities,
))


def _average_entities(measurements) -> Result:
    """La media fra piu' entita', non la loro somma.

    Nasce dalla domanda 6 -- *«dammi il livello di CO2 di tutto il piano
    terra»* -- e nasce da un difetto trovato in revisione il 12/09/2026:
    `raggruppa_per` riduceva ogni gruppo con `somma_entita`, e il piano terra
    rispondeva **900 ppm** sommando 400 e 500. La somma di due concentrazioni
    non e' una concentrazione: e' un numero senza significato con un'unita'
    accanto, cioe' la prima fondamenta rotta dentro l'operazione che doveva
    difenderla.

    Stesse regole di `somma_entita`: le unita' devono coincidere, chi non e'
    calcolabile paga sulla copertura invece di sparire.
    """
    all_given = list(measurements or [])
    if not all_given:
        return NotComputable("nessuna entita' di cui fare la media")
    computables = [m for m in all_given if m.computable]
    if not computables:
        return NotComputable(
            "nessuna delle entita' e' calcolabile: la media sarebbe uno zero "
            "che non significa zero")
    unit = {m.unit for m in computables}
    if len(unit) > 1:
        return NotComputable(
            f"unita' diverse fra le entita' ({', '.join(sorted(unit))}): "
            "la loro media non misurerebbe niente")
    return Measurement(round(sum(m.value for m in computables) / len(computables), 2),
                  unit=computables[0].unit,
                  coverage=sum(m.coverage for m in computables) / len(all_given))


_register(Operation(
    name="media_entita",
    inputs=("le misure di piu' entita', della stessa unita'",),
    returns="la loro media, con la copertura che paga chi manca",
    refuses_when=("non c'e' nessuna entita'", "nessuna e' calcolabile",
                "le unita' sono diverse"),
    run=_average_entities,
))


def _group_by(measurements: dict, *, key, reduce: str) -> Result:
    """Le entita' messe insieme per una chiave -- un'area, un piano, un tipo.

    Nasce dalla domanda 6: *«dammi il livello di CO2 di tutto il piano
    terra»*. «Tutto il piano terra» non e' un elenco di entita': e' un ramo
    dell'anagrafe, e **la chiave arriva da fuori** -- questo modulo non sa
    cos'e' un piano e non deve impararlo, o il registro comincerebbe a
    conoscere la casa.

    **Chi non ha chiave resta fuori, e non finisce in un gruppo «altro»**: un
    gruppo inventato comparirebbe in un totale che nessuno ha chiesto. Quanti
    siano rimasti fuori lo dice la copertura.

    **Come si riduce un gruppo lo dice chi chiama, e non c'e' un valore per
    difetto.** La prima stesura riduceva sempre con `somma_entita`, e il piano
    terra rispondeva 900 ppm sommando due concentrazioni (trovato in revisione
    il 12/09/2026). Un difetto del genere non si cura scegliendo meglio il
    valore per difetto: si cura togliendolo, perche' sommare e mediare sono
    due domande diverse e nessuna delle due e' «quella normale».
    """
    entities = dict(measurements or {})
    groups: dict[str, list] = {}
    keyless = 0
    for name, measurement in entities.items():
        k = key(name)
        if k is None:
            keyless += 1
            continue
        groups.setdefault(k, []).append(measurement)
    if not groups:
        return NotComputable("nessuna entita' ha una chiave per cui raggrupparla")
    riduttore = _REGISTRY.get(reduce)
    if riduttore is None:
        return NotComputable(
            f"«{reduce}» non e' un'operazione del registro: non c'e' modo di "
            "ridurre i gruppi")
    reduced = {k: riduttore.run(v) for k, v in groups.items()}
    coverage = 1.0 - keyless / len(entities) if entities else 1.0
    return Measurement(reduced, unit="gruppi", coverage=coverage)


_register(Operation(
    name="raggruppa_per",
    inputs=("le misure per entita'", "una funzione che dice a che gruppo appartiene",
            "il nome dell'operazione che riduce ogni gruppo"),
    returns=("un risultato per gruppo -- ridotto come ha chiesto chi chiama -- "
             "e la copertura paga chi non aveva chiave"),
    refuses_when=("nessuna entita' ha una chiave",
                  "l'operazione che dovrebbe ridurre i gruppi non esiste"),
    run=_group_by,
))


def _within(period: Period, limit: Period) -> Result:
    """Il pezzo di un periodo che cade **dentro** un altro.

    **Nata dal cancello, e contro la mia previsione.** Il documento delle
    domande (11/09/2026) diceva che restringere un calcolo «ai momenti in cui
    qualcosa era vero» sarebbe stata composizione e non un mattone in piu', se
    il periodo fosse un elenco di finestre. E' vero per una MISURA --
    `misure_durante` prende le letture e un periodo -- ma non per un PERIODO:
    *«quanto ha scaldato mentre qualcuno era in casa»* incrocia due periodi, e
    quella e' una forma che nessun'altra operazione aveva.

    L'ha trovata la prova delle sette domande, che e' esattamente il mestiere
    per cui quel cancello esiste: la previsione era scritta, ed era sbagliata.

    Restituisce un periodo, quindi si compone: `tempo_in_stato` lo misura,
    `quante_volte` lo conta, `quando_succede` lo colloca.
    """
    windows = []
    for start, end in period.windows:
        for other_start, other_end in limit.windows:
            overlap_start = max(start, other_start)
            overlap_end = min(end, other_end)
            if overlap_end > overlap_start:
                windows.append((overlap_start, overlap_end))
    if not windows:
        return NotComputable(
            "i due periodi non si sovrappongono mai: non c'e' nessun pezzo in comune")
    return Measurement(Period(windows), unit="periodo", coverage=1.0)


_register(Operation(
    name="dentro",
    inputs=("un periodo", "il periodo a cui restringerlo"),
    returns="il pezzo del primo che cade dentro il secondo, come un periodo",
    refuses_when=("i due periodi non si sovrappongono mai",),
    run=_within,
))
