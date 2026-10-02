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
scrivono `error`. Il confine non e' ancora tutto in inglese: altre rotte di
`api/` scrivono `errore` di proprio pugno e non passano di qui.

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
