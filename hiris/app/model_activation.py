"""Chi e' in catena: l'appartenenza, e nient'altro.

Fino alla 2.4.1 questo modulo derivava i provider ATTIVI da cinque
interruttori dell'add-on incrociati con le credenziali, e portava una regola di
compatibilita' -- `legacy = not any(toggles.values())`: se erano spenti TUTTI,
era attivo ogni provider con credenziale. Era lo stato dell'unica installazione
esistente, e il risultato era che due provider lavoravano mentre la pagina li
mostrava spenti. Peggio: accendendone UNO qualsiasi la compatibilita' cadeva e
valevano solo quelli accesi, quindi accendere il piano avrebbe spento Claude
API e OpenRouter senza toccarli.

Con la catena come unica verita' l'ambiguita' non esiste. Non c'e' piu' uno
stato «tutti spenti» che voglia dire sia «non ho ancora deciso» sia «non voglio
nessuno»: catena vuota significa una cosa sola, «HIRIS non puo' rispondere», e
la pagina lo dice invece di riaccendere di nascosto tutto cio' che ha una
credenziale.

Con `derive_active_providers` esce anche `reconcile_chain`, che accodava i
provider attivi mancanti dall'ordine salvato. La proprieta' buona che
proteggeva -- nessuno resta escluso dal ripiego senza saperlo -- non si perde:
chi diventa credenziato compare in «Fuori dalla catena», visibile, a un gesto
di distanza. Cio' che si guadagna e' che NIENTE entra in catena senza che
qualcuno ce l'abbia messo.

Della regola pre-2.5 resta nel repo la sola META' di compatibilita' («ogni
provider con una credenziale entra in catena»), in `server._catena_com_era`:
serviva a copiare nell'archivio la catena che HIRIS stava gia' usando. L'altra
meta' -- quella che leggeva i cinque interruttori -- e' uscita con la versione
B, che li ha tolti dallo schema: senza produttore, era codice irraggiungibile.

Quello che resta NON sparisce con la versione B, contrariamente a quanto questa
riga diceva: e' cio' che compone la catena di ogni installazione NUOVA, e senza
non ne nascerebbe nessuna. Va deciso, non ereditato -- vedi la sua docstring.
"""
from __future__ import annotations


def provider_in_catena(chain_order: list[str], credenziali: dict[str, bool]) -> list[str]:
    """L'ordine dell'utente, filtrato a chi ha una credenziale.

    Nessun accodamento, nessun ripiego su un ordine di strategia, nessun
    doppione. Una catena vuota resta vuota: e' uno stato leggibile, non un
    guasto da coprire.
    """
    dentro: list[str] = []
    for nome_provider in chain_order or []:
        if nome_provider in dentro:
            continue
        if credenziali.get(nome_provider):
            dentro.append(nome_provider)
    return dentro
