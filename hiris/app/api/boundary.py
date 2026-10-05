"""Il confine HTTP: dove un'occorrenza del dominio smette di parlare italiano.

E' la legge del progetto applicata, non una regola nuova: **il dominio in
italiano, il confine nella lingua del sistema esterno**. Qui il sistema esterno
e' il browser, e la sua lingua e' l'inglese.

`Workshop.apply`/`.restore`, `ConstructionStore.mark_cancelled` e
`AgendaStore.cancel` restituiscono tutte lo stesso idioma -- un dict che porta
`"errore"` quando il tentativo non e' riuscito (`action/actuator.py`). Quel dict
attraversa DUE porte: gli strumenti del modello, dove resta italiano perche' e'
il dominio, e HTTP, dove esce in inglese perche' e' il confine. Senza questa
funzione le rotte che lo inoltrano tal quale (`handlers_agenda.py`,
`handlers_constructions.py`) scriverebbero `errore` dove i loro stessi rifiuti
scrivono `error`.

I rifiuti che una rotta scrive di suo passano da `error_response` (Tappa 4,
Task 2; C-06, S-25; D2 approvata il 05/10/2026): la chiave e la forma d'errore
su HTTP vivono qui e solo qui. Resta `errore` cio' che va al modello -- i
risultati degli strumenti, anche quando viaggiano dentro una risposta HTTP
come il `content` di JSON-RPC in `handlers_mcp.py`, che e' testo per il
modello e non involucro.

Si traduce la CHIAVE e non il valore: il messaggio e' scritto per una persona,
e questo prodotto parla italiano alle persone.
"""
from __future__ import annotations

from aiohttp import web


def occurrence_out(occurrence: dict) -> dict:
    """L'occorrenza come esce su HTTP. Non modifica l'originale.

    L'ordine delle chiavi si conserva -- `error` prende il posto esatto di
    `errore` invece di finire in coda -- cosi' il corpo di una risposta non
    cambia forma per un dettaglio che nessuno ha deciso.
    """
    return {("error" if k == "errore" else k): v for k, v in occurrence.items()}


def error_body(text: str, **fields) -> dict:
    """Il corpo di un errore su HTTP: `error` col testo per la persona, e i
    campi che la rotta aggiunge (un limite, un conteggio) accanto."""
    return {"error": text, **fields}


def error_response(status: int, text: str, *, headers=None, **fields) -> web.Response:
    """La risposta d'errore di una rotta, nella forma unica del confine."""
    return web.json_response(error_body(text, **fields), status=status, headers=headers)
