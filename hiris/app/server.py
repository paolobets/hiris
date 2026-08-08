# hiris/app/server.py
import asyncio
import contextlib
import hashlib
import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
import aiohttp
from aiohttp import web
from .api.handlers_chat import handle_chat, handle_chat_reply_poll
from .api.handlers_chatbots import (
    handle_list_chatbots, handle_create_chatbot, handle_get_chatbot,
    handle_update_chatbot, handle_delete_chatbot,
    handle_get_chatbot_usage, handle_reset_chatbot_usage,
)
from .api.handlers_entities import handle_list_entities
from .api.handlers_status import handle_status
from .api.handlers_config import handle_config
from .api.handlers_usage import handle_usage, handle_reset_usage
from .api.handlers_chat_history import handle_get_chat_history, handle_clear_chat_history
from .api.handlers_models import (
    handle_list_models, handle_get_models_config, handle_save_models_config,
)
from .api.handlers_knowledge import (
    handle_list_pending, handle_approve, handle_reject, handle_manual_add,
)
from .chatbot_engine import ChatbotEngine
from .version import read_version
from .proxy.ha_client import HAClient
from .casa.archivio import ArchivioCasa
from .casa.anagrafe import ricostruisci
from .memoria.archivio import ArchivioMemoria
from .casa.comportamento import rileggi, rileggi_plance
from .env_util import env_bool
from .proxy.entity_cache import EntityCache
from .backends.embeddings import build_embedding_provider
from .brain.knowledge_store import KnowledgeStore
from .brain.memory_migration import migrate_agent_memories
from .brain.privacy import VaultStore, Pseudonymizer
from .api.middleware_internal_auth import internal_auth_middleware
from .api.middleware_csrf import csrf_middleware
from .llm_router import _VALID_BACKEND_NAMES as _VALID_POLICY_BACKENDS

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


def _chat_subscription_active(cfg_on: bool, bridge_on: bool) -> bool:
    """Slice 4b final-review Fix 2: the release's #1 fail-safe, extracted to a
    tiny pure function so the invariant is unit-tested against REAL code
    (see test_chat_subscription_path.py) rather than a hand-copied
    truth-table or a substring match on the source. The chat-via-abbonamento
    addon option must NEVER activate unless the reasoning-queue bridge is
    ALSO genuinely enabled (BRIDGE_ENABLED) — otherwise chat jobs get
    enqueued into a queue nothing sweeps/claims/prunes and sit pending
    forever. Both must be True; an ``or`` here would be a silent regression.
    """
    return cfg_on and bridge_on


def _parse_policy_csv(value: str | None) -> list[str] | None:
    """Parse a CSV of backend names (e.g. 'claude, ollama') into an ordered list.

    Unknown backend names are dropped, order preserved. Returns None if the
    input is None/empty or if filtering leaves nothing (so the router falls
    back to its strategy-derived default order).
    """
    if not value:
        return None
    names = [name.strip() for name in value.split(",")]
    filtered = [name for name in names if name in _VALID_POLICY_BACKENDS]
    return filtered or None


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


def _deploy_card_to_www(slug: str = "hiris") -> None:
    """Copy hiris-chat-card.js to <ha-config>/www/{slug}/ for auth-free Lovelace access.

    Requires 'config:rw' in the add-on map (config.yaml).
    """
    ha_config = _find_ha_config_dir()
    if ha_config is None:
        logger.error(
            "HA config directory not found at /config or /homeassistant — "
            "card cannot be deployed. Ensure 'config:rw' is in the add-on map, "
            "then stop and restart the add-on. "
            "Until fixed, /local/%s/hiris-chat-card.js will return 404.",
            slug,
        )
        return

    src = os.path.join(os.path.dirname(__file__), "static", "hiris-chat-card.js")
    dst_dir = os.path.join(ha_config, "www", slug)
    dst = os.path.join(dst_dir, "hiris-chat-card.js")
    try:
        os.makedirs(dst_dir, exist_ok=True)
        shutil.copy2(src, dst)
        logger.info("HIRIS card deployed to %s", dst)
    except Exception as exc:
        logger.error("Failed to deploy HIRIS card to %s: %s", dst, exc, exc_info=True)


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


async def _write_ingress_config(supervisor_token: str, slug: str = "hiris") -> None:
    """Write /homeassistant/www/{slug}/hiris-ingress.json with the real ingress URL.

    The HA Supervisor uses a randomly-generated ingress token (not the add-on slug)
    as the path component in /api/hassio_ingress/{token}/.  The Lovelace card reads
    this file (no auth required — /local/ is served publicly) to discover the correct
    URL before making any API call.
    """
    ha_config = _find_ha_config_dir()
    if ha_config is None:
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://supervisor/addons/self/info",
                headers={"Authorization": f"Bearer {supervisor_token}"},
            ) as resp:
                if resp.status != 200:
                    logger.warning(
                        "Supervisor /addons/self/info returned %s — "
                        "card will fall back to slug-based ingress URL",
                        resp.status,
                    )
                    return
                data = await resp.json()
    except Exception as exc:
        logger.warning("Cannot reach Supervisor API (%s) — skipping ingress config", exc)
        return

    ingress_url = (data.get("data") or {}).get("ingress_url")
    if not ingress_url:
        logger.warning("Supervisor did not return ingress_url — skipping ingress config")
        return

    dst_dir = os.path.join(ha_config, "www", slug)
    dst = os.path.join(dst_dir, "hiris-ingress.json")
    try:
        os.makedirs(dst_dir, exist_ok=True)
        with open(dst, "w", encoding="utf-8") as f:
            json.dump({"ingress_url": ingress_url}, f)
        logger.info("HIRIS ingress config written: %s → %s", ingress_url, dst)
    except Exception as exc:
        logger.error("Failed to write ingress config to %s: %s", dst, exc)


async def _register_lovelace_card(ha_base_url: str, token: str, slug: str = "hiris") -> None:
    """Register /local/{slug}/hiris-chat-card.js?v=VERSION as a Lovelace module resource.

    Uses the HA WebSocket API, which works even when the REST endpoint is unavailable.
    Migrates stale URLs (old ingress URL and older versioned /local/ URLs). Idempotent.
    The ?v= query param forces the browser to fetch the new JS on every version bump.
    """
    version = read_version()
    new_url = f"/local/{slug}/hiris-chat-card.js?v={version}"
    old_url = f"/api/hassio_ingress/{slug}/static/hiris-chat-card.js"
    ws_url = (
        ha_base_url.replace("http://", "ws://").replace("https://", "wss://")
        + "/api/websocket"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                # Authenticate
                handshake = await asyncio.wait_for(ws.receive_json(), timeout=10.0)
                if handshake.get("type") == "auth_required":
                    await ws.send_json({"type": "auth", "access_token": token})
                    auth_resp = await asyncio.wait_for(ws.receive_json(), timeout=10.0)
                    if auth_resp.get("type") != "auth_ok":
                        logger.warning("HA WebSocket auth failed — Lovelace registration skipped")
                        return

                # List existing resources
                await ws.send_json({"id": 1, "type": "lovelace/resources"})
                list_resp = await _ws_await(ws, msg_id=1)

                if not list_resp.get("success"):
                    # YAML mode or HA version without resources support
                    err_msg = list_resp.get("error", {}).get("message", "unsupported")
                    logger.info(
                        "Lovelace resources not manageable via WebSocket (%s) — "
                        "add manually in lovelace config: url: %s  type: module",
                        err_msg, new_url,
                    )
                    return

                resources: list[dict] = list_resp.get("result", [])
                msg_id = 2

                # Remove stale URLs: old ingress URL and any /local/ URL that is not
                # the current versioned URL (handles version upgrades and bare URL left
                # by older add-on versions).
                base_local = f"/local/{slug}/hiris-chat-card.js"
                for resource in resources:
                    url = resource.get("url", "")
                    is_stale = (
                        url == old_url
                        or (url.startswith(base_local) and url != new_url)
                    )
                    if is_stale:
                        await ws.send_json({
                            "id": msg_id,
                            "type": "lovelace/resources/delete",
                            "resource_id": resource["id"],
                        })
                        del_resp = await _ws_await(ws, msg_id)
                        if del_resp.get("success"):
                            logger.info("Removed stale Lovelace resource: %s", url)
                        msg_id += 1

                # Idempotency check against the current versioned URL
                for resource in resources:
                    if resource.get("url") == new_url:
                        logger.debug("HIRIS Lovelace card already registered: %s", new_url)
                        return

                # Register
                await ws.send_json({
                    "id": msg_id,
                    "type": "lovelace/resources/create",
                    "res_type": "module",
                    "url": new_url,
                })
                create_resp = await _ws_await(ws, msg_id)

                if create_resp.get("success"):
                    logger.info(
                        "HIRIS Lovelace card registered ✓ url=%s — reload HA UI to activate",
                        new_url,
                    )
                else:
                    logger.warning(
                        "Lovelace registration failed: %s",
                        create_resp.get("error", {}).get("message", "unknown"),
                    )
    except Exception as exc:
        logger.warning("Lovelace card registration error: %s", exc)


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
    da li' in poi la cache resta `loaded is False` e i quattro strumenti che
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
    # ritorno: cio' che sblocca i quattro strumenti e' l'inventario.
    try:
        await cache.load_area_registry(ha_client)
    except Exception as exc:
        logger.warning("Ricarica del registro aree non riuscita: %s", exc)
    return True


def should_start_agent_worker() -> bool:
    """Gate worker chat-via-abbonamento in-addon (SP-2): attivo quando
    l'abbonamento è attivo (provider_subscription, o il legacy
    chat_via_subscription) E un token OAuth è presente."""
    sub_on = (
        env_bool("PROVIDER_SUBSCRIPTION")
        or env_bool("CHAT_VIA_SUBSCRIPTION")
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

    app["internal_token"] = os.environ.get("INTERNAL_TOKEN", "")
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

    # Deploy card JS and ingress config to /homeassistant/www/, register Lovelace resource
    hiris_slug = os.environ.get("HIRIS_SLUG", "hiris")
    _deploy_card_to_www(hiris_slug)
    await _write_ingress_config(os.environ.get("SUPERVISOR_TOKEN", ""), hiris_slug)
    await _register_lovelace_card(
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

    data_path = os.environ.get("CHATBOTS_DATA_PATH", "/data/chatbots.json")
    data_dir = os.path.dirname(os.path.abspath(data_path))
    app["data_dir"] = data_dir
    # SP-2 Task 4: models-config store (chain_order + brain_model), letta prima
    # della costruzione LLMRouter più sotto così il chain-build (Task 2 Step 5)
    # può leggere chain_order, e prima di _holistic_reason (Brain) che legge
    # brain_model.
    from .api.handlers_models import load_models_config
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

    engine = ChatbotEngine(ha_client=ha_client, data_path=data_path)
    engine.set_entity_cache(entity_cache)
    engine.set_archivi(archivio_casa, archivio_memoria)
    # Task 1 fetta E4: il WebSocket verso HA parte qui, non dentro
    # `engine.start()` -- e' il server ad aprire i sensi della casa, non i
    # chatbot. Deve stare dopo la registrazione di tutti i listener sopra
    # (state/anagrafe/plance, :633-690): aprirlo prima lascerebbe una finestra
    # di eventi senza nessuno ad ascoltarli.
    await ha_client.start_websocket()
    await engine.start()
    app["engine"] = engine

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
    # d'attuazione rimasta in un HIRIS che per decisione non agisce.
    # Torneranno rifatte, col perimetro e la verifica umana, nel progetto
    # agenti. SILENZIO DICHIARATO, stessa disciplina di advisory.db/
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
    local_model_name = os.environ.get("LOCAL_MODEL_NAME", "")
    openai_api_key = os.environ.get("OPENAI_API_KEY", "")
    openrouter_api_key = os.environ.get("OPENROUTER_API_KEY", "")
    llm_strategy = os.environ.get("LLM_STRATEGY", "balanced")
    automatic_policy = _parse_policy_csv(os.environ.get("AUTOMATIC_POLICY", ""))
    chat_policy = _parse_policy_csv(os.environ.get("CHAT_POLICY", ""))

    from .model_activation import derive_active_providers
    _prov_cfg = {
        "provider_subscription": env_bool("PROVIDER_SUBSCRIPTION"),
        "provider_claude": env_bool("PROVIDER_CLAUDE"),
        "provider_openai": env_bool("PROVIDER_OPENAI"),
        "provider_openrouter": env_bool("PROVIDER_OPENROUTER"),
        "provider_ollama": env_bool("PROVIDER_OLLAMA"),
        "chat_via_subscription": env_bool("CHAT_VIA_SUBSCRIPTION"),
    }
    _prov_creds = {
        "subscription": bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()),
        "claude": bool(api_key),
        "openai": bool(openai_api_key),
        "openrouter": bool(openrouter_api_key),
        "ollama": bool(local_model_url and local_model_name),
    }
    _active = derive_active_providers(_prov_cfg, _prov_creds)
    app["active_providers"] = _active

    # SP-2 T3: l'abbonamento first-class (provider_subscription) implica il
    # bridge attivo -- il fail-safe #1 (_chat_subscription_active = cfg AND
    # bridge, invariato) altrimenti bloccherebbe la chat lasciando i job
    # 'chat' in coda senza nessuno che li spazzi/reclami/pruni. Calcolato qui,
    # PRIMA di ogni gate più sotto che legge BRIDGE_ENABLED dall'env
    # (_reasoning_sweep, il wiring di chat_via_subscription poco più in
    # basso -- fetta E3 Task 4: il terzo gate, l'enqueue di
    # `_holistic_reason`, e' uscito con lei), così ognuno di quei punti vede
    # l'abbonamento senza duplicare il parsing env. Vedi task-3-report.md per
    # il grep BRIDGE_ENABLED che aveva individuato i tre gate originari.
    # SP-2 T3 review: usa lo stato di attivazione CREDENZIALE-CONSAPEVOLE
    # (_active["subscription"] = toggle AND token presente, o derivato legacy),
    # non il toggle grezzo: così provider_subscription=true SENZA token non apre
    # i gate di enqueue mentre il worker (gated dal token) non parte — evitando
    # richieste chat accodate e mai servite. Simmetrico a should_start_agent_worker.
    _sub_first_class = _active["subscription"]

    # Memory / RAG config
    mem_provider = os.environ.get("MEMORY_EMBEDDING_PROVIDER", "")
    mem_model = os.environ.get("MEMORY_EMBEDDING_MODEL", "")
    memory_rag_k = int(os.environ.get("MEMORY_RAG_K", "5"))

    embedder = build_embedding_provider(
        provider=mem_provider,
        model=mem_model,
        openai_api_key=openai_api_key,
        local_model_url=local_model_url,
    )
    app["embedding_provider"] = embedder
    app["memory_rag_k"] = memory_rag_k

    knowledge_store = KnowledgeStore(os.path.join(data_dir, "knowledge.db"))
    app["knowledge_store"] = knowledge_store

    # A migration failure must never brick add-on boot (Slice 3 Task 4, M1):
    # log loudly and continue with an empty/partial KnowledgeStore rather
    # than crashing startup over legacy hiris_memory.db data.
    try:
        _migrated_memories = migrate_agent_memories(data_dir, knowledge_store)
        if _migrated_memories:
            logger.info(
                "Startup: migrated %d legacy agent memories into KnowledgeStore",
                _migrated_memories,
            )
    except Exception as exc:
        logger.error("Startup: migrate_agent_memories failed, continuing boot: %s", exc, exc_info=True)

    from .history.store import HistoryStore
    from .history.capture import HistoryCapture
    from .api.handlers_history_policy import load_policy as _load_history_policy

    history_store = HistoryStore(os.path.join(data_dir, "history.db"))
    app["history_store"] = history_store
    history_capture = HistoryCapture(history_store, _load_history_policy(data_dir))
    app["history_capture"] = history_capture
    ha_client.add_state_listener(history_capture.on_state_changed)

    vault = VaultStore(os.path.join(data_dir, "vault.db"))
    pseudonymizer = Pseudonymizer(vault)
    app["vault"] = vault
    app["pseudonymizer"] = pseudonymizer

    # Ricarica dell'inventario entita' dopo un avvio senza Home Assistant.
    # `entity_cache.load` piu' sopra logga e prosegue se fallisce: senza questo
    # lavoro la cache resterebbe "mai caricata" fino al riavvio dell'addon, e i
    # quattro strumenti che la leggono continuerebbero a rispondere "non ancora
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

    engine._scheduler.add_job(
        _ricarica_inventario,
        trigger="interval", minutes=2,
        id="hiris_entity_cache_reload", replace_existing=True,
        misfire_grace_time=120,
    )

    # Task 4 SDD casa: la sentinella dell'mtime, registrata come lavoro
    # periodico come gli altri qui sopra. Cinque minuti: il comportamento
    # cambia con una cadenza di giorni, non serve un giro piu' stretto, e il
    # costo di un giro a vuoto sono solo due `stat()`.
    engine._scheduler.add_job(
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

    engine._scheduler.add_job(
        _run_retention,
        trigger="cron",
        hour=3,
        minute=0,
        id="hiris_retention",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    def _run_history_compact() -> None:
        from datetime import datetime, timezone
        pol = _load_history_policy(data_dir)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            history_store.compact(today=today, retention_days=pol["retention_days"])
        except Exception as exc:
            logger.error("History compaction failed: %s", exc, exc_info=True)

    engine._scheduler.add_job(
        _run_history_compact,
        trigger="cron", hour=3, minute=30,
        id="hiris_history_compact", replace_existing=True, misfire_grace_time=3600,
    )

    async def _run_history_digest_job() -> None:
        from datetime import datetime, timezone
        from .brain.history_digest import run_history_digest
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            await run_history_digest(history_store, knowledge_store, embedder, today=today)
        except Exception as exc:
            logger.error("History digest failed: %s", exc, exc_info=True)

    engine._scheduler.add_job(
        _run_history_digest_job,
        trigger="cron", hour=4, minute=0,
        id="hiris_history_digest", replace_existing=True, misfire_grace_time=3600,
    )

    # ── Mayan EDMS polling ingestion job (second-brain phase-3, Task 6) ────────
    # Read config from env vars exported by run.sh (bashio::config 'mayan.*').
    mayan_url = os.environ.get("MAYAN_URL", "").strip()
    mayan_token = os.environ.get("MAYAN_TOKEN", "").strip()
    mayan_tag_id = int(os.environ.get("MAYAN_TAG_ID", "0") or "0")
    mayan_sensitivity = os.environ.get("MAYAN_SENSITIVITY", "sensitive").strip() or "sensitive"
    mayan_poll_minutes = max(5, int(os.environ.get("MAYAN_POLL_MINUTES", "60") or "60"))

    if mayan_url and mayan_token and mayan_tag_id > 0:
        from .brain.mayan_client import MayanClient
        from .brain.mayan_ingest import ingest_tag as _mayan_ingest_tag

        mayan_client = MayanClient(mayan_url, mayan_token)
        app["mayan_client"] = mayan_client
        logger.info(
            "Mayan EDMS enabled — url=%s tag_id=%d poll_minutes=%d sensitivity=%s",
            mayan_url, mayan_tag_id, mayan_poll_minutes, mayan_sensitivity,
        )

        async def _run_mayan_ingest() -> None:
            client = app.get("mayan_client")
            store = app.get("knowledge_store")
            embedder = app.get("embedding_provider")
            if client is None or store is None or embedder is None:
                return
            try:
                n = await _mayan_ingest_tag(
                    client, store, embedder,
                    tag_id=mayan_tag_id,
                    sensitivity=mayan_sensitivity,
                )
                if n:
                    logger.info("Mayan ingest: %d new document(s) ingested", n)
            except Exception as exc:
                logger.error("Mayan ingest job failed: %s", exc, exc_info=True)

        engine._scheduler.add_job(
            _run_mayan_ingest,
            trigger="interval",
            minutes=mayan_poll_minutes,
            id="hiris_mayan_ingest",
            replace_existing=True,
            misfire_grace_time=300,
        )
        # Also run one initial ingestion shortly after startup (non-blocking)
        _spawn(_run_mayan_ingest(), name="mayan_ingest_initial")
    else:
        logger.debug(
            "Mayan EDMS disabled (url=%r, token set=%s, tag_id=%d)",
            mayan_url, bool(mayan_token), mayan_tag_id,
        )

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
    # the house. chat_store has no separate "conversation_id"; a conversation
    # IS a chatbot's active session, keyed by chatbot_id, so that's what the
    # job context carries and what this receives.
    from .chat_store import append_messages as _append_chat_messages
    from .chat_store import _is_toxic_assistant as _is_toxic_chat_reply

    async def _submit_chat_reply(chatbot_id: str, reply_text: str) -> None:
        if not chatbot_id or not reply_text:
            return
        # Final-review Fix 3 (Slice 4b): mirror the sync path's two
        # persistence guards (handlers_chat.py, ~line 423) so a reply that
        # arrived via the async runner gets the same treatment as one from
        # the local runner. De-tokenize BEFORE the toxicity check, same order
        # as the sync path, so both the stored history and the toxic-pattern
        # match see real values rather than vault tokens.
        _pseudonymizer = app.get("pseudonymizer")
        if _pseudonymizer is not None:
            # SECURITY (review B/#7): this async-bridge reply comes from an
            # external runner process on a job claimed/submitted over the
            # network, entirely outside this process's per-request
            # ContextVar-scoped pseudonym map (_enqueue_chat_job never calls
            # pseudonymize for this path either) — there is no legitimate
            # per-job token mapping available here. Pass an explicit empty
            # mapping so detokenize's new contract (expand ONLY tokens in the
            # supplied mapping) safely leaves any [TYPE_N]-shaped text
            # verbatim, instead of resolving it against the shared,
            # unscoped vault as it used to.
            reply_text = _pseudonymizer.detokenize(reply_text, {})
        if _is_toxic_chat_reply(reply_text):
            # Drop silently, same as the sync path: the next turn must not
            # inherit a poisoned/leaked history. There's no HTTP response
            # here to carry a visible error (the caller already got a 202
            # long ago) -- the poll route's chat_reply_skipped handling is
            # the user-facing side of this.
            return
        _append_chat_messages(chatbot_id, [{"role": "assistant", "content": reply_text}], data_dir)
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
    # Designer (static/config/templates.js, fuori scope, e' la E5 -- la
    # voce resta li' come checkbox inerte, dichiarata nel report del Task 8).
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
        if not env_bool("BRIDGE_ENABLED") and not _sub_first_class:
            return
        for job in reasoning_queue.sweep_expired(_time.time()):
            if job.get("kind") != "chat":
                logger.warning(
                    "reasoning sweep: job %s di tipo %r orfano (ponte olistico rimosso, fetta E3 Task 4), scartato",
                    job.get("job_id"), job.get("kind"))
        reasoning_queue.prune(_time.time() - 7 * 86400)

    engine._scheduler.add_job(
        _reasoning_sweep, trigger="interval", minutes=2,
        id="hiris_reasoning_sweep", replace_existing=True, misfire_grace_time=120)

    # Slice 4b Task 5: the chat_via_subscription addon option only takes
    # effect when the bridge is ALSO truly usable. handlers_chat._bridge_on
    # just checks that app["reasoning_queue"] is wired -- and it always is in
    # prod (created unconditionally a few lines above) -- so on its own it's
    # not a signal that anything actually claims/sweeps/prunes those jobs.
    # That sweeping/pruning (_reasoning_sweep just above, for the chat kind
    # it still processes) is gated on BRIDGE_ENABLED, read the same way here
    # as everywhere else in this module. Gating the flag itself at this
    # single wiring point -- rather than teaching _bridge_on about
    # BRIDGE_ENABLED -- keeps handlers_chat.py's tests able to wire/unwire
    # the queue directly without touching env vars, while still making sure
    # chat_via_subscription=true + BRIDGE_ENABLED=0 enqueues nothing that
    # would sit pending forever and grow the DB.
    #
    # SP-2 T3: provider_subscription (first-class) must ALSO force the bridge
    # on, everywhere BRIDGE_ENABLED is read -- not just here. _sub_first_class
    # (computed once, right after _active above) is OR'd into all remaining
    # BRIDGE_ENABLED reads in this module: _reasoning_sweep's early-return
    # (fetta E3 Task 4: this used to be one of three, the holistic-enqueue
    # read went with `_holistic_reason`) and this cfg/bridge derivation.
    # Missing it would leave a hole where the fail-safe below
    # (_chat_subscription_active, still a strict AND) blocks chat while the
    # sweep that's supposed to drain the queue never runs.
    _bridge_enabled = (
        env_bool("BRIDGE_ENABLED")
        or _sub_first_class  # SP-2: abbonamento attivo implica il bridge (sweep coda)
    )
    _chat_via_subscription_cfg = (
        env_bool("CHAT_VIA_SUBSCRIPTION")
        or _sub_first_class
    )
    app["chat_via_subscription"] = _chat_subscription_active(_chat_via_subscription_cfg, _bridge_enabled)

    # fetta E3 Task 4: l'arrivo serale (watcher/arrival.py, ArrivalWatcher)
    # e' uscito -- riusava lo stesso adapter `_on_situation` della ronda,
    # uscito con lei (vedi il commento piu' in alto). Nessun sostituto:
    # nessun path di actuation restava dietro, solo una proposta che ora
    # nessuno genera piu'.

    # SP-2 T5C: per-provider DEFAULT model chosen by the user (used when an
    # entity's model is "auto"); Ollama excluded — it uses local_model.model
    # via fixed_model instead. Empty string ("") preserves today's behaviour
    # (fall back to AUTO_MODEL_MAP).
    _pm = app["models_config"].get("provider_models", {})

    claude_runner = None
    if api_key and _active["claude"]:
        claude_runner = ClaudeRunner(
            api_key=api_key,
            usage_path=usage_path,
            default_model=_pm.get("claude", ""),
        )

    _usage_base, _usage_ext = os.path.splitext(usage_path)
    _usage_ext = _usage_ext or ".json"

    openai_runner = None
    if openai_api_key and _active["openai"]:
        openai_runner = OpenAICompatRunner(
            base_url="https://api.openai.com/v1",
            api_key=openai_api_key,
            usage_path=f"{_usage_base}_openai{_usage_ext}",
            default_model=_pm.get("openai", ""),
        )

    ollama_runner = None
    if local_model_url and local_model_name and _active["ollama"]:
        ollama_runner = OpenAICompatRunner(
            base_url=local_model_url.rstrip("/") + "/v1",
            api_key="ollama",
            fixed_model=local_model_name,
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
                        if local_model_name in _names:
                            logger.info("Ollama OK — modello '%s' pronto", local_model_name)
                        else:
                            logger.warning(
                                "Ollama raggiungibile ma il modello '%s' non è nella lista %s — "
                                "pull potrebbe essere necessario",
                                local_model_name, _names,
                            )
                    else:
                        logger.warning("Ollama /api/tags ha risposto con status %s", _r.status)
        except Exception as _exc:
            logger.warning(
                "Ollama non raggiungibile a %s (%s) — le richieste al modello locale falliranno",
                local_model_url, _exc,
            )

    openrouter_runner = None
    if openrouter_api_key and _active["openrouter"]:
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
    app["local_model_name"] = local_model_name

    if any([claude_runner, openai_runner, openrouter_runner, ollama_runner]):
        # SP-2: una catena unica = ordine di strategia (o override manuale futuro,
        # Task 4) filtrato ai provider ATTIVI (Task 1). Sub non è un backend del
        # router (gira via runner in-addon), quindi non entra qui.
        from .llm_router import _STRATEGY_ORDER
        from .model_activation import reconcile_chain
        # override manuale (Task 4) — se presente in models_config, filtra ai
        # provider attivi, poi (review finale SP-2) i provider attivi mancanti
        # dall'override vengono APPENDED in ordine di strategia -- una
        # chain_order parziale salvata quando meno provider erano attivi non
        # deve MAI far sparire dalla catena un provider che diventa attivo
        # dopo (fail-open su automatic_allows_sensitive() + provider escluso
        # dal failover finché l'utente non riapre #/models e risalva).
        # Se il risultato è comunque vuoto, fallback esplicito ai provider
        # attivi in ordine di strategia (mai degradare silenziosamente).
        _strategy_order = _STRATEGY_ORDER.get(llm_strategy, _STRATEGY_ORDER["balanced"])
        _manual = app.get("models_config", {}).get("chain_order")
        _chain = reconcile_chain(_strategy_order, _manual, app["active_providers"])

        router = LLMRouter(
            claude=claude_runner,
            openai=openai_runner,
            openrouter=openrouter_runner,
            ollama=ollama_runner,
            strategy=llm_strategy,
            automatic_policy=automatic_policy,  # deprecato, tenuto per retro-compat
            chat_policy=chat_policy,            # deprecato
            model_chain=_chain,
        )
        app["claude_runner"] = claude_runner  # backward compat (may be None)
        app["llm_router"] = router
        engine.set_claude_runner(router)
    else:
        app["claude_runner"] = None
        app["llm_router"] = None

    # ── Chat-via-abbonamento worker in-addon (Plan 2B Task 4) ──────────────
    # Polls the internal reasoning queue and reasons via `claude -p` under the
    # user's Claude subscription (CLAUDE_CODE_OAUTH_TOKEN) instead of metered
    # API spend. Off unless both the feature flag and the token are present
    # (should_start_agent_worker). Il server MCP interno che la chat usava
    # per i tool di controllo casa e' uscito (Fetta E2 Task 3): questo worker
    # resta, ma senza quel percorso ragiona in puro testo (vedi
    # agent/runner.py).
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
    if app.get("mayan_client") is not None:
        await app["mayan_client"].aclose()
    if "knowledge_store" in app:
        app["knowledge_store"].close()
    if "vault" in app:
        app["vault"].close()
    if "history_store" in app:
        app["history_store"].close()
    if "reasoning_queue" in app:
        app["reasoning_queue"].close()
    if "archivio_casa" in app:
        app["archivio_casa"].chiudi()
    if "archivio_memoria" in app:
        app["archivio_memoria"].chiudi()
    await app["engine"].stop()
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
    app.router.add_get("/api/status", handle_status)
    app.router.add_get("/api/config", handle_config)
    app.router.add_get("/api/usage", handle_usage)
    app.router.add_post("/api/usage/reset", handle_reset_usage)
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_get("/api/chat/reply/{job_id}", handle_chat_reply_poll)
    app.router.add_get("/api/chatbots", handle_list_chatbots)
    app.router.add_post("/api/chatbots", handle_create_chatbot)
    app.router.add_get("/api/chatbots/{agent_id}", handle_get_chatbot)
    app.router.add_put("/api/chatbots/{agent_id}", handle_update_chatbot)
    app.router.add_delete("/api/chatbots/{agent_id}", handle_delete_chatbot)
    app.router.add_get("/api/entities", handle_list_entities)
    app.router.add_get("/api/chatbots/{agent_id}/usage", handle_get_chatbot_usage)
    app.router.add_post("/api/chatbots/{agent_id}/usage/reset", handle_reset_chatbot_usage)
    app.router.add_get("/api/chatbots/{agent_id}/chat-history", handle_get_chat_history)
    app.router.add_delete("/api/chatbots/{agent_id}/chat-history", handle_clear_chat_history)
    # fetta E3 Task 9: le tre rotte /api/tasks* sono uscite insieme al Task
    # Engine -- lasciano rotta la pagina #/tasks (tasks-route.js) e il
    # pannello Task della chat (chat/tasks.js), entrambi vivi in static/
    # fino alla E5 (vedi il report del task).
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
    app.router.add_get("/api/knowledge/pending", handle_list_pending)
    app.router.add_post("/api/knowledge/{id}/approve", handle_approve)
    app.router.add_post("/api/knowledge/{id}/reject", handle_reject)
    app.router.add_post("/api/knowledge", handle_manual_add)

    from .api.handlers_history_policy import (
        handle_get_history_policy, handle_save_history_policy,
    )
    app.router.add_get("/api/history/policy", handle_get_history_policy)
    app.router.add_post("/api/history/policy", handle_save_history_policy)

    # fetta E3 Task 3: le quattro rotte CRUD /api/agentbots sono uscite
    # insieme ad api/handlers_agentbots.py. La pagina #/agentbots
    # (agentbot-route.js), il suo editor (agentbot-editor.js) e il wizard
    # (create-wizard.js: POST /api/agentbots) restano nello static/ (fetta
    # E5) e da qui in poi ricevono 404 -- non riparati, per costruzione.
    #
    # fetta E3 Task 7: /api/gateway/policy, /api/gateway/autonomy-summary
    # (api/handlers_gateway_policy.py) e /api/sentinel/policy,
    # /api/sentinel/timeline (api/handlers_sentinel.py) sono uscite insieme
    # alla Sentinella e al semaforo che le serviva -- entrambi i moduli
    # handler sono cancellati per intero. La pagina #/gateway
    # (gateway-route.js) e il riquadro "Autonomia" dell'editor Chatbot
    # (chatbot-editor.js -> POST /api/gateway/autonomy-summary) restano nello
    # static/ (fetta E5) e da qui in poi ricevono 404 -- non riparati, per
    # costruzione (vedi il report del task).

    from .api.handlers_reasoning import handle_reasoning_claim, handle_reasoning_submit
    app.router.add_post("/api/reasoning/claim", handle_reasoning_claim)
    app.router.add_post("/api/reasoning/submit", handle_reasoning_submit)

    # fetta E3 Task 5: /api/brain/feed e /api/brain/reasoning sono uscite col
    # Brain auto-proponente (handle_brain_feed componeva reasoning_log/
    # brain.feed, handle_brain_reasoning leggeva il solo reasoning_log --
    # entrambi usciti).
    # fetta E3 Task 6: /api/brain/advisories* e' uscita con loro --
    # `handlers_brain.py` (che a questo punto conteneva solo le advisories)
    # e' cancellato per intero. La Dashboard (static/config/dashboard.js:206,
    # 257-258 e static/config/main.js:127) chiamava queste tre rotte per il
    # pannello segnalazioni e il badge nella nav: restano rotte morte,
    # elenco per la E5 (static/ non e' nel perimetro di questo task).

    # Task 6 SDD casa: sola lettura, per guardare dal vivo cio' che l'archivio
    # ha ricostruito -- la suite verde non prova che la lettura funzioni.
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
    # Stessa forma di /api/casa e /api/memoria: nessun frontend in questo
    # task, si guarda dal browser.
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
