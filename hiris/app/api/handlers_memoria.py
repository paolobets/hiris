"""La vista HTTP della memoria -- cio' che HIRIS sa, in chiaro e correggibile.

E' la decisione (5) del progetto della memoria (docs/design/2026-08-05-la-
conoscenza-di-hiris.md, §6), scritta a luglio e mai eseguita. Oggi la pagina
"Memoria" interroga la coda di approvazione di knowledge_store, vuota per
costruzione da mesi: nessuno la riempie piu'. Questa vista interroga invece
l'archivio vero (memoria/archivio.py) e rende reale la regola (2) del
contratto: si puo' ricordare subito solo se poi si puo' guardare e correggere.

Tre cose, non di piu':

1. GET mostra la frase E cosa HIRIS ha capito -- le ancore col nome che
   l'anagrafe conosce OGGI (`Indice.verifica`), non l'identificatore nudo: e'
   il motivo per cui si ancora a un identificatore invece che a una parola.
   Se l'identificatore non esiste piu' nell'anagrafe, questa vista lo dice
   (`esiste: false`), non lo tace ne' fa finta che l'ancora non ci sia.
2. PATCH corregge l'interpretazione, mai il testo (memoria/archivio.py,
   regola 2): usa `valida()` -- lo stesso CANCELLO che gia' protegge
   l'ingresso dal modello (interpretazione.py) -- cosi' un'ancora senza
   riscontro nell'anagrafe viene RIFIUTATA con la ragione, non accettata a
   meta' come farebbe l'ingestione normale (che scarta e prosegue).
3. Senza archivio, la risposta non afferma "zero ricordi" come se fosse un
   fatto accertato: lo dichiara (`disponibile: false`) -- stessa convenzione
   di `handlers_casa.handle_get_casa`, non una seconda inventata qui.
"""
from __future__ import annotations

from aiohttp import web

from ..memoria.interpretazione import valida
from ..memoria.riconoscitore import costruisci_indice

# Gli stessi campi scalari che ArchivioMemoria.correggi() accetta
# (memoria/archivio.py, `_CAMPI_MODIFICABILI`) piu' le due liste che quel
# metodo sostituisce per intero (`ancore`, `condizioni`). Duplicato qui
# apposta invece di importare il nome con l'underscore da un altro modulo:
# quel prefisso e' gia' il segnale "non e' superficie pubblica".
_CAMPI_CORREGGIBILI = {
    "detto_da", "forza", "grandezza", "minimo", "massimo", "unita",
    "ancore", "condizioni",
}


def _risolvi_ancora(ancora: dict, indice) -> dict:
    """Un'ancora arricchita col nome che l'anagrafe conosce OGGI.

    `indice is None` (l'anagrafe della casa non e' disponibile) e "verificato
    assente dall'anagrafe" sono due fatti diversi: `esiste` resta `None` nel
    primo caso, mai `False` -- dichiarare un'assenza che non si e' potuta
    controllare sarebbe lo stesso silenzio non dichiarato che questo ramo ha
    gia' pagato dodici volte.
    """
    if indice is None:
        return {**ancora, "nome_attuale": None, "esiste": None}
    voce = indice.verifica(ancora["tipo"], ancora["riferimento"])
    return {**ancora, "nome_attuale": voce.get("nome") if voce else None,
            "esiste": voce is not None}


async def handle_get_memoria(request: web.Request) -> web.Response:
    archivio = request.app.get("archivio_memoria")
    if archivio is None:
        # Stessa convenzione di handle_get_casa (handlers_casa.py): senza
        # archivio non sappiamo se i ricordi sono zero o se e' l'archivio a
        # mancare -- `disponibile` lo dice, `ricordi: []` resta un
        # contenitore naturale, non l'affermazione di un fatto.
        return web.json_response({"disponibile": False, "ricordi": []})

    casa_archivio = request.app.get("archivio_casa")
    indice = costruisci_indice(casa_archivio.leggi()) if casa_archivio is not None else None

    ricordi = archivio.richiama(limite=200)
    for r in ricordi:
        r["corretto_da_utente"] = bool(r["corretto_da_utente"])
        r["ancore"] = [_risolvi_ancora(a, indice) for a in r["ancore"]]
    return web.json_response({"disponibile": True, "ricordi": ricordi})


async def handle_patch_memoria(request: web.Request) -> web.Response:
    archivio = request.app.get("archivio_memoria")
    if archivio is None:
        return web.json_response(
            {"errore": "l'archivio della memoria non e' disponibile"}, status=503)
    try:
        id_ricordo = int(request.match_info["id"])
    except (TypeError, ValueError):
        return web.json_response({"errore": "id non valido"}, status=400)

    try:
        corpo = await request.json()
    except Exception:
        return web.json_response(
            {"errore": "corpo della richiesta non valido: atteso JSON"}, status=400)
    if not isinstance(corpo, dict):
        return web.json_response(
            {"errore": "corpo della richiesta non valido: atteso un oggetto"}, status=400)

    campi = {k: v for k, v in corpo.items() if k in _CAMPI_CORREGGIBILI}
    if not campi:
        return web.json_response(
            {"errore": "nessun campo correggibile nella richiesta"}, status=400)

    # L'anagrafe puo' mancare (Home Assistant non ancora pronto): un indice
    # costruito su una casa vuota non verifica NESSUNA ancora, che e' il
    # comportamento giusto in fail-closed -- "un'ancora senza riscontro non
    # si scrive" vale anche quando il riscontro non si puo' nemmeno cercare.
    casa_archivio = request.app.get("archivio_casa")
    indice = costruisci_indice(casa_archivio.leggi() if casa_archivio is not None else {})

    # `valida()` e' il CANCELLO gia' scritto per l'interpretazione del
    # modello (interpretazione.py): qui si riusa per la correzione umana,
    # con la STESSA regola sulle ancore. I campi assenti dalla richiesta si
    # passano "neutri" (None/[]): non generano problemi propri (vedi
    # `_valida_forza`/`_valida_intervallo`/`_valida_ancore`/
    # `_valida_condizioni`), cosi' ogni problema dichiarato viene sempre da
    # un campo che l'utente ha davvero toccato in questa richiesta.
    interpretazione = {
        "forza": campi.get("forza"),
        "grandezza": campi.get("grandezza"),
        "minimo": campi.get("minimo"),
        "massimo": campi.get("massimo"),
        "ancore": campi.get("ancore") or [],
        "condizioni": campi.get("condizioni") or [],
    }
    pulita, problemi = valida(interpretazione, indice)
    if problemi:
        # Rifiutata con la ragione, non accettata a meta' (regola 2 di
        # ArchivioMemoria): nessuna delle correzioni si scrive, il ricordo
        # resta esattamente com'era.
        return web.json_response(
            {"errore": "; ".join(problemi), "problemi": problemi}, status=400)

    aggiornamenti: dict = {}
    if "detto_da" in campi:
        aggiornamenti["detto_da"] = campi["detto_da"]
    if "forza" in campi:
        aggiornamenti["forza"] = pulita["forza"]
    if "grandezza" in campi:
        aggiornamenti["grandezza"] = pulita["grandezza"]
    if "minimo" in campi:
        aggiornamenti["minimo"] = pulita["minimo"]
    if "massimo" in campi:
        aggiornamenti["massimo"] = pulita["massimo"]
    if "unita" in campi:
        # `valida()` non prende `unita` in input: la deduce sempre da ancora
        # + grandezza (interpretazione._deduci_unita), perche' quel percorso
        # e' per il modello ("l'unita' non si chiede, si deduce"). Qui invece
        # e' una correzione umana diretta a un campo che ArchivioMemoria.
        # correggi() gia' accetta -- passa cosi' com'e', senza dedurla.
        aggiornamenti["unita"] = campi["unita"]
    if "ancore" in campi:
        aggiornamenti["ancore"] = pulita["ancore"]
    if "condizioni" in campi:
        aggiornamenti["condizioni"] = pulita["condizioni"]

    archivio.correggi(id_ricordo, **aggiornamenti)
    return web.json_response({"ok": True})


async def handle_delete_memoria(request: web.Request) -> web.Response:
    archivio = request.app.get("archivio_memoria")
    if archivio is None:
        return web.json_response(
            {"errore": "l'archivio della memoria non e' disponibile"}, status=503)
    try:
        id_ricordo = int(request.match_info["id"])
    except (TypeError, ValueError):
        return web.json_response({"errore": "id non valido"}, status=400)
    archivio.dimentica(id_ricordo)
    return web.Response(status=204)
