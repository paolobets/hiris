"""Le due rotte della pagina dell'osservatore (fetta «l'osservatore», Task 7:
docs/design/2026-08-26-l-osservatore.md §7).

Non serializzano niente per conto proprio. `Watcher.watching()` e
`ObservationsStore.facts()` gia' tornano la forma che la pagina mostra --
una seconda forma costruita qui la farebbe divergere il primo giorno in cui
qualcuno aggiunge un campo da una parte sola (fondamenta 3).

**503, non un elenco vuoto, quando manca il collaboratore.** Spec §7: la
pagina esiste perche' il proprietario possa vedere «cosa sto guardando e
perche'» in ogni momento -- un `{"watching": []}` direbbe «HIRIS non guarda
niente», mentre l'osservatore assente e' un'altra cosa (l'add-on e' partito
senza di lui). E' la stessa distinzione a tre stati che il resto del prodotto
difende ovunque (`casa.non_disponibili`, `casa.etichette`, eccetera): un
guasto non si appiattisce su un'assenza.

Entrambe le rotte sono GET, quindi nessun `csrf_middleware` da rispettare
(sono metodi "safe", stessa esenzione di `GET /api/agenda`)."""
from __future__ import annotations

from aiohttp import web


async def handle_watching(request: web.Request) -> web.Response:
    """Cosa sta guardando l'osservatore, e da dove viene ogni voce.

    `Watcher.watching()` porta gia' `provenienza` per ciascuna voce --
    oggi sempre `"pavimento"` -- che e' cio' che dice alla pagina se una
    voce si puo' togliere (spec §7). Non si ricalcola qui.
    """
    watcher = request.app.get("watcher")
    if watcher is None:
        return web.json_response(
            {"watching": [], "error": "osservatore non disponibile"}, status=503)
    return web.json_response({"watching": watcher.watching()})


async def handle_facts(request: web.Request) -> web.Response:
    """Gli oggetti costruiti dall'aggregazione, filtrabili per giorno.

    `giorno` arriva dalla query cosi' com'e' -- una stringa o `None` -- e va
    all'archivio senza essere interpretato qui: e' `ObservationsStore.
    facts()` a sapere cosa significa "nessun filtro" (`giorno=None`, gli
    oggetti piu' recenti di ogni giorno). Un formato malformato non solleva:
    l'archivio confronta per uguaglianza esatta, e una data che non
    combacia con nessuna riga torna semplicemente un elenco vuoto -- non un
    errore, perche' "nessun oggetto per quel giorno" e' un esito legittimo
    (un giorno in cui la casa non ha fatto niente di osservabile), non un
    guasto.
    """
    store = request.app.get("observations")
    if store is None:
        return web.json_response(
            {"facts": [], "error": "archivio non disponibile"}, status=503)
    day = request.query.get("day") or None
    return web.json_response({"facts": store.facts(day=day)})
