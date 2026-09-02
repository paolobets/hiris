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

Chi chiama `get()` porta tre cose:

- `slot`: un'etichetta che identifica IL CHIAMANTE (`"cerca"`, `"ricorda"`),
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
  questo task esiste. Usa un'impronta del CONTENUTO (`_fingerprint_nomi`).
- `behavior_loaded_at` (T7, R2 -- docs/design/2026-08-20-i-riferimenti.md):
  la data dell'ultima rilettura di automazioni/script
  (`ArchivioCasa.comportamento_letto_il()`), o `None` quando non e' mai stata
  letta. Da quando `costruisci_indice()` indicizza anche il comportamento
  (parametro `comportamento`), la chiave non puo' piu' bastarsi con
  `aggiornata_il`: quella data e' dell'ANAGRAFE (aree, entita', dispositivi,
  piani) e cambia con una cadenza diversa dal comportamento (giorni contro
  mesi, `ArchivioCasa.sostituisci_comportamento`, docstring). Senza questa
  voce, un'automazione rinominata in Home Assistant non invaliderebbe MAI la
  cache -- lo stesso indice vecchio, con l'automazione ancora sotto il nome
  di ieri, servirebbe finche' l'anagrafe (non il comportamento) non cambia
  anche lei: potrebbe non succedere mai in un turno.

## La forma della cache: una voce per spazio, non una sola casella

Una sola casella condivisa rimbalzerebbe fra `_cerca` e `_ricorda` -- due
chiamanti diversi nello stesso turno la ricostruirebbero a vicenda, e il
guadagno sparirebbe senza che un test che guarda solo i risultati se ne
accorga. `_voci` e' un dizionario per `slot`: ogni spazio tiene la SUA
ultima voce (chiave di frescura + `Lookup`), sovrascritta quando la chiave
cambia. Non c'e' scadenza a tempo: l'unico motivo di ricostruzione e' che la
chiave sia cambiata, e la dimensione resta comunque limitata al numero di
spazi distinti che esistono nel codice (oggi due), non alla storia di quante
volte l'anagrafe e' cambiata durante l'uptime del processo.

## Concorrenza

Il processo e' asincrono a thread singolo; il lavoratore del ponte gira
in-processo sullo stesso event loop (nessun `threading.Thread` ne'
`ThreadPoolExecutor` fra `ToolDispatcher` e il ponte -- verificato con
grep su `hiris/app/`). `get()` non contiene nessun `await`: legge e
scrive `_voci` in un'unica porzione di codice sincrona, quindi non puo' mai
essere interrotta a meta' da un'altra coroutine. Il caso peggiore e'
costruire lo stesso indice due volte (due `get()` con la stessa chiave
schedulate senza mai cedere il controllo fra l'una e l'altra non possono
comunque accadere in un ciclo a thread singolo prima che la prima abbia
scritto `_voci`) -- MAI servirne uno mezzo fatto. Se un giorno un `await`
finisse fra la lettura della chiave e la scrittura della voce, questa
garanzia cadrebbe: e' per questo che `costruisci_indice()` (sincrona, niente
I/O) resta l'unica cosa che gira fra le due.
"""
from __future__ import annotations

import hashlib

from .resolver import Lookup, costruisci_indice


def _fingerprint_nomi(nomi: dict[str, str] | None) -> str:
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


class LookupCache:
    """Un `Lookup` per spazio, riusato finche' la sua chiave non cambia.

    Si costruisce una volta (accanto a `entity_cache`, in
    `hiris/app/server.py`) e si passa a `ToolDispatcher` come
    dipendenza. Non ha altro stato che `_voci`: nessuna scadenza a tempo,
    nessuna dimensione massima diversa dal numero di spazi distinti.
    """

    def __init__(self) -> None:
        self._voci: dict[str, tuple[tuple, Lookup]] = {}

    def get(self, slot: str, home_space: dict,
               aggiornata_il: str | None,
               nomi_di_ripiego: dict[str, str] | None = None,
               behavior: list[dict] | None = None,
               behavior_loaded_at: str | None = None) -> Lookup:
        """Il `Lookup` per questo `slot`, ricostruito solo se la chiave e'
        cambiata rispetto all'ultima voce salvata per questo stesso spazio.

        `costruisci_indice()` non e' chiamata affatto quando la voce e'
        ancora valida: e' li' che sta il guadagno, non in un accesso al
        dizionario piu' veloce di un altro.

        Vuole `casa` gia' letta: usalo quando il chiamante ha comunque
        bisogno del valore anche fuori dall'indice (`_cerca`, per
        `_cecita()`) -- li' non c'e' niente da rimandare. Se invece la
        lettura serve SOLO a costruire l'indice, vedi `get_lazy()`.

        `comportamento`/`behavior_loaded_at` (T7, R2): automazioni e
        script da indicizzare, e la data della loro ultima lettura -- vedi
        "## La chiave" sopra per perche' la seconda non e' opzionale quando
        si passa la prima."""
        return self.get_lazy(slot, lambda: home_space, aggiornata_il, nomi_di_ripiego,
                                  behavior, behavior_loaded_at)

    def get_lazy(self, slot: str, build_home_space,
                      aggiornata_il: str | None,
                      nomi_di_ripiego: dict[str, str] | None = None,
                      behavior: list[dict] | None = None,
                      behavior_loaded_at: str | None = None) -> Lookup:
        """Come `get()`, ma la casa si legge SOLO su un miss.

        Fix della review indipendente del Task B7: `_ricorda` non ha bisogno
        di `ArchivioCasa.leggi()` per decidere se il colpo va a segno -- la
        chiave (`aggiornata_il` + impronta dei nomi) si calcola senza. Prima
        di questo fix `_ricorda` chiamava `leggi()` PRIMA di sapere se la
        cache avrebbe dato un colpo a segno: su un hit, una lettura SQL vera
        (piu' un `json.loads` per riga) veniva fatta e buttata -- uno dei DUE
        costi che il brief del task nominava esplicitamente (lettura
        dell'archivio E compilazione), di cui questo spazio ne eliminava solo
        uno. `build_home_space` (un callable a zero argomenti, non un valore
        gia' letto) si invoca solo quando la voce salvata non e' piu' valida:
        su un hit non viene MAI chiamato, e la lettura non si paga.

        `comportamento` NON e' pigro come `build_home_space`: e' un valore gia'
        letto, passato dal chiamante (`_cerca`, che lo legge comunque per
        indicizzarlo). Solo `_ricorda` non lo passa affatto (`None`, il
        comportamento non e' un tipo di ancora -- vedi
        `memoria/interpretazione.VOCABULARY`), e su quello spazio la sua
        assenza dalla chiave non cambia nulla: non essendo mai indicizzato,
        non puo' mai andare stantio."""
        key = (aggiornata_il, behavior_loaded_at, _fingerprint_nomi(nomi_di_ripiego))
        entry = self._voci.get(slot)
        if entry is not None and entry[0] == key:
            return entry[1]
        lookup = costruisci_indice(build_home_space(), nomi_di_ripiego, behavior)
        self._voci[slot] = (key, lookup)
        return lookup
