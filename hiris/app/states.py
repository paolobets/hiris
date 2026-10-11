"""Il vocabolario degli stati: le parole con cui le tre code -- le promesse,
le costruzioni, le proposte da fare a mano -- dicono a che punto e' una
cosa, e la frase con cui ciascuna si legge.

**Una casa sola** (Tappa 8, D4 (a), decisa dal proprietario l'08/10/2026).
Fino a quel giorno ogni coda aveva le sue parole: «in attesa» si scriveva
`in_attesa` in promesse e costruzioni e `attesa` nelle proposte; il «no» di
chi decide era `disdetta` in promesse e costruzioni e `rifiutata` nelle
proposte, mentre su una costruzione `rifiutata` voleva dire «non sono
riuscito a scriverla». La pagina Costruzioni disegna le due code insieme, e
la stessa parola cambiava faccia da una riga all'altra. Le parole sono
quelle delle promesse; le altre due code sono state migrate sui dati
(`mind/store._MIGRATION_15_STEPS`, `revisions._migration_7`).

**Ogni coda tiene le sue parole esclusive** (`mantenuta`, `applicata`,
`incerta`, `fatta_fuori`...), ma le compone da qui: un archivio non scrive
uno stato che questo modulo non conosce. Lo pretende
`tests/test_stati_vocabolario.py`, che chiede gli stati agli archivi e
pretende che ognuno stia qui con la sua frase.

**La frase leggibile** e' cio' che una persona legge al posto della parola
dell'archivio: la pagina la riceve dalla rotta (`stato_leggibile`, C-10) e
non tiene una sua tabella; il modello la riceve dentro un rifiuto, al posto
della parola grezza (C-54). E' minuscola perche' entra anche in mezzo a una
frase; chi la mette in testa a un'etichetta alza la prima lettera.

Restano fuori, dichiarati (D4): la coda del ponte (`pending`, `decided`...,
un contratto interno in inglese, `reasoning/queue.py`), i tentativi
dell'osservatore (`mind/store.ATTEMPT_*`, vincolati dal loro `CHECK`), gli
esiti di un turno (`steering.py`) e lo stato derivato del «Rifalla».

Foglia: non importa niente del prodotto, e lo importano tutti.
"""
from __future__ import annotations

# --- I significati condivisi -------------------------------------------------

#: Aspetta una risposta (una persona, o l'ora).
PENDING = "in_attesa"
#: Presa in carico: qualcuno ci sta lavorando, e non e' ancora conclusa.
TAKEN = "in_corso"
#: Il «no» di chi decide. Non e' un fallimento: e' l'esercizio del controllo.
CANCELLED = "disdetta"
#: HIRIS ha provato, e non ci e' riuscito.
FAILED = "fallita"

# --- Le parole esclusive delle promesse --------------------------------------

#: La promessa e' stata mantenuta.
KEPT = "mantenuta"
#: Nessuno l'ha mantenuta in tempo: si dichiara, non si recupera.
SKIPPED = "saltata"

# --- Le parole esclusive delle costruzioni -----------------------------------

#: Scritta in Home Assistant.
APPLIED = "applicata"
#: La scrittura e' partita e non si sa se Home Assistant l'abbia fatta (E-11,
#: Tappa 7): puo' essere arrivata, puo' non esserlo.
UNCERTAIN = "incerta"
#: Nessuno ha risposto entro la scadenza.
EXPIRED = "scaduta"

# --- Le parole esclusive delle proposte da fare a mano -----------------------

#: L'hai fatta tu, fuori da Home Assistant.
DONE_ELSEWHERE = "fatta_fuori"
#: La stessa domanda e' tornata come proposta che HIRIS puo' costruire.
SUPERSEDED = "superata"
#: Ne e' nata un'automazione («Rendila automatica»).
AUTOMATED = "automatizzata"

# --- Le code ------------------------------------------------------------------

#: In sospeso: non ancora concluse. Vale per promesse e costruzioni; una
#: proposta da fare a mano non si prende in carico, e il suo solo stato
#: sospeso e' `PENDING`.
SUSPENDED = (PENDING, TAKEN)

#: Gli stati di ciascuna coda, tutti: sono cio' che ogni archivio puo'
#: scrivere.
PROMISE_STATES = (PENDING, TAKEN, KEPT, SKIPPED, CANCELLED, FAILED)
CONSTRUCTION_STATES = (PENDING, TAKEN, APPLIED, CANCELLED, FAILED, UNCERTAIN,
                       EXPIRED)
PROPOSAL_STATES = (PENDING, CANCELLED, DONE_ELSEWHERE, SUPERSEDED, AUTOMATED)

#: La frase leggibile di ogni stato. Proposte l'08/10/2026 nel tono delle
#: etichette che le pagine avevano (In attesa, Non riuscita, Non eseguita...),
#: e approvate dal proprietario lo stesso giorno («Si' bene»); stanno anche nel
#: glossario (§4). `disdetta` ha UNA frase per le tre code: la proposta che
#: hai rifiutato si legge come la costruzione che hai declinato e la promessa
#: che hai disdetto, e nessuna delle tre porta la parola «rifiutata», che
#: sulla pagina Costruzioni voleva dire un guasto. La frase e' «annullata da
#: te», scelta dal proprietario l'08/10/2026 contro «disdetta da te»: il
#: codice resta `disdetta`, cambia solo cio' che si legge.
READABLE = {
    PENDING: "in attesa",
    TAKEN: "in corso",
    CANCELLED: "annullata da te",
    FAILED: "non riuscita",
    KEPT: "mantenuta",
    SKIPPED: "non eseguita",
    APPLIED: "applicata",
    UNCERTAIN: "esito incerto",
    EXPIRED: "scaduta",
    DONE_ELSEWHERE: "l’hai fatta tu, fuori da Home Assistant",
    SUPERSEDED: "superata: ora c’è una proposta che HIRIS può costruire",
    AUTOMATED: "ne è nata un’automazione: la trovi tra le proposte",
}


def readable(state: str) -> str:
    """La frase di `state`. Uno stato che il vocabolario non conosce torna
    com'e': e' una riga che un archivio non avrebbe dovuto scrivere, e
    mostrarla grezza la fa vedere invece di nasconderla."""
    return READABLE.get(state, state)


def sql_list(states) -> str:
    """Gli stati come lista SQL fra apici (`'in_attesa','in_corso'`), per un
    `IN (...)` composto una volta dal vocabolario. Sono costanti di questo
    modulo, mai un valore che arriva da fuori."""
    return ",".join(f"'{s}'" for s in states)
