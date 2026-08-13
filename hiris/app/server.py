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
from .impostazioni_chat import ImpostazioniChat
from .version import read_version
from .proxy.ha_client import HAClient
from .azione.registro import RegistroServizi
from .azione.porta import PortaAzione
from .casa.archivio import ArchivioCasa
from .casa.anagrafe import ricostruisci
from .memoria.archivio import ArchivioMemoria
from .casa.comportamento import rileggi, rileggi_plance
from .env_util import env_bool
from .token_interno import prepara_token_interno
from .proxy.entity_cache import EntityCache
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


def _ponte_attivo(interruttore: bool, piano_attivo: bool) -> bool:
    """Il ponte e' acceso se lo accendi, o se il Piano Claude Max lo implica.

    Fino alla 2.3.1 questa funzione si chiamava `_chat_subscription_active` ed
    era un AND fra DUE opzioni dell'add-on (`chat_via_subscription` e
    `bridge_enabled`). L'AND era il fail-safe numero uno del rilascio: senza,
    si poteva instradare la chat in una coda che nessuno spazzava, e i
    messaggi restavano pendenti per sempre.

    Il proprietario ha fuso i due interruttori in uno solo (`ponte.attivo`,
    13 agosto 2026), e il fail-safe NON e' stato rimosso: e' diventato
    STRUTTURALE. Questa unica espressione governa adesso sia la spazzata
    (`_reasoning_sweep`) sia l'instradamento, quindi i due non possono piu'
    essere in disaccordo — mentre prima potevano, ed erano governati da leve
    diverse. L'invariante «non accodare mai in una coda che nessuno spazza»
    oggi non regge su un `and` da non sbagliare, ma sul fatto che c'e' un
    valore solo.

    `piano_attivo` e' `_sub_first_class`, cioe' Piano Claude Max acceso CON il
    suo token: continua a implicare il ponte, cosi' chi sta nella
    configurazione consigliata non deve accendere niente.

    Rimettere qui un AND fra due valori farebbe cadere
    `test_chat_subscription_path.py::test_il_ponte_e_un_interruttore_solo`.
    """
    return interruttore or piano_attivo


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


def _catena_com_era(strategia: str, credenziali: dict, interruttori: dict,
                    ponte: bool) -> list[str]:
    """La catena che HIRIS usava con la regola PRE-2.5: la si esegue una volta
    sola, alla migrazione, per copiarne il risultato nell'archivio.

    Vive QUI e non in `model_activation.py` perche' non e' piu' una regola del
    prodotto: e' un pezzo di storia che serve a non perdere una configurazione.
    Sparisce insieme alla versione B (Task 13), quando nessuna installazione
    puo' piu' arrivare non seminata.

    E' `derive_active_providers` + `reconcile_chain` senza il ramo dell'ordine
    manuale: qui si arriva solo quando `chain_order` e' vuota, quindi il ramo
    manuale non avrebbe niente da filtrare.
    """
    from .llm_router import _STRATEGY_ORDER
    legacy = not any(interruttori.values())
    attivi = {}
    for p in ("subscription", "claude", "openai", "openrouter", "ollama"):
        ha = bool(credenziali.get(p))
        if legacy:
            attivi[p] = (ha and ponte) if p == "subscription" else ha
        else:
            attivi[p] = interruttori.get(p, False) and ha
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
    # Stesso avvio, stesso guasto: se `load` era fallita per Home Assistant
    # irraggiungibile, anche il registro delle aree lo era. Indipendente dal
    # ritorno: cio' che sblocca gli strumenti e' l'inventario.
    try:
        await cache.load_area_registry(ha_client)
    except Exception as exc:
        logger.warning("Ricarica del registro aree non riuscita: %s", exc)
    return True


def should_start_agent_worker() -> bool:
    """Gate worker del ponte in-addon: attivo quando il Piano Claude Max e'
    acceso (`provider_subscription`) oppure il ponte lo e' (`ponte.attivo`,
    che esporta BRIDGE_ENABLED), E un token OAuth e' presente.

    Fino alla 2.3.1 la seconda meta' della condizione leggeva
    CHAT_VIA_SUBSCRIPTION: era una delle tre cose che quell'opzione faceva, e
    l'unica che `bridge_enabled` non faceva. Fuse le due opzioni, questo gate
    e quello della spazzata leggono finalmente lo STESSO valore — prima si
    poteva far partire il worker (via `chat_via_subscription`) lasciando
    spenta la spazzata (`bridge_enabled`), e il worker sondava una coda che
    nessuno riempiva."""
    sub_on = (
        env_bool("PROVIDER_SUBSCRIPTION")
        or env_bool("BRIDGE_ENABLED")
    )
    return sub_on and bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip())


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
    try:
        await entity_cache.load_area_registry(ha_client)
    except Exception as exc:
        logger.warning("Area registry load failed: %s", exc)
    ha_client.add_state_listener(entity_cache.on_state_changed)
    app["entity_cache"] = entity_cache

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
    save_models_config(data_dir, _archivio)
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
    _nome_modello_com_era = os.environ.get("LOCAL_MODEL_NAME", "")
    openai_api_key = os.environ.get("OPENAI_API_KEY", "")
    openrouter_api_key = os.environ.get("OPENROUTER_API_KEY", "")
    llm_strategy = os.environ.get("LLM_STRATEGY", "balanced")

    # ── Le credenziali, e nient'altro ──────────────────────────────────
    # fetta «la catena diventa l'unica verita'»: qui c'erano i cinque
    # interruttori `provider_*` incrociati con le credenziali
    # (`derive_active_providers`), cioe' la SECONDA rappresentazione dello
    # stato di un provider. Adesso l'unica cosa che si misura qui e' se la
    # credenziale c'e'; chi la USA lo dice `chain_order`.
    _credenziali = {
        "subscription": bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()),
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
    app["credenziali_provider"] = _credenziali

    # ── Migrazione della catena (versione A, seconda meta') ──────────────
    # L'ULTIMO istante in cui la vecchia regola esiste: la catena che HIRIS
    # stava usando viene copiata nell'archivio PRIMA che la derivazione dai
    # cinque interruttori sparisca. Senza questa copia, l'installazione del
    # proprietario -- cinque interruttori a false, credenziali presenti --
    # passerebbe da «due provider lavorano» a «zero provider».
    from .migrazione_opzioni import semina_catena
    if not app["models_config"].get("chain_order"):
        _catena_di_oggi = _catena_com_era(
            os.environ.get("LLM_STRATEGY", "balanced"),
            # Le credenziali COM'ERANO, non quelle di adesso: la credenziale di
            # Ollama comprendeva il nome del modello. Passare quelle nuove
            # farebbe entrare in catena, per migrazione, un Ollama che la
            # vecchia regola non ci aveva MAI messo -- cioe' la migrazione
            # inventerebbe invece di copiare.
            {**_credenziali, "ollama": bool(local_model_url and _nome_modello_com_era)},
            {k: env_bool(v) for k, v in {
                "subscription": "PROVIDER_SUBSCRIPTION", "claude": "PROVIDER_CLAUDE",
                "openai": "PROVIDER_OPENAI", "openrouter": "PROVIDER_OPENROUTER",
                "ollama": "PROVIDER_OLLAMA"}.items()},
            env_bool("BRIDGE_ENABLED"),
        )
        _arch, _seminata = semina_catena(dict(app["models_config"]),
                                         _catena_di_oggi, log=logger)
        if _seminata:
            save_models_config(data_dir, _arch)
            app["models_config"] = load_models_config(data_dir)

    # SP-2 T3: l'abbonamento first-class (provider_subscription) implica il
    # bridge attivo -- senza, la chat resterebbe bloccata lasciando i job
    # 'chat' in coda senza nessuno che li spazzi/reclami/pruni. Calcolato qui,
    # PRIMA di ogni gate più sotto che legge BRIDGE_ENABLED dall'env
    # (_reasoning_sweep e il cablaggio di `app["ponte_attivo"]` poco più in
    # basso -- fetta E3 Task 4: il terzo gate, l'enqueue di
    # `_holistic_reason`, e' uscito con lei), così ognuno di quei punti vede
    # l'abbonamento senza duplicare il parsing env. Vedi task-3-report.md per
    # il grep BRIDGE_ENABLED che aveva individuato i tre gate originari.
    # SP-2 T3 review: usa lo stato CREDENZIALE-CONSAPEVOLE, non il toggle
    # grezzo (`_credenziali["subscription"]` = token presente),
    # non il toggle grezzo: così provider_subscription=true SENZA token non apre
    # i gate di enqueue mentre il worker (gated dal token) non parte — evitando
    # richieste chat accodate e mai servite. Simmetrico a should_start_agent_worker.
    # `PROVIDER_SUBSCRIPTION` e' l'ULTIMO dei cinque interruttori ancora
    # letto, e resta finche' il Task 14 non porta il piano DENTRO la catena e
    # il Task 13 non lo toglie dallo schema. Non e' una seconda
    # rappresentazione della catena: il piano non e' un membro di
    # `chain_order`, e la sua presenza in testa discende da qui.
    _sub_first_class = _credenziali["subscription"] and env_bool("PROVIDER_SUBSCRIPTION")

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
    from .chat_store import delete_old_messages as _delete_old_messages

    def _run_retention() -> None:
        from .chat_store import HISTORY_RETENTION_DAYS
        if HISTORY_RETENTION_DAYS > 0:
            n = _delete_old_messages(data_dir, HISTORY_RETENTION_DAYS)
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

    # Slice 4b Task 3: separate daily cap for chat-via-abbonamento, checked by
    # handle_chat's subscription branch (handlers_chat.py) against
    # reasoning_queue.count_chat_today() -- independent of the Sentinel's own
    # cap (SENTINEL_DAILY_CAP, uscita insieme a lei -- fetta E3 Task 7).
    app["chat_daily_cap"] = int(os.environ.get("CHAT_DAILY_CAP", "50"))

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
        # Stesso combinatore dell'instradamento, piu' in basso: e' cosi' che il
        # fail-safe «mai accodare in una coda che nessuno spazza» regge adesso
        # che l'AND fra due opzioni non c'e' piu'.
        if not _ponte_attivo(env_bool("BRIDGE_ENABLED"), _sub_first_class):
            return
        for job in reasoning_queue.sweep_expired(_time.time()):
            if job.get("kind") != "chat":
                logger.warning(
                    "reasoning sweep: job %s di tipo %r orfano (ponte olistico rimosso, fetta E3 Task 4), scartato",
                    job.get("job_id"), job.get("kind"))
        reasoning_queue.prune(_time.time() - 7 * 86400)

    scheduler.add_job(
        _reasoning_sweep, trigger="interval", minutes=2,
        id="hiris_reasoning_sweep", replace_existing=True, misfire_grace_time=120)

    # Il punto di cablaggio: da qui `handle_chat` sa se instradare il turno
    # sul ponte. `handlers_chat._bridge_on` verifica soltanto che
    # `app["reasoning_queue"]` sia agganciata -- e in produzione lo e' sempre,
    # perche' la coda si crea incondizionatamente poche righe piu' su -- quindi
    # da sola non dice che qualcuno reclami o spazzi quei job. E' questo valore
    # a dirlo. Tenere il gate QUI, invece di insegnare BRIDGE_ENABLED a
    # `_bridge_on`, lascia ai test di handlers_chat.py la possibilita' di
    # agganciare o sganciare la coda senza toccare le variabili d'ambiente.
    #
    # SP-2 T3: `provider_subscription` first-class deve forzare il ponte
    # ovunque BRIDGE_ENABLED sia letto, non solo qui. `_sub_first_class`
    # (calcolata una volta, subito dopo `_active`) entra in tutti e due i punti
    # rimasti: l'uscita anticipata di `_reasoning_sweep` e questo cablaggio.
    #
    # Fusione dei due interruttori (2.4.0): qui c'erano DUE derivazioni --
    # `_bridge_enabled` e `_chat_via_subscription_cfg` -- combinate da un AND,
    # ed era quello il fail-safe. Adesso il valore e' uno, calcolato dalla
    # stessa funzione che governa la spazzata: i due gate leggono la medesima
    # espressione e non possono divergere. Il fail-safe non e' sparito, ha
    # cambiato natura -- da regola da non sbagliare a struttura.
    app["ponte_attivo"] = _ponte_attivo(env_bool("BRIDGE_ENABLED"), _sub_first_class)

    # fetta E3 Task 4: l'arrivo serale (watcher/arrival.py, ArrivalWatcher)
    # e' uscito -- riusava lo stesso adapter `_on_situation` della ronda,
    # uscito con lei (vedi il commento piu' in alto). Nessun sostituto:
    # nessun path di actuation restava dietro, solo una proposta che ora
    # nessuno genera piu'.

    # SP-2 T5C: per-provider DEFAULT model chosen by the user (used when an
    # entity's model is "auto"); Ollama escluso — usa sempre il suo modello,
    # via `fixed_model`. Empty string ("") preserves today's behaviour
    # (fall back to AUTO_MODEL_MAP).
    _pm = app["models_config"].get("provider_models", {})
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
            default_model=_pm.get("claude", ""),
        )

    _usage_base, _usage_ext = os.path.splitext(usage_path)
    _usage_ext = _usage_ext or ".json"

    openai_runner = None
    if openai_api_key and _credenziali["openai"]:
        openai_runner = OpenAICompatRunner(
            base_url="https://api.openai.com/v1",
            api_key=openai_api_key,
            usage_path=f"{_usage_base}_openai{_usage_ext}",
            default_model=_pm.get("openai", ""),
        )

    ollama_runner = None
    if _risponde["ollama"]:
        ollama_runner = OpenAICompatRunner(
            base_url=local_model_url.rstrip("/") + "/v1",
            api_key="ollama",
            fixed_model=_modello_ollama,
            usage_path=f"{_usage_base}_ollama{_usage_ext}",
        )
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
            default_model=_pm.get("openrouter", ""),
        )
        logger.info("OpenRouter abilitato (200+ modelli via openrouter.ai)")

    # Store config for /api/models endpoint
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
            strategy=llm_strategy,
            model_chain=_chain,
        )
        app["claude_runner"] = claude_runner  # backward compat (may be None)
        app["llm_router"] = router
    else:
        app["claude_runner"] = None
        app["llm_router"] = None

    # ── Chat-via-abbonamento worker in-addon (Plan 2B Task 4) ──────────────
    # Polls the internal reasoning queue and reasons via `claude -p` under the
    # user's Claude subscription (CLAUDE_CODE_OAUTH_TOKEN) instead of metered
    # API spend. Off unless both the feature flag and the token are present
    # (should_start_agent_worker). Il server MCP interno che la chat usava per
    # i tool di CONTROLLO casa usci' con la Fetta E2 Task 3 e non e' tornato:
    # quando l'azione e' rientrata (fetta «comandare») e' rientrata come UNO
    # strumento nel catalogo unico, non come un secondo server. Questo worker
    # non ragiona piu' in puro testo -- dalla fetta "il ponte riceve gli
    # strumenti" (parita' B) riceve gli strumenti dalla rotta `POST /api/mcp`
    # registrata piu' sotto, e il prompt lo dichiara al modello solo quando la
    # sonda ha confermato che ci sono davvero (vedi agent/runner.py).
    if should_start_agent_worker():
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
        logger.info("Chat-via-abbonamento worker in-addon avviato")
    else:
        logger.info("Chat-via-abbonamento worker NON avviato (flag/token assenti)")


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


def _inject_version(html: str, version: str) -> str:
    """Append a per-file content fingerprint (?v=HASH) to local static asset
    URLs so browsers bust cache whenever a file's content actually changes.

    Replaces the previous single global ?v=VERSION scheme, which only busted
    caches on a release version bump and left stale JS/CSS in place during any
    edit that didn't change config.yaml's version field."""
    def _repl(m: "re.Match[str]") -> str:
        attr, path = m.group(1), m.group(2)
        return f'{attr}="{path}?v={_asset_fingerprint(path, version)}"'

    return _ASSET_REF_RE.sub(_repl, html)


async def _serve_index(request: web.Request) -> web.Response:
    html = request.app.get("html_index") or ""
    if not html:
        return web.Response(text="UI not yet available", status=503)
    return web.Response(
        text=_inject_version(html, read_version()),
        content_type="text/html",
        headers=_NO_CACHE,
    )


async def _serve_config(request: web.Request) -> web.Response:
    html = request.app.get("html_config") or ""
    if not html:
        return web.Response(text="UI not yet available", status=503)
    return web.Response(
        text=_inject_version(html, read_version()),
        content_type="text/html",
        headers=_NO_CACHE,
    )


async def _handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "version": read_version(),
                              "build": request.app.get("build_stamp", "")})
