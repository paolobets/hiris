"""La cache dell'INDICE (Task B7) -- vive quanto il processo, non quanto la
chiamata.

Perche' un file suo, e non dentro `riconoscitore.py`: `costruisci_indice()` e'
dichiarata PURA nel suo stesso docstring -- stessi argomenti, stesso
risultato, nessuno stato che sopravvive alla chiamata -- ed e' la proprieta'
su cui poggiano i test di B3/B4/B5. Una cache e' l'opposto per natura: STATO
che sopravvive fra le chiamate e puo' mentire se la chiave sbaglia. Tenerle
nello stesso file avrebbe reso "`costruisci_indice` e' ancora pura?" una
domanda che richiede di leggere anche una classe stateful per rispondere. Qui
`CacheIndice` CHIAMA `costruisci_indice()`, non la sostituisce e non la
modifica: nessuna riga di questo file cambia cosa contiene un `Indice`.

`DispatcherStrumenti` nasce a OGNI turno (`handlers_chat.py:76`, per design:
senza un dispatcher per-chiamata i runner degradano ogni tool a un errore
"non disponibile"). Una cache sull'istanza del dispatcher aiuterebbe solo
DENTRO un turno -- il caso vero misurato (`cerca` chiamato quattro volte per
le abat-jour) e' esattamente questo, ma non basta: `CacheIndice` e' pensata
per essere costruita UNA VOLTA, accanto a `entity_cache`
(`hiris/app/server.py`), e passata al dispatcher come dipendenza a ogni
turno -- cosi' il riuso vale anche FRA i turni, non solo dentro uno.

## La chiave

Chi chiama `ottieni()` porta tre cose:

- `spazio`: un'etichetta che identifica IL CHIAMANTE (`"cerca"`, `"ricorda"`),
  non il contenuto. `_cerca` passa `nomi_di_ripiego`, `_ricorda` no: sulla
  stessa identica casa i due indici hanno contenuti diversi, quindi devono
  restare due voci -- e usare il chiamante come discriminante, invece di
  sperare che il contenuto differisca sempre, e' cio' che lo garantisce anche
  nel caso limite in cui `nomi_di_ripiego` di `_cerca` sia vuoto (specchio
  giu').
- `aggiornata_il`: la data dell'ultima ricostruzione dell'anagrafe
  (`ArchivioCasa.aggiornata_il()`), o `None` quando l'anagrafe non e' mai
  stata letta. `_ricorda` decide `casa={}` esattamente quando questo valore
  e' `None` (vedi `strumenti.py::_ricorda`): passare lo STESSO valore letto
  una volta sola alla decisione e alla chiave fa si' che "anagrafe non letta"
  e "anagrafe letta ma vuota" non si confondano mai, senza bisogno di un
  terzo campo esplicito.
- `nomi_di_ripiego`: i nomi vivi di ripiego (entity_id -> friendly_name), che
  cambiano piu' spesso dell'anagrafe (un'entita' nuova, un friendly_name
  cambiato in Home Assistant). La chiave non usa la LORO LUNGHEZZA -- due
  dizionari diversi possono avere lo stesso numero di voci, e una chiave che
  non li distingue servirebbe un indice vecchio: il difetto esatto per cui
  questo task esiste. Usa un'impronta del CONTENUTO (`_impronta_nomi`).

## La forma della cache: una voce per spazio, non una sola casella

Una sola casella condivisa rimbalzerebbe fra `_cerca` e `_ricorda` -- due
chiamanti diversi nello stesso turno la ricostruirebbero a vicenda, e il
guadagno sparirebbe senza che un test che guarda solo i risultati se ne
accorga. `_voci` e' un dizionario per `spazio`: ogni spazio tiene la SUA
ultima voce (chiave di frescura + `Indice`), sovrascritta quando la chiave
cambia. Non c'e' scadenza a tempo: l'unico motivo di ricostruzione e' che la
chiave sia cambiata, e la dimensione resta comunque limitata al numero di
spazi distinti che esistono nel codice (oggi due), non alla storia di quante
volte l'anagrafe e' cambiata durante l'uptime del processo.

## Concorrenza

Il processo e' asincrono a thread singolo; il lavoratore del ponte gira
in-processo sullo stesso event loop (nessun `threading.Thread` ne'
`ThreadPoolExecutor` fra `DispatcherStrumenti` e il ponte -- verificato con
grep su `hiris/app/`). `ottieni()` non contiene nessun `await`: legge e
scrive `_voci` in un'unica porzione di codice sincrona, quindi non puo' mai
essere interrotta a meta' da un'altra coroutine. Il caso peggiore e'
costruire lo stesso indice due volte (due `ottieni()` con la stessa chiave
schedulate senza mai cedere il controllo fra l'una e l'altra non possono
comunque accadere in un ciclo a thread singolo prima che la prima abbia
scritto `_voci`) -- MAI servirne uno mezzo fatto. Se un giorno un `await`
finisse fra la lettura della chiave e la scrittura della voce, questa
garanzia cadrebbe: e' per questo che `costruisci_indice()` (sincrona, niente
I/O) resta l'unica cosa che gira fra le due.
"""
from __future__ import annotations

import hashlib

from .riconoscitore import Indice, costruisci_indice


def _impronta_nomi(nomi: dict[str, str] | None) -> str:
    """Un'impronta del CONTENUTO di `nomi` (entity_id -> friendly_name), non
    della sua lunghezza -- vedi il docstring del modulo. `None` e `{}` danno
    la stessa impronta, coerente con `costruisci_indice`, che tratta
    `nomi_di_ripiego or {}` allo stesso modo.

    sha256 su un materiale ordinato (le chiavi di un dict non hanno un ordine
    garantito attraverso letture diverse allo stesso contenuto logico, in
    generale): ordinare prima di concatenare rende l'impronta stabile per lo
    stesso contenuto, indipendentemente dall'ordine di inserimento.
    """
    if not nomi:
        return "vuoto"
    materiale = "\x00".join(f"{k}\x01{v}" for k, v in sorted(nomi.items()))
    return hashlib.sha256(materiale.encode("utf-8")).hexdigest()


class CacheIndice:
    """Un `Indice` per spazio, riusato finche' la sua chiave non cambia.

    Si costruisce una volta (accanto a `entity_cache`, in
    `hiris/app/server.py`) e si passa a `DispatcherStrumenti` come
    dipendenza. Non ha altro stato che `_voci`: nessuna scadenza a tempo,
    nessuna dimensione massima diversa dal numero di spazi distinti.
    """

    def __init__(self) -> None:
        self._voci: dict[str, tuple[tuple, Indice]] = {}

    def ottieni(self, spazio: str, casa: dict,
               aggiornata_il: str | None,
               nomi_di_ripiego: dict[str, str] | None = None) -> Indice:
        """L'`Indice` per questo `spazio`, ricostruito solo se la chiave e'
        cambiata rispetto all'ultima voce salvata per questo stesso spazio.

        `costruisci_indice()` non e' chiamata affatto quando la voce e'
        ancora valida: e' li' che sta il guadagno, non in un accesso al
        dizionario piu' veloce di un altro.

        Vuole `casa` gia' letta: usalo quando il chiamante ha comunque
        bisogno del valore anche fuori dall'indice (`_cerca`, per
        `_cecita()`) -- li' non c'e' niente da rimandare. Se invece la
        lettura serve SOLO a costruire l'indice, vedi `ottieni_pigro()`."""
        return self.ottieni_pigro(spazio, lambda: casa, aggiornata_il, nomi_di_ripiego)

    def ottieni_pigro(self, spazio: str, costruisci_casa,
                      aggiornata_il: str | None,
                      nomi_di_ripiego: dict[str, str] | None = None) -> Indice:
        """Come `ottieni()`, ma la casa si legge SOLO su un miss.

        Fix della review indipendente del Task B7: `_ricorda` non ha bisogno
        di `ArchivioCasa.leggi()` per decidere se il colpo va a segno -- la
        chiave (`aggiornata_il` + impronta dei nomi) si calcola senza. Prima
        di questo fix `_ricorda` chiamava `leggi()` PRIMA di sapere se la
        cache avrebbe dato un colpo a segno: su un hit, una lettura SQL vera
        (piu' un `json.loads` per riga) veniva fatta e buttata -- uno dei DUE
        costi che il brief del task nominava esplicitamente (lettura
        dell'archivio E compilazione), di cui questo spazio ne eliminava solo
        uno. `costruisci_casa` (un callable a zero argomenti, non un valore
        gia' letto) si invoca solo quando la voce salvata non e' piu' valida:
        su un hit non viene MAI chiamato, e la lettura non si paga."""
        chiave = (aggiornata_il, _impronta_nomi(nomi_di_ripiego))
        voce = self._voci.get(spazio)
        if voce is not None and voce[0] == chiave:
            return voce[1]
        indice = costruisci_indice(costruisci_casa(), nomi_di_ripiego)
        self._voci[spazio] = (chiave, indice)
        return indice
