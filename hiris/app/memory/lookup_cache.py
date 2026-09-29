"""La cache dell'INDICE (Task B7) -- vive quanto il processo, non quanto la
chiamata.

Perche' un file suo, e non dentro `resolver.py`: `costruisci_indice()` e'
dichiarata PURA nel suo stesso docstring -- stessi argomenti, stesso
risultato, nessuno stato che sopravvive alla chiamata -- ed e' la proprieta'
su cui poggiano i test di B3/B4/B5. Una cache e' l'opposto per natura: STATO
che sopravvive fra le chiamate e puo' mentire se la chiave sbaglia. Tenerle
nello stesso file avrebbe reso "`costruisci_indice` e' ancora pura?" una
domanda che richiede di leggere anche una classe stateful per rispondere. Qui
`LookupCache` CHIAMA `costruisci_indice()`, non la sostituisce e non la
modifica: nessuna riga di questo file cambia cosa contiene un `Lookup`.

`ToolDispatcher` nasce a OGNI turno (`handlers_chat.py:76`, per design:
senza un dispatcher per-chiamata i runner degradano ogni tool a un errore
"non disponibile"). Una cache sull'istanza del dispatcher aiuterebbe solo
DENTRO un turno -- il caso vero misurato (`cerca` chiamato quattro volte per
le abat-jour) e' esattamente questo, ma non basta: `LookupCache` e' pensata
per essere costruita UNA VOLTA, accanto a `entity_cache`
(`hiris/app/server.py`), e passata al dispatcher come dipendenza a ogni
turno -- cosi' il riuso vale anche FRA i turni, non solo dentro uno.

## La chiave

Chi chiama `get_lazy()` porta due cose:

- `slot`: un'etichetta che identifica IL CHIAMANTE (`"ricorda"`), non il
  contenuto. Fino al 29/09/2026 gli spazi erano due: c'era anche `"cerca"`,
  la vecchia ricerca per nome, che passava i nomi vivi di ripiego e il
  comportamento (automazioni e script) e voleva quindi un indice diverso
  sulla stessa casa. La porta della casa (`home_space/house_query.py`)
  confronta i nomi da se', e con lo spazio sono usciti la sua chiave (i nomi
  di ripiego, per impronta del contenuto; la data del comportamento) e il
  metodo `get()` che lo serviva. L'etichetta resta: e' cio' che impedisce a
  un secondo chiamante di ricevere l'indice di un altro.
- `aggiornata_il`: la data dell'ultima ricostruzione dell'anagrafe
  (`HomeSpaceStore.aggiornata_il()`), o `None` quando l'anagrafe non e' mai
  stata letta. `_remember` decide `casa={}` esattamente quando questo valore
  e' `None` (vedi `tools.py::_remember`): passare lo STESSO valore letto
  una volta sola alla decisione e alla chiave fa si' che "anagrafe non letta"
  e "anagrafe letta ma vuota" non si confondano mai, senza bisogno di un
  terzo campo esplicito.

## La forma della cache: una voce per spazio

`_voci` e' un dizionario per `slot`: ogni spazio tiene la SUA ultima voce
(chiave di frescura + `Lookup`), sovrascritta quando la chiave cambia. Non
c'e' scadenza a tempo: l'unico motivo di ricostruzione e' che la chiave sia
cambiata, e la dimensione resta limitata al numero di spazi distinti che
esistono nel codice (oggi uno), non alla storia di quante volte l'anagrafe
e' cambiata durante l'uptime del processo.

## Concorrenza

Il processo e' asincrono a thread singolo; il lavoratore del ponte gira
in-processo sullo stesso event loop (nessun `threading.Thread` ne'
`ThreadPoolExecutor` fra `ToolDispatcher` e il ponte -- verificato con
grep su `hiris/app/`). `get_lazy()` non contiene nessun `await`: legge e
scrive `_voci` in un'unica porzione di codice sincrona, quindi non puo' mai
essere interrotta a meta' da un'altra coroutine. Il caso peggiore e'
costruire lo stesso indice due volte (due `get_lazy()` con la stessa chiave
schedulate senza mai cedere il controllo fra l'una e l'altra non possono
comunque accadere in un ciclo a thread singolo prima che la prima abbia
scritto `_voci`) -- MAI servirne uno mezzo fatto. Se un giorno un `await`
finisse fra la lettura della chiave e la scrittura della voce, questa
garanzia cadrebbe: e' per questo che `costruisci_indice()` (sincrona, niente
I/O) resta l'unica cosa che gira fra le due.
"""
from __future__ import annotations

from .resolver import Lookup, costruisci_indice


class LookupCache:
    """Un `Lookup` per spazio, riusato finche' la sua chiave non cambia.

    Si costruisce una volta (accanto a `entity_cache`, in
    `hiris/app/server.py`) e si passa a `ToolDispatcher` come
    dipendenza. Non ha altro stato che `_voci`: nessuna scadenza a tempo,
    nessuna dimensione massima diversa dal numero di spazi distinti.
    """

    def __init__(self) -> None:
        self._voci: dict[str, tuple[str | None, Lookup]] = {}

    def get_lazy(self, slot: str, build_home_space,
                 aggiornata_il: str | None) -> Lookup:
        """Il `Lookup` per questo `slot`, ricostruito solo se la chiave e'
        cambiata; la casa si legge SOLO su un miss.

        Fix della review indipendente del Task B7: `_remember` non ha bisogno
        di `HomeSpaceStore.leggi()` per decidere se il colpo va a segno -- la
        chiave si calcola senza. `build_home_space` (un callable a zero
        argomenti, non un valore gia' letto) si invoca solo quando la voce
        salvata non e' piu' valida: su un hit non viene MAI chiamato, e la
        lettura non si paga. `costruisci_indice()` non e' chiamata affatto
        quando la voce e' ancora valida: e' li' che sta il guadagno."""
        entry = self._voci.get(slot)
        if entry is not None and entry[0] == aggiornata_il:
            return entry[1]
        lookup = costruisci_indice(build_home_space())
        self._voci[slot] = (aggiornata_il, lookup)
        return lookup
