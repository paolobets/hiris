"""Cio' che l'add-on scrive in Home Assistant per installarsi e disinstallarsi.

La terza porta di scrittura (Tappa 7, D1): la voce di menu dell'add-on e la
disinstallazione della vecchia card Lovelace. Non sono servizi
(`action/actuator.py`) e non sono la configurazione di automazioni, script e
scene (`action/construction/workshop.py`).
"""
import asyncio
import logging
import os

import aiohttp
from aiohttp import web

from ..background import spawn as _spawn
from ..home_space.redaction import home_assistant_folder
from ..panel_visibility import sync_panel_visibility

logger = logging.getLogger(__name__)


async def _ws_await(ws, msg_id: int, timeout: float = 10.0) -> dict:
    """Read WebSocket messages until we get the one matching msg_id."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError(f"Timeout waiting for WS message id={msg_id}")
        msg = await asyncio.wait_for(ws.receive_json(), timeout=remaining)
        if msg.get("id") == msg_id:
            return msg


# fetta E5 Task 5: la card Lovelace esce per intero -- il file
# `static/hiris-chat-card.js`, la sua copia dentro Home Assistant, il file di
# scoperta dell'ingress che solo lei leggeva e la registrazione della risorsa.
# Tornera' riscritta da zero quando il prodotto sara' completo.
#
# Con lei escono `_deploy_card_to_www` (copiava il JS in <config-ha>/www/{slug}/),
# `_write_ingress_config` (scriveva `hiris-ingress.json` accanto alla card: il
# suo unico lettore era la card, `hiris-chat-card.js:565`) e
# `_register_lovelace_card` (registrava la risorsa e migrava gli URL stantii).
#
# Al loro posto resta questa **disinstallazione**, perche' quelle tre funzioni
# non scrivevano dentro l'add-on: scrivevano nella configurazione dell'utente.
# Cancellare il solo codice lascerebbe in piedi una risorsa Lovelace che punta
# a un file che non esiste piu' -- un errore visibile nella dashboard, che
# l'utente dovrebbe togliere a mano senza sapere perche'. Chi ha installato
# disinstalla.
#
# Le tre regole che questa funzione rispetta, e che i test pinnano:
#  1. **tocca solo cio' che ha messo lei**: gli unici URL riconosciuti sono i
#     due che `_register_lovelace_card` sapeva creare -- il vecchio URL ingress
#     e qualunque `/local/{slug}/hiris-chat-card.js` (nudo o con `?v=`).
#     Qualsiasi altra risorsa Lovelace dell'utente resta dov'e';
#  2. **e' idempotente**: al secondo avvio non trova niente e non fa niente;
#  3. **non fa cadere l'avvio e non lo appende**: se Home Assistant non
#     risponde, o la cartella di configurazione non e' montata, la funzione
#     registra e torna -- entro un tempo **limitato** (`_WS_CONNECT_TIMEOUT`
#     sulla connessione, 10s su ciascuna delle due attese dentro la
#     conversazione). E se la deregistrazione fallisce lo **dice**: ogni
#     risorsa rimasta col proprio URL, piu' una riga di riepilogo con
#     l'elenco completo. Una traccia lasciata in silenzio nella configurazione
#     dell'utente sarebbe indistinguibile da un'assenza di problemi -- e un
#     elenco monco lo sarebbe altrettanto, perche' l'utente toglierebbe cio'
#     che ha letto e resterebbe con il resto.
_LOCAL_CARD_URL = "/local/{slug}/hiris-chat-card.js"
_URL_CARD_INGRESS = "/api/hassio_ingress/{slug}/static/hiris-chat-card.js"
# I due file che l'add-on copiava dentro <config-ha>/www/{slug}/. Nient'altro
# di quella cartella e' suo: se l'utente ci ha messo roba propria, resta.
_FILE_CARD = ("hiris-chat-card.js", "hiris-ingress.json")


# Quanto tempo si aspetta che Home Assistant apra il WebSocket. Le due attese
# dentro la conversazione hanno gia' un timeout esplicito (10s); la CONNESSIONE
# non ce l'aveva, e senza un `ClientTimeout` proprio valeva il default di
# aiohttp: cinque minuti. Un add-on che parte mentre Home Assistant sta ancora
# salendo sarebbe rimasto appeso dentro `_on_startup` per cinque minuti a ogni
# avvio -- non un guasto, ma nemmeno un avvio: la chat non c'e' finche' quella
# riga non torna. "Non fa cadere l'avvio" e "non ritarda l'avvio" sono due
# promesse diverse, e serviva la seconda (fix round 1, Important 1).
_WS_CONNECT_TIMEOUT = 15.0


def _e_risorsa_della_card(url: str, slug: str) -> bool:
    """Vero SOLO per le tre forme di URL che l'add-on sapeva registrare.

    fix round 1, Critical. Prima questa funzione chiudeva con
    `url.startswith(locale)`, che di forme ne riconosceva infinite: erano
    "sue" anche `/local/hiris/hiris-chat-card.js.bak`,
    `/local/hiris/hiris-chat-card.js-mio.js` e `/local/hiris/hiris-chat-card.json`.
    Un utente con un proprio fork della card dal nome derivato se lo sarebbe
    visto deregistrare dall'add-on, con un log che diceva "rimossa" e nessun
    modo di capire che era suo. Il vincolo e' l'opposto: mai toccare risorse
    che non ha installato lui. Le tre forme, e nient'altro:
      - il vecchio URL ingress;
      - `/local/{slug}/hiris-chat-card.js` nudo (add-on vecchi);
      - lo stesso con la query di versione, `?v=...`.
    """
    local = _LOCAL_CARD_URL.format(slug=slug)
    return (
        url == _URL_CARD_INGRESS.format(slug=slug)
        or url == local
        or url.startswith(local + "?")
    )


async def _deregistra_risorsa_card(ha_base_url: str, token: str, slug: str) -> bool:
    """Toglie da Lovelace TUTTE le risorse della card. Torna False se ne resta.

    `False` = "qualcosa e' rimasto nella configurazione dell'utente", e a quel
    punto il log l'ha gia' detto: ogni risorsa non tolta col proprio URL, piu'
    una riga di riepilogo con l'elenco completo. Nessun ramo di questa funzione
    solleva, e nessuno puo' bloccare l'avvio piu' di
    `_WS_CONNECT_TIMEOUT` + due attese da 10s.
    """
    ws_url = (
        ha_base_url.replace("http://", "ws://").replace("https://", "wss://")
        + "/api/websocket"
    )
    try:
        async with aiohttp.ClientSession() as session:
            # La connessione si apre a mano invece che con `async with
            # session.ws_connect(...)` per poterle mettere attorno un
            # `wait_for`: e' il solo punto della conversazione che non aveva
            # un timeout suo (vedi `_WS_CONNECT_TIMEOUT`). Il `finally`
            # chiude il context manager esattamente come farebbe l'`async
            # with`, anche quando l'attesa scade.
            connessione = session.ws_connect(ws_url)
            ws = await asyncio.wait_for(
                connessione.__aenter__(), timeout=_WS_CONNECT_TIMEOUT)
            try:
                handshake = await asyncio.wait_for(ws.receive_json(), timeout=10.0)
                if handshake.get("type") == "auth_required":
                    await ws.send_json({"type": "auth", "access_token": token})
                    auth_resp = await asyncio.wait_for(ws.receive_json(), timeout=10.0)
                    if auth_resp.get("type") != "auth_ok":
                        logger.warning(
                            "card HIRIS: autenticazione WebSocket rifiutata da Home "
                            "Assistant — la risorsa Lovelace non e' stata tolta; se "
                            "resta in dashboard, toglila da Impostazioni -> "
                            "Dashboard -> Risorse")
                        return False

                await ws.send_json({"id": 1, "type": "lovelace/resources"})
                list_resp = await _ws_await(ws, msg_id=1)
                if not list_resp.get("success"):
                    # Lovelace in modalita' YAML: le risorse non si gestiscono da
                    # qui, e in quella modalita' l'add-on non ne aveva mai
                    # registrata una (la registrazione usciva dallo stesso ramo).
                    logger.info(
                        "card HIRIS: risorse Lovelace non gestibili via WebSocket "
                        "(%s) — se avevi aggiunto la card a mano, toglila dal tuo "
                        "lovelace.yaml",
                        list_resp.get("error", {}).get("message", "unsupported"))
                    return True

                # fix round 1, Important 2: una delete rifiutata NON interrompe
                # piu' il ciclo. Chi aggiorna da una versione vecchia ha
                # tipicamente DUE risorse della card (l'URL nudo e quello
                # versionato): col vecchio `return False` la seconda non veniva
                # ne' tentata ne' nominata nel log, e l'utente toglieva a mano
                # l'unica che aveva letto restando con l'altra -- cioe' con
                # l'errore rosso che questa funzione esiste per togliergli. Si
                # tenta ognuna, si nomina ognuna, e l'esito complessivo torna in
                # fondo.
                msg_id = 2
                tolte: list[str] = []
                rimaste: list[str] = []
                for risorsa in list_resp.get("result", []):
                    url = risorsa.get("url", "")
                    if not _e_risorsa_della_card(url, slug):
                        continue
                    await ws.send_json({
                        "id": msg_id,
                        "type": "lovelace/resources/delete",
                        "resource_id": risorsa["id"],
                    })
                    resp = await _ws_await(ws, msg_id)
                    msg_id += 1
                    if resp.get("success"):
                        tolte.append(url)
                        logger.info(
                            "card HIRIS: risorsa Lovelace rimossa (%s) — la card e' "
                            "uscita dal prodotto, tornera' riscritta", url)
                    else:
                        rimaste.append(url)
                        logger.warning(
                            "card HIRIS: non ho potuto togliere la risorsa Lovelace "
                            "%s (%s) — toglila a mano da Impostazioni -> Dashboard "
                            "-> Risorse", url,
                            resp.get("error", {}).get("message", "sconosciuto"))
                if rimaste:
                    # Il riepilogo: chi legge il log deve trovare in UNA riga
                    # l'elenco COMPLETO di cio' che gli e' rimasto da togliere,
                    # senza doversi ricostruire da solo quante righe cercare.
                    logger.warning(
                        "card HIRIS: %d risorse Lovelace rimosse, %d rimaste da "
                        "togliere a mano: %s", len(tolte), len(rimaste),
                        ", ".join(rimaste))
                return not rimaste
            finally:
                await connessione.__aexit__(None, None, None)
    except Exception as exc:
        logger.warning(
            "card HIRIS: Home Assistant non ha risposto (%s) — se nella tua "
            "dashboard resta la risorsa %s, toglila da Impostazioni -> Dashboard "
            "-> Risorse", exc, _LOCAL_CARD_URL.format(slug=slug))
        return False


def _rimuovi_file_card(slug: str) -> None:
    """Toglie i due file della card da <config-ha>/www/{slug}/, se ci sono."""
    ha_config = home_assistant_folder()
    if ha_config is None:
        # Senza cartella montata non c'e' niente da togliere e niente da dire:
        # non e' un guasto, e' una installazione che la copia non l'ha mai
        # ricevuta.
        return
    folder = os.path.join(ha_config, "www", slug)
    for name in _FILE_CARD:
        path = os.path.join(folder, name)
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.info("card HIRIS: rimosso %s", path)
        except Exception as exc:
            logger.warning(
                "card HIRIS: non ho potuto rimuovere %s (%s) — puoi cancellarlo "
                "a mano", path, exc)
    # La cartella si toglie SOLO se e' rimasta vuota: se l'utente ci ha messo
    # qualcosa di suo, quella roba non e' dell'add-on e non si tocca.
    try:
        if os.path.isdir(folder) and not os.listdir(folder):
            os.rmdir(folder)
            logger.info("card HIRIS: rimossa la cartella vuota %s", folder)
    except Exception as exc:
        logger.debug("card HIRIS: cartella %s non rimossa (%s)", folder, exc)


async def _disinstalla_card_lovelace(ha_base_url: str, token: str,
                                     slug: str = "hiris") -> None:
    """Disinstalla la card Lovelace dalla configurazione di Home Assistant.

    Prima la risorsa, poi i file: al contrario si lascerebbe -- proprio nella
    finestra in cui Home Assistant non risponde -- una risorsa registrata che
    punta a un file gia' cancellato, cioe' l'errore che questa funzione esiste
    per evitare. Se la deregistrazione fallisce i file si tolgono lo stesso
    (il JS non esiste piu' nell'immagine: quella copia e' un residuo di una
    versione precedente), ma il fallimento e' gia' stato dichiarato nel log
    con l'URL da togliere a mano.
    """
    await _deregistra_risorsa_card(ha_base_url, token, slug)
    _rimuovi_file_card(slug)


async def _start_panel_sync(app: web.Application) -> None:
    # Il compito si tiene in `app`: il tetto della sincronia e' di dieci
    # minuti, e un arresto durante l'attesa del nucleo lo lascerebbe pendente
    # a chiusura. `_on_cleanup` lo ferma.
    app["panel_sync_task"] = _spawn(sync_panel_visibility(app), name="panel_visibility")
