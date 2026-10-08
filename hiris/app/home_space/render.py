"""La resa: una funzione per genere di oggetto (Tappa 9, «Una resa per
oggetto»; piano della Tappa 4, Task 7-8).

Ogni oggetto della casa che HIRIS mostra -- al modello, a una pagina, a un
servizio firmato -- esce da UNA funzione di questo modulo, col vocabolario
dei campi (`field_vocabulary`) e a una delle tre profondita' (corta, media,
completa). Le porte chiamano la resa e inoltrano il suo dizionario: non lo
compongono (R3, `tests/test_resa_unica.py`).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .house import House


# -- ricordo ---------------------------------------------------------------
#
# Fetta F3 della Tappa 9 (08/10/2026): C-41, S-22, D6.

#: Il genere di un ricordo, nella parola di `house_query.KINDS`.
MEMORY_KIND = "ricordo"

#: I campi di un ricordo, nell'ordine in cui la resa li porta: le colonne di
#: `memory/store.py` (tabella `ricordi`), che non si rinominano (spec §9:
#: cambia la resa, non il record), e le due liste che `MemoryStore._compose`
#: scioglie dalle loro tabelle.
_MEMORY_FIELDS = ("id", "testo", "detto_da", "said_by", "detto_il", "forza",
                  "grandezza", "minimo", "massimo", "unita", "corretto_da_utente",
                  "ancore", "condizioni")


def render_memory(memory: dict, house: House) -> dict:
    """La resa di UN ricordo: la stessa forma da ogni porta da cui un ricordo
    esce -- il dettaglio di `search` (`queries._view_memory`), i `ricordi`
    ancorati nelle schede di area, entita', dispositivo e comportamento,
    `fetch` (`tools._recall`) e la pagina Memoria (`GET /api/memories`).
    Fondamenta 3: fino all'08/10/2026 ogni porta lo componeva da se', e
    `corretto_da_utente` usciva dalla pagina (booleano), da `fetch` e dalle
    schede (l'intero della colonna), e dal dettaglio no (C-41).

    `memory` e' la riga di `MemoryStore`, con `ancore` e `condizioni` gia'
    sciolte; `house` e' l'istantanea della casa di chi chiede, e ogni ancora
    porta il nome di oggi e se esiste ancora (`House.tether`, G-21: qui si
    chiama, non si riscrive -- D6 della Tappa 9).

    **Una profondita' sola, la completa**: ogni porta mostra il ricordo
    intero, e nessuna oggi ne chiede uno piu' corto. Il tetto in caratteri
    (R16) arriva con i tetti per risposta (Tappa 9, T6).

    Il vocabolario dei campi (`docs/GLOSSARIO.md`, D1 della Tappa 4):
    `genere` sempre; una chiave assente nella riga resta assente («non lo
    so»), un `NULL` della colonna esce `null` («so che non c'e'»).

    **Il testo esce com'e'.** Il sanitizzatore lo applicano le porte che
    parlano al modello (`queries.sanitized_memories`), prima di questa
    funzione; la pagina mostra al proprietario le sue parole. La memoria non
    si riscrive: questa e' una copia."""
    out: dict = {"genere": MEMORY_KIND}
    for field in _MEMORY_FIELDS:
        if field in memory:
            out[field] = memory[field]
    if "corretto_da_utente" in out:
        out["corretto_da_utente"] = bool(out["corretto_da_utente"])
    if "ancore" in out:
        out["ancore"] = [house.tether(tether) for tether in out["ancore"] or []]
    return out
