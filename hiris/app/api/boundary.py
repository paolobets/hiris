"""Il confine HTTP: dove un'occorrenza del dominio smette di parlare italiano.

E' la legge del progetto applicata, non una regola nuova: **il dominio in
italiano, il confine nella lingua del sistema esterno**. Qui il sistema esterno
e' il browser, e la sua lingua e' l'inglese.

`Workshop.apply`/`.restore`, `ConstructionStore.mark_cancelled` e
`AgendaStore.cancel` restituiscono tutte lo stesso idioma -- un dict che porta
`"errore"` quando il tentativo non e' riuscito (`azione/porta.py`). Quel dict
attraversa DUE porte: gli strumenti del modello, dove resta italiano perche' e'
il dominio, e HTTP, dove esce in inglese perche' e' il confine. Senza questa
funzione le tre rotte che lo inoltrano tal quale sarebbero le uniche tre, su
diciassette, a scrivere `errore` invece di `error` -- un doppione vero, e per
giunta invisibile a chi legge solo il proprio handler.

Si traduce la CHIAVE e non il valore: il messaggio e' scritto per una persona,
e questo prodotto parla italiano alle persone.
"""
from __future__ import annotations


def occurrence_out(occurrence: dict) -> dict:
    """L'occorrenza come esce su HTTP. Non modifica l'originale.

    L'ordine delle chiavi si conserva -- `error` prende il posto esatto di
    `errore` invece di finire in coda -- cosi' il corpo di una risposta non
    cambia forma per un dettaglio che nessuno ha deciso.
    """
    return {("error" if k == "errore" else k): v for k, v in occurrence.items()}
