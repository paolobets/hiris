"""Il riallineamento dell'osservatore quando Home Assistant torna.

Decisione del proprietario del 06/10/2026, «Riallinea»: quando HIRIS si
ricollega, confronta lo stato che Home Assistant dichiara con l'ultima riga
vista (`Watcher.realign`) e segna la finestra come voce di sistema
(`Watcher.record_disconnection`).

Qui vivono i due ganci che portano all'osservatore cio' che `HAClient` ha
visto; `server.py` li iscrive e basta (regola del proprietario del 06/10/2026,
«niente codice nuovo dentro server.py»).

`watcher` e' sempre un richiamo, non l'osservatore: gli ascoltatori di
`HAClient` si iscrivono prima del websocket, l'osservatore nasce dopo, e un avviso
arrivato prima della sua nascita non riallinea niente.
"""
from __future__ import annotations

from ..background import spawn as _spawn


async def reload_and_realign(client, entity_cache, watcher) -> None:
    """Rilegge lo specchio (`EntityCache.reload`) e con la STESSA fotografia
    riallinea l'osservatore: nessuna seconda lettura degli stati. La finestra
    di scollegamento ha il suo ascoltatore (`disconnection_recorder`): si
    chiude quando Home Assistant si dichiara avviato, che puo' essere dopo."""
    photo = await entity_cache.reload(client)
    observer = watcher()
    if observer is not None:
        observer.realign(photo)


def disconnection_recorder(watcher):
    """Restituisce l'ascoltatore della finestra di scollegamento
    (`HAClient.add_disconnection_listener`): la consegna all'osservatore
    (`Watcher.record_disconnection`)."""
    def _record(window: dict) -> None:
        observer = watcher()
        if observer is not None:
            observer.record_disconnection(window)
    return _record


def mirror_reload_listener(client, entity_cache, watcher=lambda: None):
    """Restituisce l'ascoltatore di topologia che rilegge lo specchio.

    Spec «una porta sola» §6: il quarto avvisato, dopo anagrafe, servizi e
    plance. Gli altri eventi dell'anagrafe non lo toccano. `_ws_loop` emette
    «riconnessione» a ogni connessione riuscita DOPO la prima (Tappa 2, Task
    7, D2): alla prima l'avvio legge lo specchio una volta da se'
    (`entity_cache.load`), dopo essersi iscritto. Con la stessa fotografia
    l'osservatore si riallinea (`mind/realignment.py`).
    """
    def _mirror_on_reconnect(event_type: str) -> None:
        if event_type == "riconnessione":
            _spawn(reload_and_realign(client, entity_cache, watcher),
                   name="specchio-riconnessione")
    return _mirror_on_reconnect
