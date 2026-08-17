# hiris/app/server.py
import asyncio
import contextlib
import hashlib
import logging
import os
import re
from pathlib import Path
import aiohttp
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .api.handlers_chat import handle_chat, handle_chat_reply_poll
from .api.handlers_entities import handle_list_entities
from .api.handlers_config import handle_config
from .api.handlers_usage import handle_usage, handle_reset_usage
from .api.handlers_chat_history import handle_get_chat_history, handle_clear_chat_history
from .api.handlers_models import (
    handle_list_models, handle_get_models_config, handle_save_models_config,
)
from .api.handlers_impostazioni import (
    handle_get_impostazioni, handle_save_impostazioni,
)
from .decisione_modelli import piano_ha_il_token
from .impostazioni_chat import ImpostazioniChat, il_file_non_porta_i_giorni
from .version import read_version
from .proxy.ha_client import HAClient
from .azione.registro import RegistroServizi
from .azione.porta import PortaAzione
from .casa.archivio import ArchivioCasa
from .casa.anagrafe import ricostruisci
from .memoria.archivio import ArchivioMemoria
from .casa.comportamento import rileggi, rileggi_plance
from .env_util import env_bool
from .esiti_provider import RegistroEsiti
from .token_interno import prepara_token_interno
from .proxy.entity_cache import EntityCache
from .memoria.cache_indice import CacheIndice
from .backends.embeddings import build_embedding_provider
from .api.middleware_internal_auth import internal_auth_middleware
from .api.middleware_csrf import csrf_middleware

logger = logging.getLogger(__name__)

# review C/#15: asyncio only holds a WEAK reference to a task with no other
# referrer -- a bare `asyncio.create_task(...)` whose result is discarded can
# be garbage-collected mid-execution (see the asyncio docs' "Important" note
# on create_task). Several fire-and-forget spots in this module discarded the
# result, including the HA notification-action listener that drives the
# step-up APPROVAL flow (a human's phone-tap Approve/Reject awaits HTTP calls
# to HA and must not be silently dropped mid-flight). _background_tasks keeps
# a strong reference until each task finishes; _spawn() is the one place that
# creates a background task, so every fire-and-forget site goes through it.
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro, *, name: str | None = None) -> asyncio.Task:
    """Create a fire-and-forget task and keep a strong reference to it.

    Use this instead of a bare `asyncio.create_task(...)` for any task whose
    result is not awaited/stored by the caller -- otherwise nothing prevents
    the event loop from garbage-collecting it before it completes.
    """
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def _ponte_attivo(archivio: dict | None) -> bool:
    """Il ponte e' acceso se, e solo se, `ponte.attivo` lo dice nell'archivio.

    Fino alla 2.3.1 questa funzione si chiamava `_chat_subscription_active` ed
    era un AND fra DUE opzioni dell'add-on (`chat_via_subscription` e
    `bridge_enabled`). L'AND era il fail-safe numero uno del rilascio: senza,
    si poteva instradare la chat in una coda che nessuno spazzava, e i
    messaggi restavano pendenti per sempre.

    Il proprietario ha fuso i due interruttori in uno solo (`ponte.attivo`,
    13 agosto 2026), e il fail-safe NON e' stato rimosso: e' diventato
    STRUTTURALE. C'e' UN valore, derivato UNA volta (`_ricalcola_catena`
    scrive `app["ponte_attivo"]`) e letto da tutti -- la spazzata,
    l'instradamento della chat, il gate del lavoratore del ponte, la pagina.
    L'invariante «non accodare mai in una coda che nessuno spazza» non regge
    piu' su un `and` da non sbagliare, e nemmeno su due chiamate alla stessa
    funzione: regge sul fatto che non c'e' niente da combinare.

    VERSIONE B (3.0.0): erano DUE argomenti, `interruttore` (da `BRIDGE_ENABLED`,
    cioe' dall'opzione `ponte.attivo`) e `piano_attivo` (`_sub_first_class`,
    cioe' `provider_subscription` acceso col suo token), combinati con un `or`.
    Il secondo era l'IMPLICAZIONE: il piano acceso accendeva il ponte da se'.
    Esce insieme all'opzione che lo alimentava, e non e' una perdita di
    comodita' senza contropartita -- era l'ultima seconda rappresentazione del
    prodotto (invariante 1): `app["ponte_attivo"]` poteva valere True mentre
    l'archivio, che e' cio' che la pagina Modelli mostra e scrive, diceva
    False. Con l'implicazione viva il bottone «Mettilo primo» non sarebbe
    costruibile: metterebbe a `true` un valore gia' scavalcato, e spegnere il
    ponte sarebbe impossibile per chiunque abbia un token.

    Chi aggiorna col token presente e `ponte.attivo` false perde il ponte, e
    NON in silenzio: `_avvisi_del_ponte` glielo dice all'avvio nel registro, la
    pagina Modelli lo dice in cima («Il Piano Claude Max ha il token, lo paghi,
    ed e' fuori dalla catena») e accanto a quella frase c'e' il bottone che lo
    riaccende in un gesto.

    Rimettere qui un secondo valore -- un `or` con una credenziale, un `and`
    con un interruttore -- farebbe cadere
    `test_chat_subscription_path.py::test_il_ponte_e_un_valore_solo`.
    """
    return bool(((archivio or {}).get("ponte") or {}).get("attivo", False))


def _avvisi_del_ponte(ponte_attivo: bool, token_presente: bool) -> list[str]:
    """Le due frasi che `run.sh` non puo' piu' dire, e perche' sono ancora qui.

    Fino alla 2.5.0 vivevano in `run.sh`: erano l'unico posto che parlava
    PRIMA che HIRIS partisse, e leggevano `PROVIDER_SUBSCRIPTION`/
    `BRIDGE_ENABLED`. Con la versione B quelle opzioni non esistono e il ponte
    vive nell'archivio di HIRIS, che da uno script di avvio non si legge. Le
    frasi non si cancellano -- descrivono i due stati che costano soldi senza
    dirlo -- si spostano dove l'archivio c'e'.

    Funzione PURA: restituisce le righe, non le scrive. E' cio' che permette di
    provarle senza montare un'applicazione, ed e' anche la ragione per cui il
    chiamante puo' decidere il livello.

    I due stati:

    - **ponte acceso, token assente**: nessun messaggio arriva al piano. Dal
      Task 14 il turno non si perde piu' (scende alla catena nella stessa
      richiesta), ma scende a un provider a consumo: un ripiego silenzioso dal
      forfait al consumo si scopre a fine mese.
    - **token presente, ponte spento**: e' lo stato in cui si ritrova chi
      aggiorna alla 3.0.0 avendo il piano acceso via `provider_subscription`
      SENZA aver mai acceso il ponte. Quell'opzione implicava il ponte; la
      versione B toglie l'implicazione (vedi `_ponte_attivo`), e la copia
      d'archivio della 2.5.0 aveva copiato l'OPZIONE `ponte.attivo`, non lo
      stato effettivo. Il ponte si spegne, e questa riga e' cio' che rende la
      cosa rumorosa invece che silenziosa: senza, la chat tornerebbe a pagare
      a consumo senza dirlo.
    """
    if ponte_attivo and not token_presente:
        return ["Il ponte e' acceso ma «Provider · Piano Claude Max — token» e' "
                "vuoto: nessun messaggio arriva al Piano Claude Max, e ogni turno "
                "passa alla catena -- dal forfait al consumo. Incolla il token, "
                "oppure spegni il ponte dalla pagina Modelli di HIRIS."]
    if token_presente and not ponte_attivo:
        return ["Hai il token del Piano Claude Max, ma il ponte e' spento: le "
                "risposte passano dalla catena, a consumo. Il ponte non si accende "
                "piu' da un'opzione dell'add-on -- si accende nella pagina Modelli "
                "di HIRIS, col bottone accanto alla riga «Il Piano Claude Max ha il "
                "token, lo paghi, ed e' fuori dalla catena»."]
    return []


# fetta «la pagina di configurazione» (2.3.0): `_parse_policy_csv` esce con la
# sua unica ragione di esistere, l'opzione add-on `chat_policy`. La funzione
# leggeva un CSV di nomi di backend e lo passava a `LLMRouter(chat_policy=...)`,
# dove `__init__` lo scartava ogni volta: il ramo `else` che lo usa esiste solo
# quando `model_chain` e' vuota. Fino alla 2.4.1 quel ramo era irraggiungibile
# perche' `reconcile_chain` restituiva sempre almeno un nome; dalla fetta «la
# catena diventa l'unica verita'» la catena PUO' essere vuota, ed e' uno stato
# che significa qualcosa -- «HIRIS non ha a chi chiedere». Percio' `LLMRouter`
# ha smesso di ripiegare sull'ordine di strategia quando la catena arriva
# esplicita e vuota: ripiegare avrebbe rimesso in piedi, dentro al router, la
# regola `legacy` appena tolta -- la pagina avrebbe detto «catena vuota» mentre
# la chat rispondeva usando tutto cio' che aveva una credenziale. Il parametro
# `chat_policy` di `LLMRouter` RESTA: e' il default di libreria quando nessuno
# passa una catena (`model_chain=None`), ed e' pinnato dai suoi test.


def _catena_com_era(strategia: str, credenziali: dict, ponte: bool) -> list[str]:
    """La catena con cui nasce un archivio che non ha ancora la sua: **ogni
    provider di cui c'e' una credenziale**, nell'ordine del preset.

    Si chiama ancora «com'era» perche' e' cio' che la regola pre-2.5 produceva
    sull'installazione del proprietario, ed e' per quello che esiste: copiare
    la catena invece di far passare quell'impianto da «due provider lavorano» a
    «zero provider». Ma non e' piu' una copia della vecchia regola per intero.

    **Aveva un secondo ramo, ed e' uscito con la versione B.** La vecchia
    regola era in due tempi: `legacy = not any(interruttori)` -- nessuno dei
    cinque `provider_*` acceso, e allora contava la sola credenziale -- oppure,
    con almeno un interruttore acceso, contavano solo gli accesi. I cinque
    interruttori sono usciti dallo schema e `run.sh` non esporta piu' nessuno
    dei cinque `PROVIDER_*`: via Supervisor `legacy` era strutturalmente sempre
    vero e il secondo ramo era codice irraggiungibile. Tenerlo qui voleva dire
    tenere a schermo una regola che non puo' piu' girare -- e i test che la
    esercitavano difendevano uno stato che nessun utente puo' produrre.

    Resta quindi la sola regola di compatibilita', scritta per quello che e'.
    **E va DECISA, non ereditata** (G3 della revisione): non e' piu' una
    migrazione che si esaurisce, si esegue su ogni installazione nuova finche'
    qualcuno non decide che catena deve trovare chi installa HIRIS oggi. La
    fetta successiva non puo' limitarsi a cancellarla: senza, un'installazione
    nuova nasce con la catena vuota e la chat muta.

    Il piano non e' un membro della catena: entra solo se il ponte e' acceso, e
    quello lo dice `ponte.attivo`, non l'appartenenza.
    """
    from .llm_router import _STRATEGY_ORDER
    attivi = {}
    for p in ("subscription", "claude", "openai", "openrouter", "ollama"):
        ha = bool(credenziali.get(p))
        attivi[p] = (ha and ponte) if p == "subscription" else ha
    ordine = _STRATEGY_ORDER.get(strategia, _STRATEGY_ORDER["balanced"])
    return [n for n in ordine if attivi.get(n)]


def _find_ha_config_dir() -> str | None:
    """Return the HA config directory path inside the container, or None if not mounted.

    Different Supervisor versions mount the config volume at different paths:
    - /config  (documented standard, most Supervisor versions)
    - /homeassistant  (used in some older/newer variants)
    We probe both and return the first that looks like the real HA config.
    """
    for candidate in ("/config", "/homeassistant"):
        if (
            os.path.exists(os.path.join(candidate, "configuration.yaml"))
            or os.path.isdir(os.path.join(candidate, ".storage"))
        ):
            return candidate
    return None


async def _ws_await(ws, msg_id: int, timeout: float = 10.0) -> dict:
    """Read WebSocket messages until we get the one matching msg_id."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise asyncio.TimeoutError(f"Timeout waiting for WS message id={msg_id}")
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
#     registra e torna -- entro un tempo **limitato** (`_ATTESA_CONNESSIONE_WS`
#     sulla connessione, 10s su ciascuna delle due attese dentro la
#     conversazione). E se la deregistrazione fallisce lo **dice**: ogni
#     risorsa rimasta col proprio URL, piu' una riga di riepilogo con
#     l'elenco completo. Una traccia lasciata in silenzio nella configurazione
#     dell'utente sarebbe indistinguibile da un'assenza di problemi -- e un
#     elenco monco lo sarebbe altrettanto, perche' l'utente toglierebbe cio'
#     che ha letto e resterebbe con il resto.
_URL_CARD_LOCALE = "/local/{slug}/hiris-chat-card.js"
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
_ATTESA_CONNESSIONE_WS = 15.0


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
    locale = _URL_CARD_LOCALE.format(slug=slug)
    return (
        url == _URL_CARD_INGRESS.format(slug=slug)
        or url == locale
        or url.startswith(locale + "?")
    )


async def _deregistra_risorsa_card(ha_base_url: str, token: str, slug: str) -> bool:
    """Toglie da Lovelace TUTTE le risorse della card. Torna False se ne resta.

    `False` = "qualcosa e' rimasto nella configurazione dell'utente", e a quel
    punto il log l'ha gia' detto: ogni risorsa non tolta col proprio URL, piu'
    una riga di riepilogo con l'elenco completo. Nessun ramo di questa funzione
    solleva, e nessuno puo' bloccare l'avvio piu' di
    `_ATTESA_CONNESSIONE_WS` + due attese da 10s.
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
            # un timeout suo (vedi `_ATTESA_CONNESSIONE_WS`). Il `finally`
            # chiude il context manager esattamente come farebbe l'`async
            # with`, anche quando l'attesa scade.
            connessione = session.ws_connect(ws_url)
            ws = await asyncio.wait_for(
                connessione.__aenter__(), timeout=_ATTESA_CONNESSIONE_WS)
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
            "-> Risorse", exc, _URL_CARD_LOCALE.format(slug=slug))
        return False


def _rimuovi_file_card(slug: str) -> None:
    """Toglie i due file della card da <config-ha>/www/{slug}/, se ci sono."""
    ha_config = _find_ha_config_dir()
    if ha_config is None:
        # Senza cartella montata non c'e' niente da togliere e niente da dire:
        # non e' un guasto, e' una installazione che la copia non l'ha mai
        # ricevuta.
        return
    cartella = os.path.join(ha_config, "www", slug)
    for nome in _FILE_CARD:
        percorso = os.path.join(cartella, nome)
        try:
            if os.path.exists(percorso):
                os.remove(percorso)
                logger.info("card HIRIS: rimosso %s", percorso)
        except Exception as exc:
            logger.warning(
                "card HIRIS: non ho potuto rimuovere %s (%s) — puoi cancellarlo "
                "a mano", percorso, exc)
    # La cartella si toglie SOLO se e' rimasta vuota: se l'utente ci ha messo
    # qualcosa di suo, quella roba non e' dell'add-on e non si tocca.
    try:
        if os.path.isdir(cartella) and not os.listdir(cartella):
            os.rmdir(cartella)
            logger.info("card HIRIS: rimossa la cartella vuota %s", cartella)
    except Exception as exc:
        logger.debug("card HIRIS: cartella %s non rimossa (%s)", cartella, exc)


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


# fetta E3 Task 7: `_reasoning_runner(app)` -- risolveva l'oggetto a cui il
# percorso di ragionamento proattivo parlava (llm_router, poi
# engine._claude_runner) -- e' uscita: il suo unico chiamante era
# `_llm_reason`, la closure della Sentinella cancellata per intero piu' sotto
# (vedi il blocco "Sentinella" in _on_startup). Stessa sorte di
# `_reason_memory_context`, che viveva subito sotto (leggeva reasoner_
# memory.relevant_memory per il contesto memoria del ragionatore): il suo
# unico chiamante era `_gather_context`, un'altra closure dello stesso
# blocco. `MemoryRecall`/`relevant_memory` (brain/reasoner_memory.py) non
# avevano altri chiamanti: il modulo e' cancellato con loro.


# fetta E3 Task 12 ("esce il ritratto"): `_osserva_la_casa` (l'unico
# scrittore della linea di base, sul job schedulato "hiris_portrait_observe")
# e `_portrait_context` (il testo reso, gia' ORFANO DICHIARATO dal Task 7 --
# il suo ultimo chiamante di produzione, `_gather_context` dentro il blocco
# Sentinella, era caduto li') sono usciti insieme a tutto il ritratto:
# `brain/portrait.py`, `brain/portrait_store.py`, il job e il suo cablaggio
# piu' sotto. I lettori del TESTO composto erano gia' tutti caduti nei Task
# 4-7 (server.py:1777,1801,1805,2390 nella ricognizione -> prompt di
# watcher/reasoner.py e coverage_review.py, entrambi cancellati); la chat non
# lo ha mai letto (handlers_chat.py non lo chiama). Con lui esce il concetto
# di "delta dall'ultima osservazione", che il nucleo oggi non ha: e'
# materiale che tornera' nella conoscenza 2.0 se il nucleo vorra' imparare il
# delta -- con un progetto, non trascinando portrait.db.


# fetta E3 Task 6: `run_daily_briefing` (resoconto delle 08:00),
# `_format_nudge_message`/`run_urgent_nudges` (solleciti ogni 6 ore) sono
# uscite qui insieme al canale che le portava all'utente. Leggevano
# `knowledge_store.upcoming_obligations` e `advisory_store` -- due basi che
# questa fetta svuota di senso (l'advisory_store muore in questo stesso
# task, il resoconto sulla conoscenza 2.0 tornera' quando avra' il nucleo da
# leggere). SILENZIO DICHIARATO: da qui HIRIS smette di parlare da solo,
# vedi il commento sopra il cablaggio dello scheduler, piu' sotto.


async def ricarica_inventario_entita(cache, ha_client) -> bool:
    """Ritenta il caricamento iniziale dell'inventario delle entita', e SOLO
    quello. Ritorna True se questo giro l'ha rimesso in piedi.

    `_on_startup` logga e prosegue quando `EntityCache.load` fallisce (Home
    Assistant che parte dopo l'addon, riavvio del core, rete che balbetta):
    da li' in poi la cache resta `loaded is False` e gli strumenti che
    la leggono rispondono "non ancora pronto". Onesto, ma senza qualcuno che
    riprovi resterebbe cosi' fino al riavvio dell'addon: piu' onesto di prima
    e piu' scomodo. Questo e' quel qualcuno.

    Non tocca una cache gia' viva: da quel momento la mantengono aggiornata gli
    eventi di stato, e rileggere tutta la casa a ogni giro sarebbe traffico
    inutile verso Home Assistant. Modulo-level (non chiuso dentro
    `_on_startup`) per essere unit-testabile con un semplice dict al posto
    di `app`: si prova senza avviare l'applicazione.

    Non solleva mai: gira nello scheduler, e un Home Assistant ancora giu' e'
    il caso previsto, non un errore da propagare -- il giro successivo
    riprovera'.
    """
    if cache is None or ha_client is None:
        return False
    if getattr(cache, "loaded", True):
        return False
    try:
        await cache.load(ha_client)
    except Exception as exc:
        logger.warning("Ricarica dell'inventario entita' non riuscita: %s", exc)
        return False
    logger.info(
        "Inventario entita' ricaricato: %d entita' (la lettura iniziale era fallita)",
        len(cache.get_all()) if hasattr(cache, "get_all") else -1,
    )
    # Qui c'erano due chiamate WebSocket per ricostruire una mappa area->entita'
    # che nessuno leggeva, e che sbagliava (per nome invece che per id, senza
    # l'area ereditata dal dispositivo). Le aree le ricostruisce
    # `casa.anagrafe.ricostruisci`, che le legge per id e dichiara i registri
    # caduti.
    return True


def should_start_agent_worker(ponte_attivo: bool) -> bool:
    """Gate worker del ponte in-addon: il ponte e' acceso, E il token c'e'.

    Fino alla 2.3.1 la seconda meta' della condizione leggeva
    CHAT_VIA_SUBSCRIPTION: era una delle tre cose che quell'opzione faceva, e
    l'unica che `bridge_enabled` non faceva. Fuse le due opzioni, questo gate
    e quello della spazzata leggono finalmente lo STESSO valore — prima si
    poteva far partire il worker (via `chat_via_subscription`) lasciando
    spenta la spazzata (`bridge_enabled`), e il worker sondava una coda che
    nessuno riempiva.

    VERSIONE B (3.0.0): non legge piu' NIENTE dall'ambiente per il ponte.
    `PROVIDER_SUBSCRIPTION` e `BRIDGE_ENABLED` erano le ultime due opzioni
    dell'add-on lette qui, e il valore arriva adesso come argomento --
    `app["ponte_attivo"]`, lo stesso che governa la spazzata e
    l'instradamento. E' una funzione di modulo senza `app`: passarglielo e'
    l'unico modo di tenerla una funzione pura e di renderla chiamabile ANCHE
    a caldo, cioe' quando la pagina Modelli accende il ponte senza un riavvio
    (`_ricalcola_catena`). Il token resta letto qui: e' una credenziale, e le
    credenziali stanno ancora nelle opzioni dell'add-on."""
    return ponte_attivo and piano_ha_il_token()


def programma_ricostruzione_anagrafe(client, archivio, ritardo: float = 3.0):
    """Restituisce `innesca(tipo_evento)`: ricostruisce l'anagrafe, una volta sola.

    Riorganizzare la casa in Home Assistant produce una raffica di eventi —
    spostare dieci entita' ne emette dieci. Ricostruire a ogni evento
    significherebbe dieci letture di tutti i registri per un unico gesto
    dell'utente: si aspetta che la raffica finisca, e si rilegge una volta.

    Un guasto viene registrato e basta: l'ascoltatore deve sopravvivere a un
    Home Assistant che si riavvia, o dopo il primo intoppo l'anagrafe resta
    ferma per sempre senza che nessuno lo sappia.
    """
    stato: dict[str, asyncio.Task | None] = {"attesa": None}

    async def _fra_poco():
        try:
            await asyncio.sleep(ritardo)
            await ricostruisci(client, archivio)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("ricostruzione dell'anagrafe fallita: %s", exc)

    def innesca(tipo_evento: str) -> None:
        attesa = stato["attesa"]
        if attesa is not None and not attesa.done():
            attesa.cancel()
        # _spawn(), non un asyncio.create_task(...) nudo: tiene un riferimento
        # forte finche' la ricostruzione non finisce (review C/#15) -- vedi il
        # commento in cima al modulo su _background_tasks.
        stato["attesa"] = _spawn(_fra_poco(), name="ricostruzione_anagrafe")

    return innesca


def programma_rilettura_plance(client, archivio, ritardo: float = 3.0):
    """Restituisce `innesca(dati_evento)`: rilegge le plance, una volta sola.

    Gemello di `programma_ricostruzione_anagrafe` — stesso antirimbalzo,
    stessa tolleranza ai guasti — ma per un innesco DIVERSO (EVENTO_PLANCE,
    non i registri): le plance non stanno in _TABELLE e non vanno confuse con
    l'anagrafe, che questa funzione non tocca.
    """
    stato: dict[str, asyncio.Task | None] = {"attesa": None}

    async def _fra_poco():
        try:
            await asyncio.sleep(ritardo)
            await rileggi_plance(client, archivio)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("rilettura delle plance fallita: %s", exc)

    def innesca(dati_evento: dict) -> None:
        attesa = stato["attesa"]
        if attesa is not None and not attesa.done():
            attesa.cancel()
        stato["attesa"] = _spawn(_fra_poco(), name="rilettura_plance")

    return innesca


# Sentinella per distinguere, dentro `sentinella_comportamento`, «non ho
# ancora letto nulla» da «ho letto e l'impronta e' None» (cartella di Home
# Assistant assente). Con `None` come valore iniziale le due cose sarebbero
# indistinguibili: senza cartella l'impronta resta sempre `None`, e
# `guarda()` rileggerebbe a ogni chiamata invece che una volta sola.
_MAI_LETTA = object()


def sentinella_comportamento(client, archivio, cartella_ha: Path | None,
                             trova_cartella=None):
    """Restituisce `guarda()`: rilegge il comportamento solo se i file sono cambiati.

    L'mtime di `automations.yaml` e `scripts.yaml` e' l'unico segnale che
    esiste per gli script: Home Assistant, per gli script, non emette ALCUN
    evento di ricarica -- il servizio non accetta un id e il gestore non
    spara niente. Un solo meccanismo per automazioni e script, invece di due
    percorsi di cui uno incompleto. Costa due `stat()` per chiamata.

    Finche' la cartella non c'e', la si **ricerca a ogni giro**: l'add-on puo'
    partire prima che il Supervisor abbia finito di montarla, e risolverla una
    volta sola all'avvio significherebbe restare convinti per sempre che non ci
    sia niente da leggere -- con `/api/casa` che racconta lo stantio come
    stato attuale, in silenzio.

    L'mtime dei due file non basta da solo: un'automazione tolta o aggiunta
    dentro un PACCHETTO (o una cartella inclusa) non tocca `automations.yaml`,
    quindi non cambia l'impronta -- resterebbe in `/api/casa` come fantasma
    (o invisibile, per un'aggiunta) finche' nessuno tocca a mano i due file
    "principali". `guarda(forza=True)` bypassa il confronto sull'impronta:
    e' quanto usa `programma_rilettura_comportamento`, agganciata allo stesso
    evento di registro entita' (EVENTI_ANAGRAFE) che gia' fa ricostruire
    l'anagrafe -- aggiungere o togliere un'automazione CAMBIA quel registro.

    Restituisce `True` se ha riletto, `False` se non serviva o se la
    rilettura e' fallita.
    """
    ultimo: dict[str, object] = {"impronta": _MAI_LETTA}
    stato: dict[str, Path | None] = {"cartella": cartella_ha}
    _trova = trova_cartella if trova_cartella is not None else _find_ha_config_dir

    def _cartella() -> Path | None:
        if stato["cartella"] is None:
            trovata = _trova()
            if trovata:
                stato["cartella"] = Path(trovata)
                logger.info("cartella di Home Assistant comparsa dopo l'avvio: %s",
                            stato["cartella"])
        return stato["cartella"]

    def _impronta():
        cartella = _cartella()
        if cartella is None:
            return None
        marche = []
        for nome in ("automations.yaml", "scripts.yaml"):
            try:
                marche.append((nome, (cartella / nome).stat().st_mtime_ns))
            except OSError:
                marche.append((nome, None))
        return tuple(marche)

    async def guarda(forza: bool = False) -> bool:
        adesso = _impronta()
        if not forza and ultimo["impronta"] is not _MAI_LETTA and adesso == ultimo["impronta"]:
            return False
        try:
            await rileggi(client, archivio, stato["cartella"])
        except Exception as exc:
            # NON si memorizza l'impronta qui: se lo si facesse prima di aver
            # letto davvero, un guasto passeggero (Home Assistant che si
            # riavvia) congelerebbe il comportamento fino al prossimo tocco
            # dei file -- potenzialmente per settimane, senza che nessuno lo
            # sappia. Si riprova al giro successivo, tocco o non tocco.
            logger.warning("rilettura del comportamento fallita: %s", exc)
            return False
        ultimo["impronta"] = adesso
        return True

    return guarda


def programma_rilettura_comportamento(guarda, ritardo: float = 3.0):
    """Restituisce `innesca(tipo_evento)`: rilegge il comportamento FORZANDO
    il confronto sull'impronta, una volta sola per raffica.

    Gemello di `programma_ricostruzione_anagrafe` -- stesso antirimbalzo,
    stessa tolleranza ai guasti, stesso evento (EVENTI_ANAGRAFE, via
    `add_anagrafe_listener`: nessun meccanismo nuovo). Aggiungere o togliere
    un'automazione cambia il registro delle entita', ma NON tocca sempre
    `automations.yaml` -- un'automazione dentro un pacchetto no. Senza questo
    innesco, quel cambiamento resterebbe invisibile a `/api/casa` finche'
    qualcuno non tocca a mano i due file "principali" (vedi
    `sentinella_comportamento`).
    """
    stato: dict[str, asyncio.Task | None] = {"attesa": None}

    async def _fra_poco():
        try:
            await asyncio.sleep(ritardo)
            await guarda(forza=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("rilettura forzata del comportamento fallita: %s", exc)

    def innesca(tipo_evento: str) -> None:
        attesa = stato["attesa"]
        if attesa is not None and not attesa.done():
            attesa.cancel()
        stato["attesa"] = _spawn(_fra_poco(), name="rilettura_comportamento")

    return innesca


def _governa_lavoratore_del_ponte(app) -> None:
    """Fa partire, o fa smettere, il lavoratore che risponde sul piano.

    Fino alla 2.5.0 questa decisione si prendeva UNA volta, alla fine
    dell'avvio, perche' l'interruttore del ponte era un'opzione dell'add-on e
    cambiarla voleva dire riavviare. Dalla versione B l'interruttore vive
    nell'archivio e la pagina Modelli lo riscrive: la decisione deve poterne
    seguire i cambiamenti, o accendere il ponte dalla pagina produrrebbe la
    peggiore delle due meta' (la chat instradata sul piano, e nessuno a
    rispondere: ogni turno aspetta la scadenza e poi ripiega sulla catena).

    Le due direzioni sono simmetriche e sono entrambe necessarie:
    - acceso e nessun lavoratore vivo -> si avvia;
    - spento e un lavoratore vivo -> si ferma. Senza questo ramo, spegnere il
      ponte lascerebbe un ciclo che interroga la coda ogni tre secondi per
      sempre -- rumore nel registro, e un consumatore per una coda che nessuno
      riempie.

    Senza un event loop in corso non si fa niente e non e' un ripiego: un
    compito asincrono non ha dove girare. Succede solo fuori dal server (i test
    che chiamano `_ricalcola_catena` come funzione), e in quel caso l'assenza
    del lavoratore e' il fatto vero, non una supposizione.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return

    voluto = should_start_agent_worker(bool(app.get("ponte_attivo")))
    corrente = app.get("agent_worker_task")
    vivo = corrente is not None and not corrente.done()

    if voluto and not vivo:
        from .agent import runner as _agent_runner

        app["agent_worker_task"] = _spawn(
            _agent_runner.run_loop(
                "http://127.0.0.1:8099",
                _agent_runner.build_headers,
                os.environ.get("HIRIS_AGENT_MODE", "live"),
                int(os.environ.get("HIRIS_AGENT_POLL_SECONDS", "3")),
            ),
            name="agent_worker",
        )
        logger.info(
            "Lavoratore del ponte avviato: il ponte e' acceso e il token del "
            "Piano Claude Max c'e'.")
    elif not voluto and vivo:
        corrente.cancel()
        app["agent_worker_task"] = None
        logger.info(
            "Lavoratore del ponte fermato: il ponte e' spento, oppure manca il "
            "token del Piano Claude Max. La chat risponde dalla catena.")


def _ricalcola_catena(app) -> None:
    """Rimette in vigore, a caldo, ciò che la pagina Modelli ha appena salvato.

    Senza questa funzione un riordino cambierebbe la PAGINA e non il RUNTIME:
    `handle_save_models_config` aggiorna `app["models_config"]`, ma la catena
    del router si costruiva solo all'avvio. Quindi il turno successivo usava
    l'ordine di prima e -- peggio -- la pagina, che descrive il runtime perché
    è la sola misura che ha, alla ricarica rimostrava l'ordine vecchio: il
    salvataggio sembrava perso. Era la stessa divergenza che questa fetta
    chiude, spostata di un livello, e fino al Task 10 c'era una riga in pagina
    che la confessava.

    VERSIONE B (3.0.0): rimette in vigore anche il PONTE. `app["ponte_attivo"]`
    era una copia presa all'avvio da `BRIDGE_ENABLED`, e finche' quel valore
    veniva da un'opzione dell'add-on non poteva cambiare senza un riavvio.
    Adesso viene dall'archivio, che la pagina Modelli riscrive: se restasse
    fermo all'avvio, accendere il ponte dalla pagina tornerebbe 200 e non
    farebbe niente fino al riavvio successivo -- esattamente il difetto che il
    Task 10 ha chiuso per la catena. Qui e' l'UNICO posto che lo scrive.
    """
    from .model_activation import provider_in_catena
    cfg = app.get("models_config") or {}
    # Un valore solo, derivato una volta, letto da tutti: la spazzata
    # (`_reasoning_sweep`), l'instradamento (`handlers_chat.handle_chat`), la
    # pagina Consumi, il gate del lavoratore qui sotto. Nessuno dei quattro
    # ricalcola niente, quindi nessuno dei quattro puo' dire una cosa diversa.
    app["ponte_attivo"] = _ponte_attivo(cfg)
    # E il lavoratore del ponte SEGUE l'interruttore, invece di essere deciso
    # una volta all'avvio. Sono i due lati dello stesso fatto: accendere il
    # ponte senza far partire chi risponde vorrebbe dire accodare ogni turno in
    # una coda che nessuno serve, e ogni messaggio scadrebbe prima di ripiegare
    # sulla catena (Task 14) -- cioe' il bottone «Mettilo primo» sarebbe un
    # bottone che risponde 200 e fa aspettare. Spegnerlo senza fermarlo
    # lascerebbe un ciclo che interroga una coda vuota ogni tre secondi.
    _governa_lavoratore_del_ponte(app)
    router = app.get("llm_router")
    mappa = router._backend_map() if router is not None else {}
    # Chi può rispondere ADESSO: la stessa regola dell'avvio (`_risponde`),
    # RILETTA invece che ricordata. Un backend costruito, e -- per Ollama -- un
    # modello scelto: il runner locale esiste con il solo indirizzo, ma senza
    # un modello sarebbe un anello che `_ordered_backends` salta in silenzio
    # mentre la pagina lo disegna numerato (il buco che il Task 9 ha chiuso).
    risponde = {nome: b is not None for nome, b in mappa.items()}
    if risponde.get("ollama"):
        risponde["ollama"] = bool((cfg.get("ollama") or {}).get("modello"))
    catena = provider_in_catena(cfg.get("chain_order") or [], risponde)
    # UN calcolo, DUE copie: quella che la pagina riceve e quella che il router
    # usa. Sono lo stesso valore -- se divergessero, divergerebbero da sé
    # stesse -- e sono due oggetti perché nessuno dei due possa modificare
    # l'altro per sbaglio (stessa ragione del `list(_chain)` dell'avvio).
    app["catena_modelli"] = list(catena)
    if router is None:
        return
    # NIENTE ripiego sulla policy precedente quando la catena è vuota: una
    # catena esplicitamente vuota vale per quello che dice. Un `or
    # router._chat_policy` rimetterebbe in piedi la regola legacy tolta al
    # Task 7 -- pagina che dice «la catena è vuota, HIRIS non può rispondere»
    # e chat che risponde lo stesso, usando l'ordine di prima.
    router._chat_policy = list(catena)
    ollama = mappa.get("ollama")
    if ollama is not None:
        # L'unico valore della fetta che non si può leggere al momento
        # dell'uso: `AsyncOpenAI` cuoce il timeout nel client alla costruzione
        # (vedi `OpenAICompatRunner.applica_timeout`, che è un no-op quando il
        # numero non è cambiato).
        ollama.applica_timeout((cfg.get("ollama") or {}).get("timeout_s", 120))


async def _on_startup(app: web.Application) -> None:
    from .claude_runner import ClaudeRunner
    from .llm_router import LLMRouter
    # fetta E3 Task 7: `import time as _time` viveva fra gli import della
    # Sentinella (cancellati con lei), ma serve ancora qui sotto a
    # `_reasoning_sweep` (ponte push, vivo) -- spostato invece di perso.
    import time as _time

    # Pre-load static HTML so request handlers don't do sync open().read()
    # per request (would block the event loop). Cache invalidation happens via
    # _inject_version() on every render anyway.
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    for fname, key in (("index.html", "html_index"), ("config.html", "html_config")):
        path = os.path.join(static_dir, fname)
        try:
            with open(path, encoding="utf-8") as f:
                app[key] = f.read()
        except FileNotFoundError:
            logger.error("Static %s missing at %s", fname, path)
            app[key] = ""

    # fetta E4 Task 4 ("un bot solo"): prima `data_dir` si derivava da
    # `CHATBOTS_DATA_PATH` (un file per l'entita' Chatbot che non esiste
    # piu'). Ne' l'una ne' l'altra erano un'opzione dell'add-on (nessuna voce
    # in config.yaml/run.sh: solo un varco interno per i test) -- lo stesso
    # varco, letto direttamente come directory.
    #
    # Sta qui in cima, e non piu' sotto insieme al resto degli store, perche'
    # il token interno ci si conserva dentro (vedi subito sotto) e va risolto
    # prima che qualunque middleware possa servire una richiesta.
    data_dir = os.environ.get("HIRIS_DATA_DIR", "/data")
    app["data_dir"] = data_dir
    # Il token interno: se l'opzione dell'add-on e' vuota (il default di
    # config.yaml) viene generato e conservato in `data_dir`, cosi' che
    # sopravviva ai riavvii -- ed e' `prepara_token_interno` a ripubblicarlo
    # anche in `os.environ["INTERNAL_TOKEN"]`, perche' il worker del ponte
    # (`agent/runner.py::build_headers`) legge di li' a ogni giro e senza
    # quella riga continuerebbe a mandare l'header vuoto. Se generarlo o
    # scriverlo fallisce si torna "" e il rifiuto-per-default resta in piedi,
    # dichiarato nel log: vedi `token_interno.py`.
    app["internal_token"] = prepara_token_interno(data_dir)
    # CR-1: trusted Supervisor-ingress source CIDRs. The ingress-bypass in
    # internal_auth_middleware only applies to requests from these ranges, so a
    # forged X-Ingress-Path from a direct LAN/tunnel client cannot bypass the
    # internal_token. Default = the standard HA Supervisor Docker network.
    _cidrs = [c.strip() for c in os.environ.get(
        "SUPERVISOR_INGRESS_CIDR", "172.30.32.0/23").split(",") if c.strip()]
    app["supervisor_ingress_cidrs"] = _cidrs or ["172.30.32.0/23"]
    # fetta E3 Task 7: `app["execute_policy"]` (tiers/entity_tiers) e' uscita.
    # Era il semaforo condiviso fra la superficie remota (execute-API, uscita
    # fetta E2 Task 4) e la Sentinella (watcher/executor.py::execute, uscita
    # in questo task): con entrambe morte non resta nessun lettore. Con lei
    # esce `api/handlers_gateway_policy.py` (apply_saved_policy, che la
    # costruiva dalla policy UI-managed) e `hiris/app/security/semaphore.py`
    # (DANGEROUS_DOMAINS/effective_tier/summarize_autonomy) -- verificato con
    # grep che nessun modulo vivo li importa piu' (vedi il report del task).
    ha_base_url = os.environ.get("HA_BASE_URL", "http://supervisor/core")
    if not ha_base_url.startswith("http://supervisor"):
        logger.warning("HA_BASE_URL is %r — expected http://supervisor/core in production", ha_base_url)
    ha_client = HAClient(
        base_url=ha_base_url,
        token=os.environ.get("SUPERVISOR_TOKEN", ""),
    )
    await ha_client.start()
    app["ha_client"] = ha_client

    # Cosa Home Assistant sa fare, in questa casa. Costruito vuoto: si carica
    # al primo uso (`assicura_fresco`), non all'avvio -- un caricamento qui
    # allungherebbe il boot per una cosa che potrebbe non servire in questa
    # sessione, e fallirebbe in silenzio se HA non fosse ancora pronto.
    app["registro_servizi"] = RegistroServizi()

    # fetta E5 Task 5: qui l'add-on installava la card Lovelace dentro Home
    # Assistant (copia in www/, file di ingress, risorsa registrata). La card
    # e' uscita dal prodotto: adesso quelle tre tracce si **tolgono**, una
    # volta, riconoscendo solo cio' che l'add-on stesso aveva messo. Vedi il
    # commento esteso su `_disinstalla_card_lovelace`.
    hiris_slug = os.environ.get("HIRIS_SLUG", "hiris")
    await _disinstalla_card_lovelace(
        ha_base_url,
        os.environ.get("SUPERVISOR_TOKEN", ""),
        hiris_slug,
    )

    entity_cache = EntityCache()
    try:
        await entity_cache.load(ha_client)
    except Exception as exc:
        logger.warning("EntityCache load failed: %s", exc)
    ha_client.add_state_listener(entity_cache.on_state_changed)
    app["entity_cache"] = entity_cache

    # Task B7: la cache dell'Indice (`memoria/cache_indice.py`), di vita
    # LUNGA come `entity_cache` qui sopra -- non a ogni turno, come il
    # `DispatcherStrumenti` che la riceve (`costruisci_dispatcher_strumenti`
    # in `api/handlers_chat.py`). Prima di questo task `_cerca`/`_ricorda`
    # ricostruivano un `Indice` da zero A OGNI chiamata e lo buttavano
    # subito: si ripagava ogni volta la lettura dell'anagrafe E la
    # compilazione di un'espressione regolare per termine (misurato: la
    # compilazione domina il costo, non la lettura -- vedi il rapporto del
    # task). Costruita vuota qui, si riempie alla prima `cerca`/`ricorda`.
    app["cache_indice_strumenti"] = CacheIndice()

    # L'unico punto del prodotto che esegue qualcosa su Home Assistant
    # (`azione/porta.py`). Sta QUI, e non accanto a `registro_servizi` piu'
    # sopra, per l'ordine: la porta ha bisogno dello specchio dello stato
    # (`entity_cache`) per rileggere dopo aver agito, e sopra la cache non
    # esiste ancora -- `app.get("entity_cache")` avrebbe dato `None` e la
    # porta avrebbe rifiutato OGNI azione con «non vedo lo stato di questa
    # casa», per sempre. Costruita una volta e condivisa: la chat la usa oggi
    # via `costruisci_dispatcher_strumenti`, lo schedulatore e il brain
    # domani, senza che ne nasca una seconda.
    app["porta_azione"] = PortaAzione(ha_client, app["registro_servizi"],
                                      app.get("entity_cache"))

    # `data_dir` e' gia' risolto piu' in alto, insieme al token interno che ci
    # vive dentro (la lettura di `HIRIS_DATA_DIR` non e' stata duplicata: e'
    # stata spostata).
    # SP-2 Task 4: models-config store (chain_order), letta prima della
    # costruzione LLMRouter più sotto così il chain-build (Task 2 Step 5) può
    # leggere chain_order. Portava anche brain_model, uscito alla fetta E5
    # Task 7: il Brain (_holistic_reason) che l'avrebbe letto è già uscito
    # con la E3 -- vedi handlers_models.py.
    from .api.handlers_models import load_models_config, save_models_config
    from .migrazione_opzioni import semina
    # Task 6 -- versione A della migrazione. Il Supervisor scarta ogni chiave
    # fuori schema PRIMA che /data/options.json esista: togliere un'opzione
    # dallo schema, da sola, fa sparire IN SILENZIO il valore dell'utente, e
    # nessun ripiego in run.sh puo' recuperarlo. Finche' le opzioni ci sono
    # ancora, si copia il loro valore nell'archivio di HIRIS -- una volta sola,
    # dichiarandolo nel log. Le sette variabili qui sotto sono quelle che
    # run.sh esporta dalle opzioni di config.yaml (i nomi MAIUSCOLI non
    # coincidono con i nomi delle opzioni: la catena si segue per intero).
    _archivio, _copiate = semina(load_models_config(data_dir), {
        "BRIDGE_ENABLED": os.environ.get("BRIDGE_ENABLED", ""),
        "BRIDGE_DEADLINE_MIN": os.environ.get("BRIDGE_DEADLINE_MIN", ""),
        "CHAT_DAILY_CAP": os.environ.get("CHAT_DAILY_CAP", ""),
        "LOCAL_MODEL_NAME": os.environ.get("LOCAL_MODEL_NAME", ""),
        "OLLAMA_REQUEST_TIMEOUT": os.environ.get("OLLAMA_REQUEST_TIMEOUT", ""),
        "HIRIS_HIDE_FREE_MODELS": os.environ.get("HIRIS_HIDE_FREE_MODELS", ""),
        "LLM_STRATEGY": os.environ.get("LLM_STRATEGY", ""),
    }, log=logger)
    # Si persiste SEMPRE, anche quando non c'era niente da copiare: cio' che
    # deve arrivare al disco e' `seminato`. Se la semina restasse in memoria, il
    # rilascio successivo (versione B, opzioni fuori dallo schema) troverebbe di
    # nuovo un archivio non seminato E un ambiente muto -- cioe' esattamente la
    # perdita di valori che la versione A esiste per evitare.
    # `segni=True`: `seminato` e' un SEGNO DI MIGRAZIONE, non una decisione, e
    # l'avvio e' l'unico posto che lo scrive -- una PUT non lo tocca piu'
    # (`handlers_models._SEGNI_MIGRAZIONE`).
    save_models_config(data_dir, _archivio, segni=True)
    app["models_config"] = load_models_config(data_dir)

    # Task 5 SDD casa: l'anagrafe si costruisce all'avvio e si rifa' quando la
    # casa cambia. La costruzione iniziale non deve poter impedire il boot: un
    # Home Assistant non ancora pronto lascia l'anagrafe vuota con un avviso
    # nel log, non fa fallire l'add-on -- il primo evento di registro la
    # ricostruira' comunque.
    archivio_casa = ArchivioCasa(os.path.join(data_dir, "casa.db"))
    app["archivio_casa"] = archivio_casa
    try:
        await ricostruisci(ha_client, archivio_casa)
    except Exception as exc:
        logger.warning("costruzione iniziale dell'anagrafe fallita: %s", exc)
    ha_client.add_anagrafe_listener(programma_ricostruzione_anagrafe(ha_client, archivio_casa))

    # Task 4 SDD casa: il comportamento (il corpo di automazioni e script)
    # segue lo stesso principio -- prima lettura all'avvio senza poter
    # impedire il boot -- ma un meccanismo diverso: il comportamento cambia
    # con una cadenza di giorni, e per gli script non esiste ALCUN evento di
    # ricarica (il servizio non accetta un id), quindi lo tiene aggiornato
    # una sentinella periodica sull'mtime dei due file (vedi sotto, job
    # "hiris_comportamento_sentinella"). Un evento di registro entita' esiste
    # pero' (EVENTI_ANAGRAFE) e aggiungere/togliere un'automazione lo emette:
    # lo si aggancia qui sotto per forzare una rilettura anche quando l'mtime
    # non basta -- un'automazione tolta o messa in un PACCHETTO non tocca
    # `automations.yaml` (vedi `programma_rilettura_comportamento`).
    ha_config_dir = _find_ha_config_dir()
    guarda_comportamento = sentinella_comportamento(
        ha_client, archivio_casa, Path(ha_config_dir) if ha_config_dir else None
    )
    try:
        await guarda_comportamento()
    except Exception as exc:
        logger.warning("prima lettura del comportamento fallita: %s", exc)
    ha_client.add_anagrafe_listener(
        programma_rilettura_comportamento(guarda_comportamento))

    # Task 5 SDD casa: le plance, compresa la predefinita (url_path nullo)
    # che HIRIS non aveva mai visto. Cadenza propria (EVENTO_PLANCE, non i
    # registri): non stanno in _TABELLE, quindi una ricostruzione
    # dell'anagrafe non le tocca e viceversa. Come l'anagrafe, la prima
    # lettura non deve poter impedire il boot.
    try:
        await rileggi_plance(ha_client, archivio_casa)
    except Exception as exc:
        logger.warning("prima lettura delle plance fallita: %s", exc)
    ha_client.add_plance_listener(programma_rilettura_plance(ha_client, archivio_casa))

    # I servizi si rinfrescano su EVENTO, non a scadenza. Prima si ricaricavano
    # solo dopo 300 secondi, e per quei cinque minuti HIRIS rifiutava i servizi
    # di un'integrazione appena installata dicendo «non esiste in questa casa»:
    # una frase FALSA detta con sicurezza, che e' peggio di un «non lo so».
    #
    # Si INVALIDA e basta -- la rilettura la fa `assicura_fresco` al prossimo
    # comando. Installare un'integrazione emette una raffica di eventi, e una
    # lettura per ognuno sarebbe una tempesta per un dato che serve solo quando
    # qualcuno chiede di agire.
    _registro_servizi = app["registro_servizi"]
    ha_client.add_servizi_listener(lambda _tipo: _registro_servizi.invalida())

    # Task 4 SDD memoria: l'archivio della memoria vive nel suo file
    # (memoria.db), separato da casa.db -- e' cio' che l'utente ha detto e
    # cio' che HIRIS ne ha capito, non una REPLICA ricostruibile da HA (vedi
    # memoria/archivio.py). Nessuna lettura iniziale da fare qui: a
    # differenza dell'anagrafe non c'e' nulla da ricostruire all'avvio.
    archivio_memoria = ArchivioMemoria(os.path.join(data_dir, "memoria.db"))
    app["archivio_memoria"] = archivio_memoria

    # Task 1 fetta E4: il WebSocket verso HA parte qui -- non e' mai stato
    # dentro un "engine.start()" da quando quel task lo ha spostato (e ora
    # l'entita' Chatbot, con l'engine che la portava, e' uscita per intero:
    # fetta E4 Task 4, "un bot solo"). Deve stare dopo la registrazione di
    # tutti i listener sopra (state/anagrafe/plance, :633-690): aprirlo prima
    # lascerebbe una finestra di eventi senza nessuno ad ascoltarli.
    await ha_client.start_websocket()

    # fetta E4 Task 4: l'entita' Chatbot esce, sostituita dalle impostazioni
    # della chat -- un bot solo, senza id, coi default nel codice (mai
    # "assente": e' la chiusura per costruzione del degrado silenzioso che
    # handlers_chat.py aveva prima -- vedi impostazioni_chat.py). Gli ex
    # `engine.set_entity_cache(entity_cache)`/`set_archivi(archivio_casa,
    # archivio_memoria)` non hanno bisogno di un successore: erano gia'
    # orfani prima di questo task (nessun lettore in produzione dalla fetta
    # E4 Task 2 -- DispatcherStrumenti legge `app["entity_cache"]`/
    # `app["archivio_casa"]`/`app["archivio_memoria"]` direttamente, gia'
    # valorizzati sopra).
    impostazioni_chat = ImpostazioniChat.carica(data_dir)
    app["impostazioni_chat"] = impostazioni_chat

    # Versione A della migrazione, applicata a `giorni_conservazione`: la META'
    # CHE MANCAVA. `carica()` legge il valore attraverso `HISTORY_RETENTION_DAYS`
    # quando la chiave non c'e', ma non lo SCRIVE, e `salva()` ha un solo
    # chiamante di produzione (la PUT di «Impostazioni chat»). Chi quella pagina
    # non la apre mai non produce mai la chiave: al rilascio successivo, con
    # l'opzione fuori dallo schema e l'ambiente muto, il valore diventa il
    # default del codice (90) -- e per chi aveva scelto `0` («non cancellare
    # mai») la potatura delle 3 comincia a cancellare. Qui il valore appena
    # letto arriva al disco, una volta sola: dal secondo avvio il file porta la
    # chiave e questo ramo non fa piu' niente (e con lui tace anche la riga di
    # log della migrazione, che prima ricompariva a ogni riavvio).
    #
    # Un disco che non collabora non deve impedire il boot: si dichiara e si
    # prosegue, come per l'anagrafe e il comportamento qui sopra. Il valore in
    # memoria e' comunque quello giusto; a mancare sarebbe solo la persistenza,
    # e il cancello del rilascio la verifica esplicitamente
    # (docs/prova-modelli-e-catena.md, quarta precondizione).
    if il_file_non_porta_i_giorni(data_dir):
        try:
            impostazioni_chat.salva(data_dir)
            logger.info(
                "Migrazione (versione A): 'giorni_conservazione' (%d) e' stato "
                "scritto in impostazioni_chat.json -- da adesso si cambia dalla "
                "pagina Impostazioni chat, e l'opzione dell'add-on "
                "'history_retention_days' non serve piu'.",
                impostazioni_chat.giorni_conservazione,
            )
        except OSError as exc:
            logger.warning(
                "Migrazione (versione A): 'giorni_conservazione' (%d) NON e' "
                "stato scritto su disco (%s). Il valore vale per questo avvio, "
                "ma al prossimo riavvio si perde: 'history_retention_days' non "
                "e' piu' un'opzione dell'add-on, quindi non c'e' piu' niente da "
                "cui rileggerlo. Salvalo dalla pagina Impostazioni chat.",
                impostazioni_chat.giorni_conservazione, exc,
            )

    # Silenzio dichiarato, stessa disciplina di advisory.db/sentinel.db/ecc.
    # (tests/test_startup_legacy_db_silence.py): un chatbots.json (o il suo
    # predecessore agents.json) di un'installazione precedente non ha piu'
    # nessun lettore/scrittore -- l'entita' Chatbot e la sua migrazione
    # (ChatbotEngine._load, chatbot_engine.py) sono uscite per intero con
    # questo task. Decisione utente (vedi il commit): il prompt
    # personalizzato eventualmente salvato sul bot di default NON viene
    # migrato in ImpostazioniChat -- si riparte puliti, coi default nel
    # codice. I file restano su disco, intatti (mai dati utente cancellati
    # in /data).
    _chatbots_json_path = os.path.join(data_dir, "chatbots.json")
    _agents_json_path_legacy = os.path.join(data_dir, "agents.json")
    if os.path.exists(_chatbots_json_path) or os.path.exists(_agents_json_path_legacy):
        logger.info(
            "chatbots.json (o il suo predecessore agents.json) presente in %s "
            "da un'installazione precedente: da fetta E4 Task 4 nessun codice "
            "li legge ne' li scrive piu' (l'entita' Chatbot e' uscita, "
            "sostituita dalle impostazioni della chat). Il prompt "
            "personalizzato eventualmente salvato sul bot di default non "
            "viene migrato -- si riparte con i default nel codice. I file "
            "restano su disco, intatti.",
            data_dir,
        )

    # Lo scheduler (APScheduler) non era mai stato concettualmente
    # dell'entita' Chatbot -- ci viveva sopra solo perche' ChatbotEngine lo
    # ospitava (avviato/fermato nel suo start()/stop()), ma i lavori che
    # registra piu' sotto (ricarica inventario, sentinella comportamento,
    # retention, spazzata della coda di ragionamento)
    # non hanno niente a che fare coi chatbot. Con l'entita' uscita per
    # intero, trova casa direttamente qui.
    scheduler = AsyncIOScheduler()
    scheduler.start()
    app["scheduler"] = scheduler

    # fetta E3 Task 11: l'HealthMonitor esce -- il suo unico consumatore reale
    # era `snapshot["ha_health"]`, caduto col Task 4 (deps["get_health"] non
    # esisteva piu' nello snapshot della ronda). Le sue due rotte
    # (GET /api/health/ha, POST /api/health/ha/refresh) non avevano alcun
    # chiamante nel frontend. Con lui esce anche il SupervisorClient
    # (add-on, disco, aggiornamenti): l'HealthMonitor era il suo ultimo
    # lettore rimasto. SILENZIO DICHIARATO, stessa disciplina di advisory.db/
    # sentinel.db/proposals.db: un ha_health.json ereditato da
    # un'installazione precedente non viene cancellato (mai dati utente in
    # /data) ne' incontrato in silenzio.
    _ha_health_path = os.path.join(data_dir, "ha_health.json")
    if os.path.exists(_ha_health_path):
        logger.info(
            "ha_health.json presente in %s da un'installazione precedente: "
            "da fetta E3 Task 11 nessun codice lo legge ne' lo scrive piu' "
            "(HealthMonitor, SupervisorClient e le rotte /api/health/ha* "
            "sono usciti per intero). Il file resta su disco, intatto.",
            _ha_health_path,
        )

    # fetta E3 Task 10: le proposte escono per intero -- ProposalStore,
    # proxy/proposta_config.py (apply_ha_config), proxy/dashboard_backups.py
    # e le rotte /api/proposals*, /api/dashboards* (handlers_proposals.py,
    # handlers_dashboards.py). Scrivevano in HA col solo token del richiedente
    # (nessuna verifica umana indipendente -- mappa §3.5): l'ultima via
    # d'attuazione rimasta in un HIRIS che per decisione, ALLORA, non agiva.
    # L'azione e' rientrata con la fetta «comandare», ma rifatta e da una parte
    # sola: `esegui` -> `azione/porta.py`, che verifica contro l'installazione
    # e rilegge lo stato. Queste tre vie NON sono rientrate con lei -- scrivere
    # config, proposte e plance e' materia del progetto agenti, col perimetro
    # e la verifica umana. SILENZIO DICHIARATO, stessa disciplina di advisory.db/
    # sentinel.db (Task 6/7): un proposals.db o un dashboard_backups.json
    # ereditati da un'installazione precedente non vengono ne' cancellati
    # (mai dati utente in /data) ne' incontrati in silenzio.
    _proposals_db_path = os.path.join(data_dir, "proposals.db")
    if os.path.exists(_proposals_db_path):
        logger.info(
            "proposals.db presente in %s da un'installazione precedente: "
            "da fetta E3 Task 10 nessun codice lo legge ne' lo scrive piu' "
            "(ProposalStore e le rotte /api/proposals* sono uscite per "
            "intero). Il file resta su disco, intatto.",
            _proposals_db_path,
        )
    _dashboard_backups_path = os.path.join(data_dir, "dashboard_backups.json")
    if os.path.exists(_dashboard_backups_path):
        logger.info(
            "dashboard_backups.json presente in %s da un'installazione "
            "precedente: da fetta E3 Task 10 nessun codice lo legge ne' lo "
            "scrive piu' (dashboard_backups.py e le rotte /api/dashboards* "
            "sono uscite insieme all'apply delle proposte che salvava). Il "
            "file resta su disco, intatto.",
            _dashboard_backups_path,
        )

    # fetta E3 Task 13 ("escono le notifiche"): `notifiche.py` e il suo intero
    # cablaggio (`notify_config`, `_fetch_addon_slug`, `_ingress_click_path`,
    # `app["ingress_click_path"]`) sono usciti -- i tre chiamanti di
    # `send_notification` (health_scan.py Task 6, task_engine.py Task 9, il
    # ponte Sentinella/briefing di questo file Task 6/7) erano gia' tutti
    # usciti; questo cablaggio, lasciato intatto dal Task 9 con silenzio
    # dichiarato (vedi sotto, ora chiuso), era l'ultimo residuo -- mai piu'
    # letto da nessuno. Con lui escono le sei strade per dire una cosa a una
    # persona (mappa, elefante n.2) e la destinazione fissa HA_NOTIFY_SERVICE,
    # che nessuna interfaccia poteva cambiare: da qui in avanti HIRIS non
    # parla piu' senza essere interrogato -- esiste solo la chat. SILENZIO
    # DICHIARATO: notifiche.py era senza stato (chiamava HA/apprise/
    # retropanel dal vivo, nessuna scrittura in /data), quindi non c'e' alcun
    # file ereditato da controllare al boot. La settima strada nascera' con
    # un progetto proprio, con una destinazione configurabile -- non
    # `notify.notify` cablato.
    app["theme"] = os.environ.get("THEME", "auto")

    # fetta E3 Task 9 ("esce il Task Engine"): il TaskEngine (il pianificatore
    # innesco->azione, condannato dalla mappa per Legge III) e' uscito per
    # intero -- modulo, rotte /api/tasks*, gli hook nei due engine. Era
    # l'ULTIMO chiamante di `notifiche.send_notification` (le sue azioni
    # residue, dopo che `call_ha_service` era uscita nella review finale E2,
    # erano solo `send_notification`): il resto del cablaggio (notify_config
    # e affini) e' uscito col Task 13, vedi sopra. SILENZIO DICHIARATO:
    #  1b. `EntityCache.get_state` (proxy/entity_cache.py) e' orfano allo
    #     stesso modo: il suo unico chiamante era
    #     `TaskEngine._evaluate_condition()`. `proxy/entity_cache.py` NON si
    #     tocca in questa fetta (censimento conferma) -- lo raccoglie il
    #     Task 12.
    #  2. un `tasks.json` con task pendenti ereditato da un'installazione
    #     precedente non viene piu' ne' caricato ne' eseguito: nessun codice
    #     lo incontra piu'. Review finale fetta E3, Minor: la nota precedente
    #     diceva che "nessun log e' possibile" -- falso, come per gli altri
    #     file di questa lista: un `os.path.exists` sul path letterale e'
    #     esattamente cio' che si fa qui sotto, stessa disciplina di
    #     advisory.db/sentinel.db/portrait.db/proposals.db/
    #     dashboard_backups.json/ha_health.json. Il file resta su disco,
    #     intatto (mai dati utente cancellati in /data): va nell'elenco /data
    #     del Task 15 e nelle note di release.
    _tasks_json_path = os.path.join(data_dir, "tasks.json")
    if os.path.exists(_tasks_json_path):
        logger.info(
            "tasks.json presente in %s da un'installazione precedente: "
            "da fetta E3 Task 9 nessun codice lo legge ne' lo scrive piu' "
            "(il TaskEngine e le rotte /api/tasks* sono usciti per intero). "
            "Il file resta su disco, intatto.",
            _tasks_json_path,
        )

    api_key = os.environ.get("CLAUDE_API_KEY", "")
    usage_path = os.environ.get("USAGE_DATA_PATH", "/data/usage.json")
    local_model_url = os.environ.get("LOCAL_MODEL_URL", "")
    if local_model_url:
        try:
            from .backends.ollama import _validate_ollama_url
            _validate_ollama_url(local_model_url)
        except ValueError as exc:
            logger.error("Invalid LOCAL_MODEL_URL (%s) — disabling local model", exc)
            local_model_url = ""
    # L'UNICO uso rimasto di `LOCAL_MODEL_NAME` in questo file, e il nome lo
    # dice: serve a ricostruire la CREDENZIALE COM'ERA per la migrazione della
    # catena (sotto), dove la regola vecchia contava il modello insieme
    # all'indirizzo. Il modello che il runner usa arriva dall'archivio -- una
    # sola casa, `models_config["ollama"]["modello"]` (Task 9).
    #
    # DA VERSIONE B (3.0.0) `run.sh` NON esporta piu' questa variabile, ne' le
    # sei della semina, ne' i cinque `PROVIDER_*` letti dalla migrazione della
    # catena piu' sotto: l'opzione non c'e' piu'. Le letture restano perche'
    # un'installazione che salti la 2.5.0 e arrivi qui con l'ambiente ancora
    # popolato dal vecchio `run.sh` deve poter migrare -- non puo' succedere
    # via Supervisor, puo' succedere in sviluppo. Escono con la fetta
    # successiva, insieme a `_catena_com_era` e a `migrazione_opzioni`, quando
    # nessuna installazione potra' piu' arrivare non seminata (scadenza: la
    # prima fetta dopo il 14 agosto 2026). Fino ad allora il censimento le
    # elenca fra le «variabili lette e mai esportate da run.sh», ed e' corretto.
    _nome_modello_com_era = os.environ.get("LOCAL_MODEL_NAME", "")
    openai_api_key = os.environ.get("OPENAI_API_KEY", "")
    openrouter_api_key = os.environ.get("OPENROUTER_API_KEY", "")

    # ── Le credenziali, e nient'altro ──────────────────────────────────
    # fetta «la catena diventa l'unica verita'»: qui c'erano i cinque
    # interruttori `provider_*` incrociati con le credenziali
    # (`derive_active_providers`), cioe' la SECONDA rappresentazione dello
    # stato di un provider. Adesso l'unica cosa che si misura qui e' se la
    # credenziale c'e'; chi la USA lo dice `chain_order`.
    _credenziali = {
        "subscription": piano_ha_il_token(),
        "claude": bool(api_key),
        "openai": bool(openai_api_key),
        "openrouter": bool(openrouter_api_key),
        # La credenziale di Ollama e' il SOLO indirizzo. Prima era
        # `url and model`, cioe' il NOME DEL MODELLO faceva parte del test di
        # credenziale -- ma l'indirizzo e' cio' che si custodisce e il modello
        # e' cio' che si decide, e da questa fetta il modello vive
        # nell'archivio (Task 9). Conseguenza dichiarata: un'installazione con
        # URL presente e modello vuoto passa da «Ollama non credenziato» a
        # «Ollama credenziato, senza modello scelto» -- e la pagina lo mostra
        # invece di nasconderlo. Fino al Task 9 quello stato ha un BUCO
        # dichiarato: il runner di Ollama nasce ancora solo con
        # `url AND model`, quindi Ollama puo' stare in catena senza un backend
        # dietro. La migrazione non ce lo porta (`_catena_com_era` riceve la
        # credenziale VECCHIA, vedi sotto): ci si arriva solo mettendocelo a
        # mano dalla pagina Modelli.
        #
        # Task 9: il buco è CHIUSO, e non rimettendo il modello dentro la
        # credenziale (sarebbero di nuovo due concetti in un posto solo) ma
        # separando i due fatti: la credenziale resta l'indirizzo, e chi può
        # RISPONDERE si misura a parte (`_risponde`, più sotto) -- con quel
        # fatto si filtra la catena effettiva e si costruisce il runner. La
        # pagina mostra Ollama credenziato, fuori dalla catena, e dice che
        # manca il modello.
        "ollama": bool(local_model_url),
    }

    # ── La catena iniziale di un archivio che non ce l'ha ────────────────
    # Nata come seconda meta' della migrazione: la catena che HIRIS stava
    # usando copiata nell'archivio PRIMA che la derivazione dai cinque
    # interruttori sparisse. Senza quella copia, l'installazione del
    # proprietario -- cinque interruttori a false, credenziali presenti --
    # sarebbe passata da «due provider lavorano» a «zero provider».
    # Con la versione B i cinque interruttori NON esistono piu' e `run.sh` non
    # esporta piu' i cinque `PROVIDER_*`: qui non si copia piu' niente da
    # nessuna parte, si COMPONE una catena dalle credenziali presenti. E' la
    # sola regola di compatibilita' rimasta, e a differenza delle altre letture
    # di migrazione non si esaurisce: gira su ogni installazione nuova. Va
    # DECISA dalla fetta successiva, non ereditata (G3) -- e cancellarla e
    # basta farebbe nascere ogni installazione nuova con la catena vuota.
    # La guardia e' il SEGNO, non la forma della catena: una `chain_order`
    # vuota, da questa fetta, e' una decisione esprimibile in due click, e
    # regolarsi su di lei faceva ripopolare al riavvio una catena svuotata di
    # proposito. Vedi `semina_catena`.
    from .migrazione_opzioni import semina_catena
    if not app["models_config"].get("catena_seminata"):
        _catena_di_oggi = _catena_com_era(
            os.environ.get("LLM_STRATEGY", "balanced"),
            # Le credenziali COM'ERANO, non quelle di adesso: la credenziale di
            # Ollama comprendeva il nome del modello. Passare quelle nuove
            # farebbe entrare in catena un Ollama che la vecchia regola non ci
            # aveva MAI messo -- cioe' si inventerebbe invece di copiare.
            {**_credenziali, "ollama": bool(local_model_url and _nome_modello_com_era)},
            env_bool("BRIDGE_ENABLED"),
        )
        _arch, _da_salvare = semina_catena(dict(app["models_config"]),
                                           _catena_di_oggi, log=logger)
        if _da_salvare:
            save_models_config(data_dir, _arch, segni=True)
            app["models_config"] = load_models_config(data_dir)

    # La TERZA semina: il modello del Piano Claude Max. Fino alla 3.1.0 era un
    # effetto collaterale di `provider_models["claude"]` -- un campo solo per
    # due economie opposte, e l'impianto del proprietario girava sul piano col
    # modello scelto per non spendere sull'API. Da questa fetta e' un valore
    # suo, e qui si esegue un'ULTIMA volta la derivazione che se ne va, perche'
    # il giorno dell'aggiornamento niente cambi sotto l'utente.
    #
    # Salvataggio proprio e non fuso con quello della catena: fondere le due
    # semine in una scrittura sola le renderebbe una migrazione sola che puo'
    # trovarsi a meta', che e' esattamente cio' che i segni distinti esistono
    # per evitare.
    from .migrazione_opzioni import semina_modello_del_piano
    if not app["models_config"].get("piano_seminato"):
        from .agent.runner import modello_cli
        from .claude_runner import resolve_model
        _alias_di_oggi = modello_cli(resolve_model(
            "auto", "chat",
            app["models_config"].get("provider_models", {}).get("claude", ""),
        ))
        _arch_p, _da_salvare_p = semina_modello_del_piano(
            dict(app["models_config"]), _alias_di_oggi, log=logger)
        if _da_salvare_p:
            save_models_config(data_dir, _arch_p, segni=True)
            app["models_config"] = load_models_config(data_dir)

    # Qui viveva `_sub_first_class`, cioe' `_credenziali["subscription"] and
    # env_bool("PROVIDER_SUBSCRIPTION")`: il Piano Claude Max acceso col suo
    # token IMPLICAVA il ponte, e l'implicazione entrava in tutti e due i gate
    # (la spazzata e l'instradamento). E' USCITA con la versione B, insieme
    # all'opzione che la alimentava -- l'ultimo dei cinque interruttori ancora
    # letto, e l'ultima seconda rappresentazione del prodotto: con lei viva,
    # `app["ponte_attivo"]` poteva dire True mentre `ponte.attivo`, cioe' cio'
    # che la pagina Modelli mostra e scrive, diceva False. Il ponte adesso e'
    # un valore solo (`_ponte_attivo`, che legge l'archivio), e si accende
    # dalla pagina -- dove c'e' anche il bottone che lo fa in un gesto.
    #
    # Le due frasi che `run.sh` diceva su questo stato si sono spostate qui
    # sotto (`_avvisi_del_ponte`): da uno script di avvio l'archivio non si
    # legge, e restare in silenzio avrebbe reso muta proprio la transizione che
    # questa versione produce.

    # Provider di embedding. Fetta "esce il documentale": `MEMORY_RAG_K`/
    # `memory.rag_k` escono da qui e dalle altre quattro sedi dell'opzione --
    # erano il `k` del richiamo per somiglianza sull'archivio di conoscenza,
    # uscito con questa fetta; `app["memory_rag_k"]` non aveva gia' oggi
    # nessun lettore. Il provider resta costruito e pubblicato, ma DICHIARATO
    # INERTE: dopo questa fetta nessun percorso di HIRIS chiama piu'
    # `embed()` -- gli ultimi tre chiamanti (ingest Mayan, digest storico,
    # coda di approvazione della conoscenza) sono usciti tutti qui. Non e'
    # cancellato perche' "se e quando accendere i vettori" e' una decisione
    # esplicitamente rimandata dal contratto (docs/design/2026-08-05-la-
    # conoscenza-di-hiris.md, sezione 11) e la pagina Modelli lo mostra gia'
    # all'utente: la sua inerzia e' scritta nel CHANGELOG, non taciuta.
    mem_provider = os.environ.get("MEMORY_EMBEDDING_PROVIDER", "")
    mem_model = os.environ.get("MEMORY_EMBEDDING_MODEL", "")

    embedder = build_embedding_provider(
        provider=mem_provider,
        model=mem_model,
        openai_api_key=openai_api_key,
        local_model_url=local_model_url,
    )
    app["embedding_provider"] = embedder

    # ── Fetta "esce il documentale" ────────────────────────────────────────
    # Decisione del proprietario, 12 agosto 2026: «Al momento l'integrazione
    # documentale puo' essere tolta, la rivedremo poi, non serve.» Con Mayan
    # escono anche l'ARCHIVIO DI CONOSCENZA (`KnowledgeStore`, knowledge.db) e
    # la CATTURA DELLO STORICO (`HistoryStore`/`HistoryCapture`, history.db),
    # perche' scrivevano nello stesso posto e, letto il codice, non avevano
    # nessun altro consumatore vivo:
    #   - la chat prende il contesto da `costruisci_nucleo()` (Task 3 "il
    #     contesto della chat viene dal nucleo"), mai da `KnowledgeStore`;
    #   - la pagina Memoria interroga `memoria/archivio.py`, non la coda di
    #     approvazione (config/memoria-route.js lo dichiara per iscritto);
    #   - `search()`, `declared()`, `recent()`, `upcoming_obligations()` e
    #     `search_chunks()` non avevano gia' oggi nessun chiamante di
    #     produzione, e le quattro rotte /api/knowledge* nessun frontend.
    # Cioe': HIRIS registrava la casa a ogni `state_changed`, spendeva
    # embedding ogni notte alle 04:00 (per chi aveva scelto un provider: di
    # fabbrica l'opzione e' vuota) e ingeriva documenti in un archivio che
    # nessuno riapriva. Escono insieme il digest storico (brain/
    # history_digest.py), la migrazione una-tantum della memoria legacy
    # (brain/memory_migration.py, che scriveva solo li'), la pagina
    # Storicizzazione e le rotte /api/history/policy.
    #
    # Esce anche brain/privacy.py (`VaultStore`/`Pseudonymizer`, vault.db).
    # Le traduzioni promettevano che `mayan.sensitivity: sensitive`
    # "nasconde il contenuto all'AI cloud": era FALSO: nessun percorso
    # chiamava piu' `pseudonymize()`, quindi `last_pseudonym_map` restava
    # sempre vuota e i due `detokenize` lavoravano su un dizionario vuoto.
    # Niente da detokenizzare, quindi niente da smascherare per errore -- ma
    # la promessa non era solo non mantenuta, era contraddetta: `mayan_ingest`
    # passava all'embedder il testo OCR INTEGRALE del documento, senza
    # guardare `sensitivity`. Con `memory.embedding_provider` di fabbrica
    # ("" -> NullEmbedder, zero rete) e con `model2vec`/`ollama` quel testo
    # non usciva dall'impianto; con `openai` usciva in chiaro verso
    # api.openai.com. Il CHANGELOG 2.1.0 lo dice all'utente per esteso, per
    # provider. La promessa esce con l'opzione che la dichiarava.
    #
    # SILENZIO DICHIARATO, stessa disciplina di advisory.db/portrait.db/
    # sentinel.db piu' sotto: i file di un'installazione precedente NON
    # vengono cancellati (mai dati utente in /data), ma il loro incontro si
    # dichiara nel log invece di restare muto.
    _knowledge_db_path = os.path.join(data_dir, "knowledge.db")
    if os.path.exists(_knowledge_db_path):
        logger.info(
            "knowledge.db presente in %s da un'installazione precedente: "
            "dalla fetta \"esce il documentale\" nessun codice lo legge ne' lo "
            "scrive piu' (l'archivio di conoscenza, la coda di approvazione, "
            "il digest storico e l'ingest dei documenti sono usciti). "
            "Il file resta su disco, intatto.",
            _knowledge_db_path,
        )

    _legacy_memory_db_path = os.path.join(data_dir, "hiris_memory.db")
    if os.path.exists(_legacy_memory_db_path):
        logger.info(
            "hiris_memory.db presente in %s da un'installazione precedente: "
            "la migrazione una-tantum che lo travasava nell'archivio di "
            "conoscenza (brain/memory_migration.py) e' uscita con l'archivio "
            "stesso, quindi nessun codice lo legge piu'. Il file resta su "
            "disco, intatto.",
            _legacy_memory_db_path,
        )

    _history_db_path = os.path.join(data_dir, "history.db")
    if os.path.exists(_history_db_path):
        logger.info(
            "history.db presente in %s da un'installazione precedente: "
            "dalla fetta \"esce il documentale\" nessun codice lo legge ne' lo "
            "scrive piu' (la cattura dello storico, la compattazione delle "
            "03:30 e il digest delle 04:00 sono usciti). La cronaca della "
            "casa la tiene Home Assistant. Il file resta su disco, intatto.",
            _history_db_path,
        )

    _history_policy_path = os.path.join(data_dir, "history_policy.json")
    if os.path.exists(_history_policy_path):
        logger.info(
            "history_policy.json presente in %s da un'installazione "
            "precedente: la pagina Storicizzazione e le rotte "
            "/api/history/policy che lo leggevano e scrivevano sono uscite. "
            "Il file resta su disco, intatto.",
            _history_policy_path,
        )

    _vault_db_path = os.path.join(data_dir, "vault.db")
    if os.path.exists(_vault_db_path):
        logger.info(
            "vault.db presente in %s da un'installazione precedente: "
            "brain/privacy.py (VaultStore/Pseudonymizer) e' uscito. Se il file "
            "non e' vuoto contiene DATI PERSONALI IN CHIARO: la colonna "
            "`value` della mappa PII<->token non e' mai stata cifrata "
            "(cifratura at-rest differita e mai fatta). Nessun codice lo "
            "legge piu' e nessuna interfaccia lo svuota: cancellarlo e' "
            "sicuro, ed e' una decisione tua. Fino ad allora resta su disco, "
            "intatto.",
            _vault_db_path,
        )

    # Ricarica dell'inventario entita' dopo un avvio senza Home Assistant.
    # `entity_cache.load` piu' sopra logga e prosegue se fallisce: senza questo
    # lavoro la cache resterebbe "mai caricata" fino al riavvio dell'addon, e
    # gli strumenti che la leggono continuerebbero a rispondere "non ancora
    # pronto" per sempre.
    #
    # Due minuti: un'indisponibilita' passeggera (riavvio del core, rete che
    # balbetta) rientra entro il giro successivo invece che alla prossima notte.
    # Il costo con Home Assistant giu' per davvero e' una GET /api/states ogni
    # due minuti -- meno della ronda della sentinella -- e appena la lettura
    # riesce il lavoro torna a essere il controllo di una bandiera, senza
    # toccare piu' Home Assistant.
    async def _ricarica_inventario() -> None:
        await ricarica_inventario_entita(app.get("entity_cache"), ha_client)

    scheduler.add_job(
        _ricarica_inventario,
        trigger="interval", minutes=2,
        id="hiris_entity_cache_reload", replace_existing=True,
        misfire_grace_time=120,
    )

    # Task 4 SDD casa: la sentinella dell'mtime, registrata come lavoro
    # periodico come gli altri qui sopra. Cinque minuti: il comportamento
    # cambia con una cadenza di giorni, non serve un giro piu' stretto, e il
    # costo di un giro a vuoto sono solo due `stat()`.
    scheduler.add_job(
        guarda_comportamento,
        trigger="interval", minutes=5,
        id="hiris_comportamento_sentinella", replace_existing=True,
        misfire_grace_time=300,
    )

    # Daily retention job (chat messages only -- knowledge/memory items no
    # longer expire, Task 6 "la memoria non evapora": handle_save_memory
    # stopped computing a valid_until, so purge_expired_chatbot had no more
    # work fed to it and was removed).
    #
    # Task 12: la fonte del numero di giorni non e' piu' il globale di modulo
    # `chat_store.HISTORY_RETENTION_DAYS` (uscito dal modulo) ma
    # `app["impostazioni_chat"].giorni_conservazione` -- letto AD OGNI GIRO
    # dentro la chiusura, non catturato una volta sola all'avvio: un PUT su
    # /api/impostazioni-chat riassegna quella chiave a caldo
    # (`handlers_impostazioni.handle_save_impostazioni`), e la potatura di
    # stanotte deve vedere il valore che l'utente ha scelto oggi, non quello
    # con cui l'add-on e' partito.
    from .chat_store import delete_old_messages as _delete_old_messages

    def _run_retention() -> None:
        giorni = app["impostazioni_chat"].giorni_conservazione
        if giorni > 0:
            n = _delete_old_messages(data_dir, giorni)
            if n:
                logger.info("Retention: deleted %d old chat messages", n)

    scheduler.add_job(
        _run_retention,
        trigger="cron",
        hour=3,
        minute=0,
        id="hiris_retention",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Fetta "esce il documentale": qui vivevano tre lavori schedulati, usciti
    # insieme ai loro soggetti.
    #   - "hiris_history_compact" (03:30) compattava history.db;
    #   - "hiris_history_digest" (04:00) chiamava il provider di embedding per
    #     ogni entita' storicizzata e scriveva insight `status="approved"`
    #     nell'archivio di conoscenza -- che nessun lettore di produzione
    #     riapriva. Era la spesa notturna senza consumatore;
    #   - "hiris_mayan_ingest" (ogni `mayan.poll_minutes`) piu' il giro
    #     iniziale all'avvio: ingeriva i documenti taggati in Mayan nello
    #     stesso archivio, con lo stesso esito.
    # Nessuno slot app "mayan_client"/"knowledge_store"/"history_store",
    # nessun listener `state_changed` per la cattura, nessuna rotta.

    from .backends.openai_compat_runner import OpenAICompatRunner
    from .backends.openrouter_runner import OpenRouterRunner

    # fetta E3 Task 6: l'AdvisoryStore (le segnalazioni del Brain -- batterie
    # scariche, entita' non disponibili, automazioni rotte, domini pericolosi,
    # entita' senza area) esce insieme a tutti i suoi lettori/scrittori: il
    # resoconto delle 08:00, i solleciti ogni 6 ore e la scansione di salute
    # ogni 30 minuti che la popolava. SILENZIO DICHIARATO: nessuno slot app
    # "advisory_store", nessuna rotta /api/brain/advisories*, nessuna
    # scrittura. Un'installazione precedente puo' avere un advisory.db
    # popolato su disco -- non lo cancelliamo (mai dati utente in /data), ma
    # se c'e' lo diciamo esplicitamente nel log invece di incontrarlo in
    # silenzio: un pass muto sarebbe indistinguibile da un guasto.
    _advisory_db_path = os.path.join(data_dir, "advisory.db")
    if os.path.exists(_advisory_db_path):
        logger.info(
            "advisory.db presente in %s da un'installazione precedente: "
            "da fetta E3 Task 6 nessun codice lo legge ne' lo scrive piu' "
            "(il Brain che parlava -- resoconto, solleciti, scansione di "
            "salute -- e' uscito). Il file resta su disco, intatto.",
            _advisory_db_path,
        )

    # fetta E3 Task 12 ("esce il ritratto"): PortraitStore/portrait.py sono
    # usciti per intero -- i loro unici lettori (il Brain, la Sentinella)
    # erano gia' caduti nei Task 4-7, e l'unico scrittore era il job
    # schedulato "hiris_portrait_observe" (cancellato piu' sotto insieme al
    # resto del cablaggio). SILENZIO DICHIARATO, stessa disciplina di
    # advisory.db/sentinel.db (Task 6/7): un portrait.db ereditato da
    # un'installazione precedente non viene cancellato (mai dati utente in
    # /data) ma il suo incontro va dichiarato nel log, non muto.
    _portrait_db_path = os.path.join(data_dir, "portrait.db")
    if os.path.exists(_portrait_db_path):
        logger.info(
            "portrait.db presente in %s da un'installazione precedente: "
            "da fetta E3 Task 12 nessun codice lo legge ne' lo scrive piu' "
            "(il ritratto della casa -- portrait.py, portrait_store.py, il "
            "job schedulato 'hiris_portrait_observe' -- e' uscito per "
            "intero). Il file resta su disco, intatto.",
            _portrait_db_path,
        )

    # fetta E3 Task 7 ("esce la Sentinella intera, e il semaforo che la E2 le
    # aveva promesso"): guardiano (Guardian), ragionatore (watcher/
    # reasoner.py::reason/_llm_reason/_gather_context), esecutore (watcher/
    # executor.py::execute) e le closure che li collegavano (_notify,
    # _propose, _on_wake) sono usciti per intero, insieme a `sentinel_store`
    # (sentinel.db), al job "hiris_sentinel_reset" e al listener su
    # `ha_client`. Con Agentbot (T3), ronda (T4) e Brain (T5-6) gia' usciti,
    # il guardiano svegliava un ragionatore la cui Decisione arrivava a un
    # `executor.execute()` che da fetta E2 "propone, non agisce" -- l'ultimo
    # pezzo che poteva decidere qualcosa da solo. `hiris/app/watcher/` e
    # `hiris/app/security/` (il semaforo, DANGEROUS_DOMAINS/effective_tier/
    # summarize_autonomy) sono cancellati per intero: verificato con grep che
    # nessun modulo vivo li importa piu' (i lettori del semaforo erano
    # `watcher/executor.py` e `api/handlers_gateway_policy.py`, entrambi
    # usciti con lui; vedi il report del task). L'unico chiamante vivo che
    # importava qualcosa da `watcher/` -- `agent/runner.py`, il ponte push,
    # che riusava `watcher.reasoner.parse_decision` -- si e' portato dietro
    # quella funzione (ora vive li', non e' stata cancellata).
    #
    # Silenzio dichiarato: un `sentinel.db` popolato da un'installazione
    # precedente non incontra piu' nessun lettore/scrittore (nessuno slot
    # app, nessuna rotta, nessun listener). Il file non viene cancellato
    # (mai dati utente in /data), ma se c'e' lo diciamo esplicitamente nel
    # log invece di incontrarlo in silenzio -- stessa disciplina di
    # advisory.db (Task 6): un pass muto sarebbe indistinguibile da un
    # guasto.
    _sentinel_db_path = os.path.join(data_dir, "sentinel.db")
    if os.path.exists(_sentinel_db_path):
        logger.info(
            "sentinel.db presente in %s da un'installazione precedente: "
            "da fetta E3 Task 7 nessun codice lo legge ne' lo scrive piu' "
            "(la Sentinella -- guardiano, ragionatore, esecutore -- e' "
            "uscita per intero). Il file resta su disco, intatto.",
            _sentinel_db_path,
        )

    # ── Ponte push (Piano A, fetta 3): coda di lavori di reasoning per il
    # runner remoto. Resta -- lo usa il ramo chat sotto (Slice 4b) -- ma
    # `_execute_decision`/`app["execute_decision"]` sono usciti qui (fetta
    # E3 Task 4): applicavano una Decisione del runner attraverso lo stesso
    # executor.execute()/semaforo/adapters della revisione olistica, che non
    # esiste piu'. handlers_reasoning.py (il consumer di questo slot) non
    # trova piu' nulla in `app["execute_decision"]` -- vedi il commento li'.
    from .reasoning.queue import ReasoningQueue

    reasoning_queue = ReasoningQueue(os.path.join(data_dir, "reasoning.db"))
    app["reasoning_queue"] = reasoning_queue

    # Chat-via-abbonamento (Slice 4b, Task 1): submit-branch for kind="chat"
    # jobs — writes the runner's reply into chat_store instead of actuating
    # the house. fetta E4 Task 5 ("un bot solo"): chat_store ha smesso di
    # avere un concetto di id (o di "conversation_id") -- c'e' UNA
    # cronologia, quindi non c'e' piu' nulla da instradare per chiave.
    from .chat_store import append_messages as _append_chat_messages
    from .chat_store import _is_toxic_assistant as _is_toxic_chat_reply

    async def _submit_chat_reply(reply_text: str) -> None:
        if not reply_text:
            return
        # Final-review Fix 3 (Slice 4b): mirror the sync path's persistence
        # guard (handlers_chat.py) so a reply that arrived via the async
        # runner gets the same treatment as one from the local runner.
        #
        # Fetta "esce il documentale": qui c'era anche una detokenizzazione
        # (`app["pseudonymizer"].detokenize(reply_text, {})`), uscita con
        # brain/privacy.py. Era gia' un no-op dichiarato: la si chiamava
        # sempre con una mappa VUOTA -- questo percorso non pseudonimizza
        # nulla di suo -- e dopo l'uscita del dispatcher che popolava
        # `last_pseudonym_map` nessun percorso del prodotto pseudonimizzava
        # piu' niente. Toglierla non cambia il testo persistito di un
        # carattere.
        if _is_toxic_chat_reply(reply_text):
            # Drop silently, same as the sync path: the next turn must not
            # inherit a poisoned/leaked history. There's no HTTP response
            # here to carry a visible error (the caller already got a 202
            # long ago) -- the poll route's chat_reply_skipped handling is
            # the user-facing side of this.
            return
        _append_chat_messages([{"role": "assistant", "content": reply_text}], data_dir)
    app["submit_chat_reply"] = _submit_chat_reply

    # Qui viveva `app["chat_daily_cap"]`, copia di `CHAT_DAILY_CAP` presa
    # all'avvio e unico lettore di quell'ambiente per il comportamento. E'
    # CANCELLATA dal Task 14: il tetto giornaliero del ponte si legge adesso
    # dall'archivio (`ponte.tetto_giornaliero`, `handlers_chat.
    # _piano_puo_rispondere`), dove l'utente lo cambia e dove il Task 6 lo
    # aveva gia' copiato senza dargli lettori. Erano due rappresentazioni dello
    # stesso numero (invariante 1) e la copia in memoria era pure ferma
    # all'avvio: chi salvava dalla pagina Modelli non cambiava il tetto che il
    # turno subiva. Stessa strada del Task 10 per `ponte.scadenza_min` e
    # `ollama.timeout_s`, e stesso residuo dichiarato: `CHAT_DAILY_CAP` resta
    # letta -- solo dalla semina qui sopra, per copiare il valore com'era --
    # finche' il Task 13 non toglie l'opzione dallo schema.

    # fetta E3 Task 5: esce il Brain auto-proponente. Il Task 4 aveva lasciato
    # orfani DI PROPOSITO `brain.coverage_review`, `brain.suggestions`,
    # `brain.cognitive_loop`, `brain.learned_thresholds`, `brain.brain_trace`,
    # `brain.reasoning_log`, `brain.feed` e `api.handlers_suggestions` --
    # proponevano a un `_execute_decision` che il Task 4 stesso aveva gia'
    # cancellato. Tutti e otto i moduli sono usciti qui, insieme al loro
    # cablaggio (SuggestionStore/ReasoningLog sopra, rotte /api/suggestions*
    # e /api/brain/feed+reasoning piu' sotto). SILENZIO DICHIARATO:
    # un'installazione con suggestions.db o brain_reasoning.db popolati da
    # prima di questo task non incontra piu' nessun codice -- nessuno slot
    # app, nessuna rotta, nessun log possibile perche' nessun codice li
    # apre piu' (vedi il commento sopra dove prima viveva questo cablaggio).
    # `tools.proposal_tools.create_automation_proposal` restava orfano qui
    # (il modulo non era nel perimetro del Task 5): nessun chiamante di
    # produzione, solo citazioni in commenti/metadata (handlers_gateway_
    # policy.py's PROPOSE_TOOLS, gia' morto da prima) e nella lista UI del
    # Designer (static/config/templates.js: era una checkbox inerte, ed e'
    # uscita col file alla fetta E5 Task 6).
    # Il Task 8 di questa fetta ha cancellato l'intera cartella `tools/`,
    # `proposal_tools.py` incluso: la citazione sopra e' storica.
    # `watcher.policy.apply_brain_detector/remove_brain_detector/
    # apply_brain_tuning/remove_brain_tuning` perdevano qui il loro ultimo
    # chiamante di produzione (`brain.suggestions`/`brain.cognitive_loop`):
    # non erano nel perimetro del Task 5 (non nel file-list del brief),
    # dichiarati orfani per chi avrebbe toccato la Sentinella/il semaforo.
    # Il Task 7 di questa fetta li ha raccolti: `watcher/policy.py` e'
    # uscito per intero insieme al resto di `watcher/` -- la nota sopra e'
    # storica.

    # fetta E3 Task 6, SILENZIO DICHIARATO: qui viveva il job schedulato
    # "hiris_health_scan" (interval `HIRIS_HEALTH_SCAN_MINUTES`, 30' di
    # default -- 8 controlli, 5 sulla casa e 3 sul sistema via Supervisor,
    # riconciliati nell'AdvisoryStore con push delle sole segnalazioni gravi
    # nuove o riaperte, l'opzione add-on `brain_notify_high`). `health_
    # checks.py` importava il semaforo (la casa vecchia); l'archivio che
    # scriveva (`brain/advisory_store.py`) e' uscito sopra, insieme al
    # canale (`notifiche.py`) che portava le sue segnalazioni gravi
    # all'utente. Da questo task nessuna scansione di salute gira piu' --
    # comportamento deciso, non un guasto: vedi il commit e il report.
    # `HIRIS_HEALTH_SCAN_MINUTES` esce con il suo unico lettore (non era
    # un'opzione add-on: nessuna voce in config.yaml/run.sh/translations).
    # fetta E3 Task 5: la prune notturna del reasoning capture log era gia'
    # uscita insieme a `reasoning_log`/ReasoningLog (nessun job
    # `hiris_reasoning_prune`).

    # fetta E3 Task 12 ("esce il ritratto"), SILENZIO DICHIARATO: qui viveva
    # il job schedulato "hiris_portrait_observe" (interval
    # HIRIS_PORTRAIT_OBSERVE_MINUTES, 15' di default), che chiamava
    # `_osserva_la_casa` per aggiornare la linea di base del ritratto in
    # `portrait.db`. Con `_osserva_la_casa`/`_portrait_context`/
    # PortraitStore/portrait.py usciti per intero, nessuna osservazione gira
    # piu' -- comportamento deciso, non un guasto: vedi il commit e il
    # report. `HIRIS_PORTRAIT_OBSERVE_MINUTES` esce con il suo unico
    # lettore (non era un'opzione add-on: nessuna voce in
    # config.yaml/run.sh/translations).

    # ── Ponte push (Piano A): spazzata dei job scaduti senza risposta dal
    # runner remoto. Il ramo chat resta (Slice 4b): un job "chat" scaduto
    # resta semplicemente 'expired', esposto alla sua stessa route di poll.
    # fetta E3 Task 4: il ramo di fallback olistico (ragionava in locale via
    # _run_decision) e' uscito con `_holistic_reason`, l'unico produttore di
    # job kind="holistic" -- nessun job di quel tipo viene piu' accodato.
    # Silenzio dichiarato: un job kind="holistic" qui puo' arrivare SOLO da
    # un reasoning.db lasciato da un'installazione precedente questo
    # deploy -- nessun fallback locale lo ragiona piu', quindi non e' un
    # pass silenzioso: un log esplicito lo dichiara prima di lasciarlo
    # scadere (sweep_expired lo ha gia' marcato 'expired' sopra).
    async def _reasoning_sweep() -> None:
        # Lo STESSO VALORE dell'instradamento, non la stessa espressione: fino
        # alla 2.5.0 i due gate chiamavano `_ponte_attivo` ciascuno per conto
        # suo sugli stessi due ingressi, e il fail-safe «mai accodare in una
        # coda che nessuno spazza» reggeva sul fatto che le due chiamate
        # restassero identiche. Adesso il valore e' derivato UNA volta
        # (`_ricalcola_catena`) e qui si LEGGE: due letture dello stesso slot
        # non possono divergere nemmeno per distrazione. Ed e' anche cio' che
        # rende la spazzata sensibile al ponte spento dalla pagina, senza un
        # riavvio.
        if not app.get("ponte_attivo"):
            return
        for job in reasoning_queue.sweep_expired(_time.time()):
            if job.get("kind") != "chat":
                logger.warning(
                    "reasoning sweep: job %s di tipo %r orfano (ponte olistico rimosso, fetta E3 Task 4), scartato",
                    job.get("job_id"), job.get("kind"))
        # fetta «la catena diventa l'unica verita'», Task 14. Lo sweep NON ruba
        # il lavoro al poll: `sweep_expired` guarda solo 'pending'/'claimed' e
        # non tocca i job in 'ripiego' -- e' cio' che rende sicura la
        # convivenza fra i due, visto che il ripiego vive nella rotta di poll
        # (ogni 3,5 s) e non qui (ogni 2 minuti).
        #
        # Ma un job rimasto in 'ripiego' oltre il DOPPIO della scadenza e' un
        # ripiego che si e' schiantato: il processo e' caduto mentre chiedeva
        # alla catena, e nessuno chiudera' piu' quel job. Non puo' restare in
        # volo per sempre -- `prune` cancella 'decided', 'expired' e 'failed',
        # mai 'ripiego' -- e finche' resta li' tiene anche la conversazione
        # bloccata sul 409 (`has_pending_chat` conta i ripieghi come in volo).
        # Il doppio, e non la scadenza secca, perche' il ripiego COMINCIA alla
        # scadenza: il margine e' il tempo che la catena ha per rispondere.
        reasoning_queue.fallisci_ripieghi_bloccati(
            _time.time() - 2 * 60 * int(
                (app.get("models_config") or {}).get("ponte", {}).get("scadenza_min", 5)))
        reasoning_queue.prune(_time.time() - 7 * 86400)

    scheduler.add_job(
        _reasoning_sweep, trigger="interval", minutes=2,
        id="hiris_reasoning_sweep", replace_existing=True, misfire_grace_time=120)

    # Il punto di cablaggio -- da qui `handle_chat` sa se instradare il turno
    # sul ponte -- NON e' piu' qui: e' `_ricalcola_catena`, l'unica riga del
    # prodotto che scrive `app["ponte_attivo"]`, e viene chiamata sia all'avvio
    # (`_rimetti_in_vigore`, piu' sotto) sia a ogni salvataggio della pagina
    # Modelli. Doveva spostarsi: il valore viene adesso dall'archivio, che la
    # pagina riscrive, e un cablaggio fatto una volta all'avvio avrebbe
    # riprodotto per il ponte il difetto che il Task 10 ha chiuso per la
    # catena -- salvataggio accettato con 200, effetto solo al riavvio.
    #
    # `handlers_chat._bridge_on` verifica soltanto che `app["reasoning_queue"]`
    # sia agganciata -- e in produzione lo e' sempre, perche' la coda si crea
    # incondizionatamente poche righe piu' su -- quindi da sola non dice che
    # qualcuno reclami o spazzi quei job. E' `app["ponte_attivo"]` a dirlo:
    # tenere il gate li', invece di insegnare l'archivio a `_bridge_on`, lascia
    # ai test di handlers_chat.py la possibilita' di agganciare o sganciare la
    # coda senza toccare la configurazione.
    #
    # Fusione dei due interruttori (2.4.0): qui c'erano DUE derivazioni --
    # `_bridge_enabled` e `_chat_via_subscription_cfg` -- combinate da un AND,
    # ed era quello il fail-safe. Poi UNA espressione condivisa (2.5.0). Adesso
    # e' UN VALORE condiviso: il fail-safe non e' sparito, ha finito di
    # cambiare natura -- da regola da non sbagliare, a struttura.

    # fetta E3 Task 4: l'arrivo serale (watcher/arrival.py, ArrivalWatcher)
    # e' uscito -- riusava lo stesso adapter `_on_situation` della ronda,
    # uscito con lei (vedi il commento piu' in alto). Nessun sostituto:
    # nessun path di actuation restava dietro, solo una proposta che ora
    # nessuno genera piu'.

    # Il modello per provider, come LETTURA e non come valore. È la metà
    # nascosta del difetto peggiore trovato dal progetto: fino alla 2.4.1 qui
    # si leggeva `provider_models` UNA volta e lo si passava ai runner come
    # argomento di costruzione, mentre `api/handlers_chat._enqueue_chat_job`
    # rilegge `app["models_config"]` a OGNI turno -- quindi lo stesso valore
    # aveva effetto immediato sul ponte e solo al riavvio sull'API, e la pagina
    # ne dichiarava uno solo (invariante 4: «un valore si applica in un modo
    # solo»). La chiusura chiude su `app`, non su un valore: `models_config` è
    # RIASSEGNATO a ogni PUT (`handle_save_models_config`), quindi la lettura
    # vede sempre l'ultimo archivio, e la sostituzione del dizionario intero
    # è ciò che rende la lettura atomica -- un turno non può mai vedere metà
    # di un salvataggio.
    def _modello_di(provider: str):
        def leggi() -> str:
            return ((app.get("models_config") or {})
                    .get("provider_models", {}).get(provider, ""))
        return leggi

    def _modello_locale() -> str:
        """Il modello di Ollama non vive in `provider_models` (è un fantasma
        lì: `_clean_provider_models` lo scarta in lettura e in scrittura): la
        sua unica casa è `models_config["ollama"]["modello"]`."""
        return (app.get("models_config") or {}).get("ollama", {}).get("modello", "")

    # Il modello di Ollama, dalla SUA UNICA CASA. Fino alla 2.4.1 veniva da
    # `LOCAL_MODEL_NAME`, cioè da un'opzione dell'add-on: era il modello messo
    # dove si custodiscono le credenziali invece che dove si prendono le
    # decisioni, e `provider_models["ollama"]` restava un fantasma
    # (`_PROVIDER_MODEL_KEYS` non lo contiene, `_clean_provider_models` lo
    # scarta in lettura E in scrittura -- e resta così: NON è un doppione da
    # far rivivere).
    _modello_ollama = (app["models_config"].get("ollama") or {}).get("modello", "")
    # Chi può davvero RISPONDERE. Non è una seconda rappresentazione della
    # credenziale: sono due fatti diversi, e per quattro provider su cinque
    # coincidono. Per Ollama no -- l'indirizzo è ciò che si custodisce, il
    # modello è ciò che si decide -- e la differenza è esattamente il buco che
    # il Task 7 aveva dichiarato: con la sola credenziale, Ollama poteva finire
    # in `catena_modelli` senza un runner dietro, cioè comparire come anello
    # numerato in una pagina che descrive il runtime mentre
    # `LLMRouter._ordered_backends` lo saltava in silenzio.
    _risponde = {**_credenziali,
                 "ollama": bool(local_model_url and _modello_ollama)}

    claude_runner = None
    if api_key and _credenziali["claude"]:
        claude_runner = ClaudeRunner(
            api_key=api_key,
            usage_path=usage_path,
            leggi_modello=_modello_di("claude"),
        )

    _usage_base, _usage_ext = os.path.splitext(usage_path)
    _usage_ext = _usage_ext or ".json"

    openai_runner = None
    if openai_api_key and _credenziali["openai"]:
        openai_runner = OpenAICompatRunner(
            base_url="https://api.openai.com/v1",
            api_key=openai_api_key,
            usage_path=f"{_usage_base}_openai{_usage_ext}",
            leggi_modello=_modello_di("openai"),
        )

    ollama_runner = None
    # Il runner locale nasce con l'INDIRIZZO, che è la credenziale, e non più
    # con `url AND modello`. Il modello è una decisione, si legge a ogni uso, e
    # cambiarlo dalla pagina Modelli deve poter valere dal prossimo messaggio:
    # con la costruzione legata anche al modello, chi ne sceglieva uno su
    # un'installazione partita senza si sarebbe trovato con un gesto che non fa
    # niente -- il backend non esiste, e servirebbe un riavvio, cioè la
    # didascalia che questa fetta toglie. Chi può RISPONDERE resta `_risponde`
    # (indirizzo E modello) e governa la catena: senza modello il runner c'è ma
    # nessuno lo mette in catena, quindi `_ordered_backends` non lo incontra.
    if local_model_url:
        ollama_runner = OpenAICompatRunner(
            base_url=local_model_url.rstrip("/") + "/v1",
            api_key="ollama",
            locale=True,
            usage_path=f"{_usage_base}_ollama{_usage_ext}",
            # Dall'ARCHIVIO, non da `OLLAMA_REQUEST_TIMEOUT`: è lo stesso
            # numero che la pagina Modelli mostra sul connettore, e leggerlo in
            # due posti era la seconda rappresentazione (invariante 1).
            timeout_s=(app["models_config"].get("ollama") or {}).get("timeout_s", 120),
            leggi_modello=_modello_locale,
        )
    if _risponde["ollama"]:
        # Quick reachability check — warn but don't abort startup.
        try:
            import aiohttp as _aiohttp
            async with _aiohttp.ClientSession() as _sess:
                async with _sess.get(
                    local_model_url.rstrip("/") + "/api/tags",
                    timeout=_aiohttp.ClientTimeout(total=5),
                ) as _r:
                    if _r.status == 200:
                        _tags = await _r.json()
                        _names = [m.get("name", "") for m in _tags.get("models", [])]
                        if _modello_ollama in _names:
                            logger.info("Ollama OK — modello '%s' pronto", _modello_ollama)
                        else:
                            logger.warning(
                                "Ollama raggiungibile ma il modello '%s' non è nella lista %s — "
                                "pull potrebbe essere necessario",
                                _modello_ollama, _names,
                            )
                    else:
                        logger.warning("Ollama /api/tags ha risposto con status %s", _r.status)
        except Exception as _exc:
            logger.warning(
                "Ollama non raggiungibile a %s (%s) — le richieste al modello locale falliranno",
                local_model_url, _exc,
            )

    openrouter_runner = None
    if openrouter_api_key and _credenziali["openrouter"]:
        openrouter_runner = OpenRouterRunner(
            api_key=openrouter_api_key,
            usage_path=f"{_usage_base}_openrouter{_usage_ext}",
            leggi_modello=_modello_di("openrouter"),
        )
        logger.info("OpenRouter abilitato (200+ modelli via openrouter.ai)")

    # Store config for /api/models endpoint
    # La chiave di Claude API era una locale di questa funzione e non arrivava
    # mai nell'app: `_config_has_credential("claude")` la cercava in ambiente,
    # e nessuno la usava per altro. Dalla fetta «il modello del piano» serve
    # anche a `_fetch_claude_models`, e sta dove stanno le altre due.
    app["claude_api_key"] = api_key
    app["openai_api_key"] = openai_api_key
    app["openrouter_api_key"] = openrouter_api_key
    app["local_model_url"] = local_model_url
    # `app["local_model_name"]` e' USCITO col Task 9. Era una copia del modello
    # di Ollama presa all'avvio: dopo il Task 6 la casa del valore e'
    # l'archivio, e una copia in memoria che nessuna PUT aggiorna e' la
    # seconda rappresentazione da cui questa fetta esiste per liberarsi -- i
    # suoi due lettori (`handle_list_models`, `_modelli_in_uso`) avrebbero
    # continuato a mostrare il modello di prima dopo un salvataggio. Leggono
    # `models_config["ollama"]["modello"]`, come tutti.

    # ── La catena: l'appartenenza, e nient'altro ──────────────────────────
    # fetta «la catena diventa l'unica verita'»: qui c'erano l'ordine di
    # strategia, l'override manuale e `reconcile_chain` che li fondeva
    # accodando i provider attivi mancanti. Adesso c'e' una cosa sola --
    # l'ordine scritto nell'archivio, filtrato a chi ha una credenziale. Chi
    # diventa credenziato NON entra da solo: compare in «Fuori dalla catena»,
    # a un gesto di distanza.
    #
    # La scrittura di `app["catena_modelli"]` e' UNA, fuori dal ramo dei
    # runner: prima ce n'erano due -- `list(_chain)` qui e `[]` nell'else -- e
    # la seconda non era coperta da nessun test perche' vive dentro
    # `_on_startup`, che ogni fixture azzera (il debito E dichiarato al
    # Task 1). Con una sola scrittura non c'e' piu' un secondo posto da tenere
    # allineato: il debito si chiude togliendo il doppione, non coprendolo.
    from .model_activation import provider_in_catena
    # Il filtro e' `_risponde`, non `_credenziali` (Task 9): in catena ci puo'
    # stare solo chi ha un backend costruito. Con la sola credenziale, un
    # `chain_order` che nomina Ollama senza un modello scelto avrebbe messo in
    # catena un anello che il router salta -- la pagina lo avrebbe disegnato
    # numerato, col suo connettore, e nessun messaggio ci sarebbe mai passato.
    # Un anello a schermo che non risponde mai e' esattamente la bugia che
    # questa fetta ritira, e la differenza fra i due dizionari e' UNA riga.
    _chain = provider_in_catena(app["models_config"].get("chain_order") or [], _risponde)
    # Nessuna perdita in silenzio: chi ha una credenziale e NON sta in catena
    # non viene consultato, e prima `reconcile_chain` lo accodava da solo. Il
    # cambio di comportamento si dichiara nel registro, dove un operatore lo
    # cerca, invece di lasciarlo dedurre da un provider che non risponde mai.
    _fuori = [p for p in ("claude", "openrouter", "openai", "ollama")
              if _risponde.get(p) and p not in _chain]
    if _fuori:
        logger.info(
            "Provider con credenziale FUORI dalla catena: %s. HIRIS non li "
            "consulta: un provider e' usato se e solo se sta in catena, e in "
            "catena ci si mette dalla pagina Modelli.", ", ".join(_fuori),
        )
    # La catena EFFETTIVA, pubblicata perche' la pagina Modelli possa RICEVERE
    # la decisione invece di ricostruirla. E' lo stesso oggetto che entra nel
    # router poche righe sotto: se un giorno divergessero, divergerebbero da se
    # stessi -- che e' il difetto che questa fetta chiude, reso impossibile
    # invece che vietato.
    app["catena_modelli"] = list(_chain)

    if any([claude_runner, openai_runner, openrouter_runner, ollama_runner]):
        router = LLMRouter(
            claude=claude_runner,
            openai=openai_runner,
            openrouter=openrouter_runner,
            ollama=ollama_runner,
            # `strategy=` NON si passa piu' (versione B): era
            # `os.environ.get("LLM_STRATEGY")`, cioe' l'opzione dell'add-on, e
            # `LLMRouter` la usa SOLO nel ramo `model_chain is None` -- che qui
            # non si prende mai, perche' `model_chain=_chain` e' sempre
            # esplicito. Era un valore letto e mai usato: toglierlo non cambia
            # nessun comportamento, e lasciarlo avrebbe fatto sopravvivere
            # l'ultima lettura di comportamento di un'opzione uscita. Il
            # parametro resta in `LLMRouter` come default di libreria, dove i
            # suoi test lo pinnano.
            model_chain=_chain,
            # Il ciclo di ripiego e' il SOLO posto in cui HIRIS vede come si
            # comporta un provider davvero, e fino a questa fetta lo buttava
            # via. Lo stesso oggetto che la pagina Modelli legge: se fossero
            # due, divergerebbero -- e la pagina racconterebbe un traffico che
            # non e' quello che c'e' stato.
            registro=app["registro_esiti"],
        )
        app["claude_runner"] = claude_runner  # backward compat (may be None)
        app["llm_router"] = router
    else:
        app["claude_runner"] = None
        app["llm_router"] = None

    # ── Rimettere in vigore, a caldo ──────────────────────────────────────
    # Fuori da entrambi i rami, e con UNA implementazione sola: il ramo `else`
    # (nessun provider configurato) è il PRIMO gesto di chi installa HIRIS, e
    # senza `app["ricalcola_catena"]` la prima PUT solleverebbe
    # `TypeError: 'NoneType' object is not callable`.
    #
    # Si chiama anche QUI, all'avvio. Non serve a mettere in vigore niente di
    # nuovo -- `_chain` è appena entrata nel router -- ma fa sì che la strada
    # che rimette in vigore sia la STESSA che mette in vigore la prima volta:
    # se le due derivazioni potessero divergere, divergerebbero all'avvio,
    # dove ogni prova le guarda, invece che al primo salvataggio di un utente.
    def _rimetti_in_vigore() -> None:
        _ricalcola_catena(app)

    app["ricalcola_catena"] = _rimetti_in_vigore
    _rimetti_in_vigore()

    # ── Chat-via-abbonamento worker in-addon (Plan 2B Task 4) ──────────────
    # Polls the internal reasoning queue and reasons via `claude -p` under the
    # user's Claude subscription (CLAUDE_CODE_OAUTH_TOKEN) instead of metered
    # API spend. Il server MCP interno che la chat usava per i tool di
    # CONTROLLO casa usci' con la Fetta E2 Task 3 e non e' tornato: quando
    # l'azione e' rientrata (fetta «comandare») e' rientrata come UNO strumento
    # nel catalogo unico, non come un secondo server. Questo worker non ragiona
    # piu' in puro testo -- dalla fetta "il ponte riceve gli strumenti"
    # (parita' B) riceve gli strumenti dalla rotta `POST /api/mcp` registrata
    # piu' sotto, e il prompt lo dichiara al modello solo quando la sonda ha
    # confermato che ci sono davvero (vedi agent/runner.py).
    #
    # QUI c'era il `if should_start_agent_worker():` che lo avviava una volta
    # sola. Vive adesso in `_governa_lavoratore_del_ponte`, che
    # `_rimetti_in_vigore()` ha gia' chiamato poche righe sopra: l'avvio e il
    # salvataggio dalla pagina Modelli passano dalla STESSA strada, che e' la
    # disciplina del Task 10 (la catena) applicata al ponte. Se fosse rimasto
    # qui, accendere il ponte dalla pagina instraderebbe la chat su una coda
    # senza nessuno a servirla: ogni turno aspetterebbe la scadenza prima di
    # ripiegare, e il bottone «Mettilo primo» sarebbe un bottone che risponde
    # 200 e fa aspettare.
    #
    # Le due frasi sul ponte che `run.sh` non puo' piu' dire (da uno script di
    # avvio l'archivio non si legge): ponte acceso senza token, e token senza
    # ponte. Sono l'ultima cosa dell'avvio perche' sono le prime che un
    # operatore cerca in coda al registro quando la chat costa piu' del
    # previsto.
    for _avviso in _avvisi_del_ponte(bool(app.get("ponte_attivo")),
                                     _credenziali["subscription"]):
        logger.warning(_avviso)


async def _on_cleanup(app: web.Application) -> None:
    from .chat_store import close_all_stores
    # M-2 (Plan 2B final review, fast-follow): stop the reasoning-queue
    # consumer (agent_worker_task) and bound the wait. A claimed job can be
    # sitting inside run_loop's
    # run_in_executor offload of the blocking `run_once` (subprocess.run
    # timeout=300 + httpx.Client timeout=330) -- an unbounded
    # `await aw` after cancel() would then stall addon shutdown for up to
    # ~5 minutes, since cancelling the outer task does not interrupt a
    # thread already blocked inside the executor. `asyncio.wait_for` caps
    # that wait; on timeout we give up on a clean join and move on rather
    # than hang shutdown, and TimeoutError is suppressed same as
    # CancelledError since either outcome means "stop waiting, proceed".
    aw = app.get("agent_worker_task")
    if aw is not None:
        aw.cancel()
        with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
            await asyncio.wait_for(aw, timeout=5)
    if "reasoning_queue" in app:
        app["reasoning_queue"].close()
    if "archivio_casa" in app:
        app["archivio_casa"].chiudi()
    if "archivio_memoria" in app:
        app["archivio_memoria"].chiudi()
    # fetta E4 Task 4: lo scheduler non e' piu' ospitato da un
    # `engine.stop()` -- l'entita' Chatbot (e l'engine che lo portava) e'
    # uscita per intero. `wait=False`, stessa disciplina di
    # `ChatbotEngine.stop()` (chatbot_engine.py, uscito con lei): non
    # aspettare i job in corso al momento dello shutdown.
    if "scheduler" in app:
        app["scheduler"].shutdown(wait=False)
    await app["ha_client"].stop()
    close_all_stores()


@web.middleware
async def _security_headers(request: web.Request, handler) -> web.Response:
    response = await handler(request)
    # Static assets are content-fingerprinted (?v=HASH via _inject_version), so a
    # changed file always gets a fresh URL. As defence-in-depth against the HA
    # Ingress proxy / heuristic browser caching serving a stale copy under an old
    # URL, force revalidation: "no-cache" allows storing but requires a
    # conditional request (304 when unchanged) before the cached copy is reused.
    if request.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "no-cache")
        # Task B8 punto 5: se il client chiede un asset con un ?v=<impronta>
        # che non corrisponde all'impronta ATTUALE di quel file, il server sa
        # in quel momento che quel client ha un guscio vecchio -- e' cosi'
        # che il difetto misurato (bottone del guscio HTML mancante mentre i
        # testi del backend erano gia' aggiornati) sarebbe stato diagnosticato
        # subito invece che scoperto un giorno dopo. Non cambia cosa viene
        # servito: il file resta quello, si aggiunge solo la riga di log.
        richiesta = request.query.get("v")
        if richiesta:
            rel_path = request.path.lstrip("/")  # "static/chat/main.js"
            attuale = _asset_fingerprint(rel_path, "")
            if attuale and richiesta != attuale:
                logger.warning(
                    "Asset richiesto con impronta stantia: %s (chiesta=%s, attuale=%s) "
                    "-- il client ha un guscio HTML vecchio",
                    rel_path, richiesta, attuale,
                )
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    # X-Frame-Options omesso: HA Ingress carica l'UI in un iframe
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'",
    )
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    return response


def create_app() -> web.Application:
    app = web.Application(middlewares=[
        internal_auth_middleware,
        csrf_middleware,
        _security_headers,
    ])

    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)

    static_path = os.path.join(os.path.dirname(__file__), "static")
    # Build stamp: hash del contenuto del frontend, per verificare in UI/health
    # QUALE build gira davvero (diagnostica cache vs container non ricostruito).
    app["build_stamp"] = _compute_build_stamp(static_path)

    # Che cosa e' successo davvero, per provider (fetta «cosa e' successo
    # davvero», Task 11). Nasce QUI e non in `_on_startup` per due ragioni,
    # entrambe di sostanza: non ha niente da cui dipendere (e' un dizionario in
    # memoria con un orologio), e la pagina Modelli lo legge anche in un
    # processo dove i runner non ci sono -- un add-on senza nessuna
    # credenziale ha comunque una pagina Modelli, e quella pagina deve poter
    # dire «non l'hai ancora usato» invece di non dire niente.
    #
    # Nessuna persistenza: muore col processo, e «da quando l'add-on e'
    # partito» e' un'eta' dichiarabile (progetto §11.2). Nessuna scadenza: un
    # esito di due ore fa resta li', vecchio, e la pagina ne dice l'eta'.
    app["registro_esiti"] = RegistroEsiti()
    app.router.add_static("/static", static_path, show_index=False)

    app.router.add_get("/", _serve_index)
    app.router.add_get("/config", _serve_config)
    app.router.add_get("/api/health", _handle_health)
    # fetta E4 Task 4 ("un bot solo"): GET /api/status esce insieme
    # all'entita' Chatbot -- il suo unico contenuto era `agents.total`/
    # `agents.enabled` (handlers_status.py, cancellato), un conteggio che non
    # significa piu' niente con un bot solo. Nessun chiamante frontend (era
    # gia' una rotta solo-test nel censimento, prima di questo task).
    app.router.add_get("/api/config", handle_config)
    app.router.add_get("/api/usage", handle_usage)
    app.router.add_post("/api/usage/reset", handle_reset_usage)
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_get("/api/chat/reply/{job_id}", handle_chat_reply_poll)
    # fetta E4 Task 3 ("un bot solo"): le rotte di creazione/CRUD (POST
    # /api/chatbots, GET/PUT/DELETE /api/chatbots/{agent_id}, .../usage,
    # .../usage/reset) sono uscite -- erano le tre strade sopravvissute alla
    # E3 (wizard, editor vuoto, onboarding della chat) che creavano tutte
    # l'entita' gia' attiva, il contrario di quanto prescrive lo scope.
    # GET /api/chatbots e' restata come superficie di compatibilita'
    # dichiarata (Global Constraints) finche' avesse un chiamante: la chat
    # se n'e' staccata al Task 3 di questa fetta (nome e tetto di turni da
    # GET /api/impostazioni-chat, il "connesso" da GET api/health), la card
    # e' uscita dal prodotto al Task 5, e i tre chiamanti rimasti nella SPA
    # di configurazione (config/dashboard.js, config/models-route.js,
    # config/usage-route.js) sono usciti ai Task 7 e 8. Col gate verde
    # (`grep -rn "api/chatbots" hiris/app/static/` a zero fetch, solo
    # commenti storici) la rotta e il suo handler sono usciti col Task 10.
    app.router.add_get("/api/entities", handle_list_entities)
    # fetta E5 Task 4 ("il frontend"): erano
    # GET/DELETE /api/chatbots/{agent_id}/chat-history -- un placeholder
    # {agent_id} che il handler non leggeva mai da match_info (c'e' UNA
    # cronologia dalla E4 Task 5). Rotta onesta: nessun identificatore nel
    # percorso, perche' non c'e' niente da identificare. Chiamante unico e
    # vivo: static/chat/agents.js (ripristino e cancellazione della
    # cronologia) -- riscritto in questo stesso task. La card Lovelace non le
    # ha mai chiamate (teneva la propria cronologia in localStorage) ed e'
    # comunque uscita per intero con la E5 Task 5. Gli handler non cambiano:
    # non hanno mai visto l'id, cambia solo la firma pubblica della rotta.
    app.router.add_get("/api/chat/cronologia", handle_get_chat_history)
    app.router.add_delete("/api/chat/cronologia", handle_clear_chat_history)
    # fetta E3 Task 9: le tre rotte /api/tasks* sono uscite insieme al Task
    # Engine -- hanno lasciato rotte la pagina #/tasks (tasks-route.js) e il
    # pannello Task della chat (chat/tasks.js) per due fette. Il Task 6
    # della E5 le ha cancellate entrambe, con le due voci di menu che ci
    # portavano.
    # fetta E5 Task 2 ("il frontend"): le impostazioni della chat hanno di
    # nuovo una superficie. Fino a qui i sette campi di `ImpostazioniChat` si
    # cambiavano solo scrivendo a mano `/data/impostazioni_chat.json`
    # (`salva()` non aveva chiamanti di produzione). Il PUT passa dallo stesso
    # `csrf_middleware` di ogni altra rotta di scrittura -- nessuna
    # autenticazione propria -- e la pagina che lo chiama e' `#/impostazioni`
    # (static/config/impostazioni-route.js), nello stesso commit.
    app.router.add_get("/api/impostazioni-chat", handle_get_impostazioni)
    app.router.add_put("/api/impostazioni-chat", handle_save_impostazioni)
    app.router.add_get("/api/models", handle_list_models)
    app.router.add_get("/api/models/config", handle_get_models_config)
    app.router.add_put("/api/models/config", handle_save_models_config)
    # fetta E3 Task 11: le rotte /api/health/ha e /api/health/ha/refresh sono
    # uscite con l'HealthMonitor -- vedi il silenzio dichiarato su
    # ha_health.json in _on_startup. /api/health (poco sopra, il build
    # stamp) e' un'altra cosa e resta.
    # fetta E3 Task 10: le rotte /api/proposals* e /api/dashboards*
    # (backups/restore) sono uscite con le proposte -- vedi il commento
    # sopra la ProposalStore che viveva qui. Restano rotte, senza rimpiazzo
    # in questa fetta: #/proposals, il pannello Proposte della chat e le
    # card/badge in Dashboard (elenco E5).
    # Fetta "esce il documentale": escono le quattro rotte /api/knowledge*
    # (coda di approvazione, approva, rifiuta, aggiunta manuale -- nessun
    # frontend le chiamava piu' da quando la pagina Memoria interroga
    # /api/memoria) e le due /api/history/policy con la pagina
    # Storicizzazione che le disegnava.

    # fetta E3 Task 3: le quattro rotte CRUD /api/agentbots sono uscite
    # insieme ad api/handlers_agentbots.py. La pagina #/agentbots
    # (agentbot-route.js), il suo editor (agentbot-editor.js) e il wizard
    # (create-wizard.js: POST /api/agentbots) sono rimasti per due fette a
    # ricevere 404 -- non riparati, per costruzione. Il Task 6 della E5 li
    # ha cancellati: nessuna interfaccia nomina piu' queste rotte.
    #
    # fetta E3 Task 7: /api/gateway/policy, /api/gateway/autonomy-summary
    # (api/handlers_gateway_policy.py) e /api/sentinel/policy,
    # /api/sentinel/timeline (api/handlers_sentinel.py) sono uscite insieme
    # alla Sentinella e al semaforo che le serviva -- entrambi i moduli
    # handler sono cancellati per intero. La pagina #/gateway
    # (gateway-route.js) e il riquadro "Autonomia" dell'editor Chatbot
    # (chatbot-editor.js -> POST /api/gateway/autonomy-summary) sono rimasti
    # per due fette a ricevere 404 -- non riparati, per costruzione. Il
    # Task 6 della E5 li ha cancellati entrambi, insieme alla voce di menu
    # "Accessi Gateway" che portava alla pagina.

    from .api.handlers_reasoning import handle_reasoning_claim, handle_reasoning_submit
    app.router.add_post("/api/reasoning/claim", handle_reasoning_claim)
    app.router.add_post("/api/reasoning/submit", handle_reasoning_submit)

    # fetta "il ponte riceve gli strumenti" (parita' B) Task 1: l'adattatore
    # JSON-RPC che porta gli strumenti della casa anche al ponte via
    # abbonamento -- l'unico modo in cui la CLI `claude` accetta strumenti
    # nostri (vedi il docstring di api/handlers_mcp.py).
    #
    # CHI LA CHIAMA: il sottoprocesso `claude` che il worker del ponte avvia
    # dentro l'add-on (`--mcp-config`), e la sonda `tools/list` che il runner
    # fa PRIMA di comporre il turno (`agent/runner.py::sonda_strumenti`).
    # Fino al Task 3 di questa fetta nessun chiamante di produzione esisteva e
    # la rotta fu un ORFANO DICHIARATO, contato da `scripts/censimento.py` fra
    # le «rotte HTTP chiamate solo dai test»: col Task 3 l'orfano e' stato
    # raccolto e il censimento e' tornato a 43.
    #
    # COSA NON E': una superficie remota. Vive sul listener che c'e' gia',
    # raggiungibile su `127.0.0.1` dall'interno del container -- nessuna porta
    # nuova, nessun port mapping, nessuna opzione `Network`, nessuna opzione
    # dell'add-on. L'handler accetta inoltre la SOLA autenticazione a token
    # interno (`auth_via == "token"`): ne' l'ingress del Supervisor ne' la
    # valvola di sviluppo `HIRIS_ALLOW_NO_TOKEN` la aprono.
    from .api.handlers_mcp import handle_mcp, prepara_contatori
    app.router.add_post("/api/mcp", handle_mcp)
    # M-2 della review totale della fetta: i contatori dei giri di strumento
    # per turno si creano QUI, mentre l'app si compone, e non alla prima
    # `tools/call` servita. Scrivere in `app[...]` a richiesta gia' servita fa
    # emettere ad aiohttp «Changing state of started or joined application is
    # deprecated» -- oggi un warning nell'output della suite, con aiohttp 4 un
    # errore.
    prepara_contatori(app)

    # fetta E3 Task 5: /api/brain/feed e /api/brain/reasoning sono uscite col
    # Brain auto-proponente (handle_brain_feed componeva reasoning_log/
    # brain.feed, handle_brain_reasoning leggeva il solo reasoning_log --
    # entrambi usciti).
    # fetta E3 Task 6: /api/brain/advisories* e' uscita con loro --
    # `handlers_brain.py` (che a questo punto conteneva solo le advisories)
    # e' cancellato per intero. La Dashboard e il badge della nav le
    # chiamavano ancora, e degradavano in silenzio; la fetta E5 Task 8 ha
    # raccolto quel debito: la home e' stata riscritta come «Cosa HIRIS sa»
    # e il badge e' uscito con la sua fonte. Nessun chiamante superstite in
    # `static/` -- verificato col grep in quel task.

    # Task 6 SDD casa: sola lettura, per guardare dal vivo cio' che l'archivio
    # ha ricostruito -- la suite verde non prova che la lettura funzioni.
    # Dalla fetta E5 Task 8 e' anche la fonte della home della
    # configurazione: vedi il commento di /api/nucleo piu' sotto.
    from .api.handlers_casa import handle_get_casa
    app.router.add_get("/api/casa", handle_get_casa)

    # Task 4 SDD memoria: la pagina "cio' che HIRIS sa" -- la decisione (5)
    # del progetto della memoria. Nessun frontend in questo task: si guarda
    # dal browser come /api/casa.
    from .api.handlers_memoria import (
        handle_get_memoria, handle_patch_memoria, handle_delete_memoria,
    )
    app.router.add_get("/api/memoria", handle_get_memoria)
    app.router.add_patch("/api/memoria/{id}", handle_patch_memoria)
    app.router.add_delete("/api/memoria/{id}", handle_delete_memoria)

    # Task 3 SDD nucleo: vedere cio' che il modello vedra' -- il testo
    # ESATTO che compone `casa.nucleo.componi()`, non una sua descrizione.
    # Nata senza faccia, come /api/casa e /api/memoria: dalla fetta E5
    # Task 8 una faccia ce l'ha -- la home della configurazione
    # (`static/config/dashboard.js`) legge questa rotta e /api/casa, e non
    # ne ricalcola nessun dato per conto proprio.
    from .api.handlers_casa import handle_get_nucleo
    app.router.add_get("/api/nucleo", handle_get_nucleo)

    return app


_NO_CACHE = {"Cache-Control": "no-store"}

# Per-file content fingerprints for cache-busting. Keyed by asset path
# relative to the static dir; value is (mtime, short-sha1). Hashing a given
# file happens at most once per change (invalidated by mtime).
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
_ASSET_FP_CACHE: dict[str, tuple[float, str]] = {}
# Matches local asset refs like  src="static/config/main.js"  /  href="static/hiris.css"
# External URLs (Google Fonts, https://…) and query-stringed refs are left untouched.
_ASSET_REF_RE = re.compile(r'(src|href)="(static/[^"?]+\.(?:js|css))"')


def _asset_fingerprint(rel_path: str, fallback: str) -> str:
    """Return a short content hash for a static asset, cached by mtime.

    Because the fingerprint is derived from the file's actual bytes, ANY edit
    changes the query string and forces browsers (and the HA Ingress proxy) to
    re-fetch — no manual version bump required. Falls back to the app version
    string if the file can't be read (keeps old behaviour as a floor)."""
    # rel_path is like "static/config/main.js"; strip the "static/" mount prefix.
    abs_path = os.path.join(_STATIC_DIR, rel_path[len("static/"):])
    try:
        mtime = os.path.getmtime(abs_path)
    except OSError:
        return fallback
    cached = _ASSET_FP_CACHE.get(rel_path)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    try:
        with open(abs_path, "rb") as f:
            digest = hashlib.sha1(f.read()).hexdigest()[:10]
    except OSError:
        return fallback
    _ASSET_FP_CACHE[rel_path] = (mtime, digest)
    return digest


def _compute_build_stamp(static_dir: str) -> str:
    """Hash breve del contenuto di TUTTI gli asset frontend: cambia se e solo se
    un file del frontend cambia. Esposto in /api/health e mostrato in UI, cosi'
    si verifica CON CERTEZZA quale build sta girando davvero -- distingue
    "cache del browser/CDN" da "container addon non ricostruito" nel giro di
    live-verify (prima non c'era modo di saperlo). Deterministico: root e file
    in ordine, il path relativo entra nell'hash insieme al contenuto."""
    h = hashlib.sha1()
    try:
        for root, _dirs, files in sorted(os.walk(static_dir)):
            for name in sorted(files):
                p = os.path.join(root, name)
                rel = os.path.relpath(p, static_dir).replace(os.sep, "/")
                try:
                    with open(p, "rb") as f:
                        h.update(rel.encode("utf-8"))
                        h.update(hashlib.sha1(f.read()).digest())
                except OSError:
                    continue
    except OSError:
        return "unknown"
    return h.hexdigest()[:12]


def _inject_version(html: str, version: str, build_stamp: str = "") -> str:
    """Append a per-file content fingerprint (?v=HASH) to local static asset
    URLs so browsers bust cache whenever a file's content actually changes.

    Replaces the previous single global ?v=VERSION scheme, which only busted
    caches on a release version bump and left stale JS/CSS in place during any
    edit that didn't change config.yaml's version field.

    Task B8: se `build_stamp` e' dato, dichiara anche da quale build il guscio
    e' nato -- una `<meta name="hiris-build" content="...">` in `<head>`, col
    valore che l'app ha gia' (`app["build_stamp"]`, calcolato una sola volta in
    create_app()): questa funzione non lo ricalcola. E' la meta' che mancava
    perche' `static/chat/main.js` (e ora anche il boot della configurazione)
    potessero confrontare "da quale build sono nato" con "quale build gira
    davvero" (GET api/health) invece di limitarsi a mostrarli affiancati senza
    che nessuno li leggesse."""
    def _repl(m: "re.Match[str]") -> str:
        attr, path = m.group(1), m.group(2)
        return f'{attr}="{path}?v={_asset_fingerprint(path, version)}"'

    html = _ASSET_REF_RE.sub(_repl, html)
    if build_stamp:
        html = html.replace(
            "</head>",
            f'  <meta name="hiris-build" content="{build_stamp}">\n</head>',
            1,
        )
    return html


async def _serve_index(request: web.Request) -> web.Response:
    html = request.app.get("html_index") or ""
    if not html:
        return web.Response(text="UI not yet available", status=503)
    return web.Response(
        text=_inject_version(html, read_version(), request.app.get("build_stamp", "")),
        content_type="text/html",
        headers=_NO_CACHE,
    )


async def _serve_config(request: web.Request) -> web.Response:
    html = request.app.get("html_config") or ""
    if not html:
        return web.Response(text="UI not yet available", status=503)
    return web.Response(
        text=_inject_version(html, read_version(), request.app.get("build_stamp", "")),
        content_type="text/html",
        headers=_NO_CACHE,
    )


async def _handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "version": read_version(),
                              "build": request.app.get("build_stamp", "")})
