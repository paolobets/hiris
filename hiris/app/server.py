# hiris/app/server.py
import asyncio
import contextlib
import hashlib
import json
import logging
import os
import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
import aiohttp
from aiohttp import web
from .api.handlers_chat import handle_chat, handle_chat_reply_poll
from .api.handlers_chatbots import (
    handle_list_chatbots, handle_create_chatbot, handle_get_chatbot,
    handle_update_chatbot, handle_delete_chatbot, handle_run_chatbot,
    handle_get_chatbot_usage, handle_reset_chatbot_usage,
)
from .api.handlers_entities import handle_list_entities
from .api.handlers_suggestions import handle_list_suggestions, handle_undo_suggestion
from .api.handlers_status import handle_status
from .api.handlers_config import handle_config
from .api.handlers_usage import handle_usage, handle_reset_usage
from .api.handlers_chat_history import handle_get_chat_history, handle_clear_chat_history
from .api.handlers_tasks import handle_list_tasks, handle_get_task, handle_cancel_task
from .api.handlers_models import (
    handle_list_models, handle_get_models_config, handle_save_models_config,
)
from .api.handlers_health import handle_get_ha_health, handle_refresh_ha_health
from .api.handlers_proposals import (
    handle_list_proposals, handle_get_proposal,
    handle_apply_proposal, handle_reject_proposal,
)
from .api.handlers_dashboards import handle_restore_dashboard, handle_list_dashboard_backups
from .api.handlers_knowledge import (
    handle_list_pending, handle_approve, handle_reject, handle_manual_add,
)
from .proxy.health_monitor import HealthMonitor
from .proxy.supervisor_client import SupervisorClient
from .proxy.proposal_store import ProposalStore
from .chatbot_engine import ChatbotEngine
from .task_engine import TaskEngine
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
from .brain.reasoner_memory import relevant_memory, MemoryRecall
from .brain.briefing import build_briefing_bundle, compose_briefing
from .brain.reminders import ReminderSeen, due_nudges
from .watcher.policy import load_policy
from .api.middleware_internal_auth import internal_auth_middleware
from .api.middleware_csrf import csrf_middleware
from .mqtt_publisher import MQTTPublisher
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


async def _fetch_addon_slug(supervisor_token: str) -> str | None:
    """Lo slug INSTALLATO dell'add-on (es. '<repohash>_hiris'), dal Supervisor.

    Serve a costruire il deep-link ingress STABILE '/hassio/ingress/<slug>' per
    il clickAction delle notifiche (aprire HIRIS al tap invece della Dashboard
    home). Diverso dallo slug di config ('hiris') e dal token ingress che ruota.
    Ritorna None se il Supervisor e' irraggiungibile -> il deep-link si omette."""
    if not supervisor_token:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://supervisor/addons/self/info",
                headers={"Authorization": f"Bearer {supervisor_token}"},
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
    except Exception as exc:
        logger.warning("Cannot fetch add-on slug from Supervisor (%s)", exc)
        return None
    return (data.get("data") or {}).get("slug")


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


def _reasoning_runner(app: web.Application):
    """L'oggetto a cui il percorso di ragionamento parla davvero: il router
    LLM, o -- se non c'e' -- il ClaudeRunner dell'engine.

    Risoluzione condivisa da ogni chiamante di `_llm_reason`, cosi' che tutti
    guardino sempre lo stesso oggetto invece di rischiare di risolvere due
    runner diversi in momenti diversi.

    Fino al Task 3 di questa fetta serviva anche al bound per esecuzione
    (`agent_run_bound` & co., Agenti v1.1 Fase 2 Task 5): quel bound esisteva
    solo per misurare il costo di un Agentbot in modalita' obiettivo, e
    l'unico chiamante che poteva innescarlo (`watcher/agentbot_runner.py`) e'
    uscito con l'intero strato Agentbot -- percorso morto per costruzione, non
    solo inutilizzato oggi. Rimosso insieme a lui."""
    runner = app.get("llm_router")
    if runner is None:
        eng = app.get("engine")
        runner = getattr(eng, "_claude_runner", None) if eng is not None else None
    return runner


async def _reason_memory_context(
    app: web.Application, embedder, wake, friendly_name: str,
) -> MemoryRecall:
    """Slice 6b Task 4: bounded, egress-gated memory snippets for the
    sentinel/situation reasoner's context.

    Extracted to module level (instead of inlined in the `_gather_context`
    closure inside `_on_startup`) specifically so it is unit-testable with a
    plain dict standing in for `app` -- `_gather_context` itself is a
    closure over `_on_startup`'s locals and isn't independently reachable
    from tests. `app` only needs `.get("knowledge_store")` and
    `.get("llm_router")`, both of which a dict provides.

    The egress gate: memory that isn't `sensitivity='normal'` is only
    included when `LLMRouter.automatic_allows_sensitive()` reports the
    whole automatic backend chain is local (Task 1) -- this feeds the
    proactive reasoner's `_llm_reason` -> `run_with_actions` (automatic
    mode) path exclusively; it never routes through `simple_chat` or a
    forced non-auto model.

    Failure-safe: relevant_memory() itself never raises (see
    reasoner_memory.py), but router.automatic_allows_sensitive() or a
    malformed `wake` could -- so this is wrapped too, degrading to
    `MemoryRecall(snippets=[], by_meaning=False)` rather than ever bubbling
    an exception into `_gather_context`. Returning a `MemoryRecall` on
    every path (not sometimes a bare list) keeps `_gather_context` able to
    read `.snippets`/`.by_meaning` unconditionally.
    """
    try:
        knowledge_store = app.get("knowledge_store") if app is not None else None
        router = app.get("llm_router") if app is not None else None
        allow_sensitive = router.automatic_allows_sensitive() if router is not None else False
        query_text = f"{friendly_name} {wake.signal_kind}"[:200]
        return await relevant_memory(
            knowledge_store, embedder,
            query_text=query_text, allow_sensitive=allow_sensitive,
        )
    except Exception:
        logger.warning("_reason_memory_context: memory retrieval failed", exc_info=True)
        return MemoryRecall(snippets=[], by_meaning=False)


async def _osserva_la_casa(app) -> int:
    """Registra lo stato notevole della casa e ne calcola il cambiamento.

    E' l'UNICO scrittore della linea di base del ritratto: i consumatori
    leggono soltanto. Se aggiornasse la linea di base ogni consumatore,
    ciascuno vedrebbe solo cio' che e' cambiato dopo il precedente, e il
    delta smetterebbe di voler dire "dall'ultima volta che ho guardato".

    Non solleva mai: un'osservazione saltata e' un delta piu' vecchio, non un
    giro di scheduler perso.
    """
    try:
        store = app.get("portrait_store") if app is not None else None
        cache = app.get("entity_cache") if app is not None else None
        if store is None or cache is None or not hasattr(cache, "all_states"):
            return 0
        from .proxy.entity_cache import inventario_leggibile
        if not inventario_leggibile(cache):
            # Riavvio host: il Supervisor puo' avviare HIRIS prima che il
            # core HA sia pronto. Il primo `entity_cache.load()` fallisce (e
            # viene inghiottito), la cache resta parziale/vuota e
            # `cache.loaded` resta False. Un'osservazione su quello stato
            # cancellerebbe o riempirebbe di falsi "riapparsi" la linea di
            # base -- saltare il giro e' "un delta piu' vecchio", la
            # degradazione che il docstring sopra promette, non un guasto.
            return 0
        from .brain.portrait import notable_state
        changes = store.observe(notable_state(cache.all_states()))
        return len(changes)
    except Exception:
        logger.warning("_osserva_la_casa: osservazione fallita", exc_info=True)
        return 0


def _portrait_context(app) -> str:
    """Il ritratto reso, pronto per il prompt. "" se non disponibile.

    Sincrona di proposito: legge solo la cache in memoria e lo store locale,
    nessun I/O verso Home Assistant.
    """
    try:
        store = app.get("portrait_store") if app is not None else None
        cache = app.get("entity_cache") if app is not None else None
        if store is None or cache is None or not hasattr(cache, "all_states"):
            return ""
        from .brain.portrait import build_portrait, render_portrait
        area_map = cache.get_area_map() if hasattr(cache, "get_area_map") else None
        return render_portrait(build_portrait(
            area_map=area_map, states=cache.all_states(),
            baseline=store.baseline(), changes=store.last_changes(),
        ))
    except Exception:
        logger.warning("_portrait_context: ritratto non disponibile", exc_info=True)
        return ""


async def run_daily_briefing(app, *, today, llm_reason, notify) -> str | None:
    """Slice 7 (Maggiordomo) Task 4: the consolidated daily butler briefing
    job, replacing the old per-obligation spam (`hiris_due_reminders` /
    `_notify_due_obligations`, one notification per due obligation, no
    dedup) with ONE grounded resoconto per day.

    Module-level (not inlined in `_on_startup`) so it's unit-testable with a
    plain dict standing in for `app` -- same convention as
    `_reason_memory_context` above; `app` only needs `.get("knowledge_store")`,
    `.get("entity_cache")`, `.get("llm_router")` and `.get("advisory_store")`.

    Le batterie scariche arrivano da `advisory_store`, dove i controlli di
    salute del Brain hanno gia' scritto le loro segnalazioni: il briefing non
    le ricalcola piu' e la policy dei rilevatori non entra piu' qui.

    Egress gate: `allow_sensitive` is True only when
    `LLMRouter.automatic_allows_sensitive()` reports the automatic backend
    chain is entirely local (Slice 6b Task 1) -- the SAME gate
    `_reason_memory_context` applies, fed into `build_briefing_bundle`
    (Task 1) so sensitive deadlines are excluded (but still counted) from
    a cloud-routed briefing. `compose_briefing` (Task 2) is itself
    failure-safe (grounded LLM composition with a deterministic template
    fallback, never raises, never returns empty), and is called with the
    injected `llm_reason` -- SAME `_llm_reason` closure the sentinel
    reasoner uses (allowed_tools=[], no actuation from this call).

    The WHOLE body is wrapped in try/except: any failure (bad app wiring,
    a raising `notify`, anything) is logged and degrades to returning
    None -- this must NEVER raise into the scheduler.
    """
    try:
        router = app.get("llm_router")
        allow_sensitive = router.automatic_allows_sensitive() if router is not None else False
        bundle = build_briefing_bundle(
            app.get("knowledge_store"), app.get("entity_cache"),
            today=today, allow_sensitive=allow_sensitive,
            advisory_store=app.get("advisory_store"),
        )
        text = await compose_briefing(bundle, llm_reason)
        await notify(text)
        return text
    except Exception:
        logger.error("run_daily_briefing failed", exc_info=True)
        return None


_NUDGE_THRESHOLD_LABELS = {"overdue": "Scaduto", "today": "Oggi", "tomorrow": "Domani"}


def _format_nudge_message(item: dict, threshold: str) -> str:
    """Deterministic (non-LLM) urgent-nudge message text.

    CRITICAL (Task 3 carry-forward): an obligation's `due_date` column is
    free TEXT with no write-time format validation, so a poisoned value
    that passed the store's lexicographic `upcoming_obligations` filter
    must NEVER be echoed verbatim into a notification. `due_nudges` has
    already re-derived `threshold` via `urgency_of` (which only ever
    returns "overdue"/"today"/"tomorrow"/None off a validated `%Y-%m-%d`
    parse) -- the label below is the only date information this message
    exposes, never the raw column value. `content` is sanitized through
    the shared `_san` filter (proxy._sanitize.sanitize_ha_value), same
    prompt-injection defense `build_briefing_message` applies -- relevant
    here too since this text is what actually reaches the user's device.
    """
    try:
        from .proxy._sanitize import sanitize_ha_value as _san
    except Exception:  # pragma: no cover - fallback difensivo
        _san = lambda v: v  # noqa: E731
    label = _NUDGE_THRESHOLD_LABELS.get(threshold, threshold or "")
    content = _san((item or {}).get("content") or "")
    return f"{label}: {content}"


async def run_urgent_nudges(store, *, today, seen, notify_item) -> int:
    """Slice 7 Task 4: the deduped urgent-nudge job, separate from the
    once-a-day briefing above so a deadline crossing into overdue/today/
    tomorrow doesn't wait until the next 08:00 run to be flagged.

    `due_nudges` (Task 3) is a pure query + dedup lookup that does NOT mark
    anything itself; marking only happens here, and only AFTER a
    successful `notify_item`, so a failed send is naturally retried on the
    next tick instead of being silently dropped.

    Per-item try/except: one failing notification must not block the rest
    of the batch, and a failure must not mark that (key, threshold) as
    seen. Outer guard: a `due_nudges`/`store` failure degrades to 0 sent
    rather than raising into the scheduler.
    """
    count = 0
    try:
        nudges = due_nudges(store, today=today, seen=seen)
    except Exception:
        logger.error("run_urgent_nudges: due_nudges query failed", exc_info=True)
        return 0

    for n in nudges:
        try:
            await notify_item(n["item"], n["threshold"])
            seen.mark(n["key"], n["threshold"])
            count += 1
        except Exception:
            logger.error("run_urgent_nudges: notify/mark failed for key=%r", n.get("key"), exc_info=True)
            continue
    return count


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
    `_on_startup`) per la stessa ragione di `run_daily_briefing`: si prova
    senza avviare l'applicazione.

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
    from .claude_runner import ClaudeRunner, RunnerBackendError
    from .llm_router import LLMRouter

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
    # Il semaforo (tiers/entity_tiers) resta anche senza la superficie
    # remota: lo legge ancora watcher/executor.py (propone/nega secondo il
    # tier), e lo costruisce apply_saved_policy() poco sotto quando l'utente
    # ha salvato una policy del gateway dalla UI. Va inizializzato QUI
    # comunque perche' un'installazione senza policy salvata
    # (apply_saved_policy ritorna subito) troverebbe la chiave assente e
    # qualche lettore fallirebbe con KeyError. Un dict vuoto e' gia' il
    # default sicuro: ogni consumatore legge `.get("tiers") or {}` e un
    # tiers vuoto fa risultare "off" (fail-closed) in
    # security.semaphore.effective_tier, mai fail-open.
    # NB (Fetta E2 Task 4): fino a qui, questa chiave veniva popolata da
    # parse_execute_policy in api/handlers_execute.py -- uscita con questo
    # task insieme a tutta la superficie /api/execute che leggeva
    # policy["tools"]/["allowed_entities"]/["allowed_services"]. Quei tre
    # campi non hanno piu' alcun consumatore. Il dispatcher che li leggeva
    # anche lui (tools/dispatcher.py) e' uscito -- fetta E2 Task 7. Review
    # finale fetta E2, I-1: task_engine.py non legge piu' `execute_policy`
    # per nessuna via -- solo "tiers"/"entity_tiers" restano letti, e solo
    # da watcher/* (la Sentinella).
    app["execute_policy"] = {}
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
    # Se l'utente ha configurato la policy gateway dalla UI, la deriva e la
    # applica a `app["execute_policy"]` (le CSV d'ambiente sono uscite nel
    # Task 4 -- non c'e' piu' nulla da sovrascrivere).
    from .api.handlers_gateway_policy import apply_saved_policy
    apply_saved_policy(app)

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
    await engine.start()
    app["engine"] = engine

    # Client Supervisor di sola lettura (add-on, disco, aggiornamenti). Senza
    # SUPERVISOR_TOKEN siamo su un'installazione standalone (container senza
    # Supervisor): non lo costruiamo affatto, cosi' evitiamo tre GET destinate
    # al timeout a ogni refresh. Il monitor riceve None e la sezione non compare.
    supervisor_token = os.environ.get("SUPERVISOR_TOKEN", "").strip()
    supervisor_client = None
    if supervisor_token:
        supervisor_client = SupervisorClient(token=supervisor_token)
        await supervisor_client.start()
        app["supervisor_client"] = supervisor_client
    else:
        logger.info(
            "SUPERVISOR_TOKEN assente: sezione supervisor dello stato di salute disattivata"
        )

    health_monitor = HealthMonitor(
        ha_client=ha_client,
        data_path=os.path.join(data_dir, "ha_health.json"),
        scheduler=engine._scheduler,
        supervisor_client=supervisor_client,
    )
    await health_monitor.start()
    app["health_monitor"] = health_monitor

    proposal_store = ProposalStore(
        db_path=os.path.join(data_dir, "proposals.db"),
        scheduler=engine._scheduler,
    )
    app["proposal_store"] = proposal_store

    _apprise_raw = os.environ.get("APPRISE_URLS", "[]")
    try:
        _apprise_urls: list[str] = json.loads(_apprise_raw)
        if not isinstance(_apprise_urls, list):
            _apprise_urls = []
    except Exception:
        _apprise_urls = []
    notify_config = {
        "ha_notify_service": os.environ.get("HA_NOTIFY_SERVICE", "notify.notify"),
        "apprise_urls": _apprise_urls,
        "retropanel_url": os.environ.get("RETROPANEL_URL", "http://retropanel:8098"),
    }
    # Deep-link ingress per le notifiche (issue live-verify #1): il tap apre
    # HIRIS invece della Dashboard home. Slug installato dal Supervisor -> path
    # frontend stabile `/hassio/ingress/<slug>`; se irraggiungibile, None ->
    # il deep-link viene omesso (nessuna regressione). Letto da notify_tools
    # (ha_push).
    _slug = await _fetch_addon_slug(os.environ.get("SUPERVISOR_TOKEN", ""))
    _ingress_click_path = f"/hassio/ingress/{_slug}" if _slug else None
    notify_config["ingress_click_path"] = _ingress_click_path
    app["ingress_click_path"] = _ingress_click_path
    app["theme"] = os.environ.get("THEME", "auto")

    tasks_data_path = os.environ.get("TASKS_DATA_PATH", "/data/tasks.json")
    # Review finale fetta E2, I-1: TaskEngine non riceve piu' `execute_policy`
    # ne' `request_stepup` -- l'unica azione che li usava (l'esecuzione di
    # `call_ha_service`) e' uscita da `_run_action` (task_engine.py). Un
    # tasks.json ereditato da un'installazione 1.x puo' ancora contenere
    # quell'azione: al trigger fallisce ora come "Unknown action type",
    # loggata, non piu' eseguita in silenzio.
    task_engine = TaskEngine(
        ha_client=ha_client,
        entity_cache=entity_cache,
        notify_config=notify_config,
        data_path=tasks_data_path,
    )
    await task_engine.start()
    app["task_engine"] = task_engine

    mqtt_pub = MQTTPublisher()
    await mqtt_pub.start(
        host=os.environ.get("MQTT_HOST", ""),
        port=int(os.environ.get("MQTT_PORT", "1883")),
        user=os.environ.get("MQTT_USER", ""),
        password=os.environ.get("MQTT_PASSWORD", ""),
    )
    app["mqtt_publisher"] = mqtt_pub
    engine.set_mqtt_publisher(mqtt_pub)

    # SP-4 Fase A Task 1: one-time removal of HA entities discovered under
    # the pre-rename MQTT scheme (hiris_<id> / hiris/agents) for chatbots
    # already loaded from disk — guarded by a marker file so it only runs
    # once per install, before anything republishes discovery under the new
    # chatbot_<id> / hiris/chatbots scheme.
    # SP-4 Fase B Task 3: cleanup_legacy_discovery() now also retracts the
    # old-scheme COMMAND entities (switch/button) — installs that already
    # booted 0.102.0 have the v1 marker written and would never re-run the
    # fixed cleanup, so the marker is bumped to a new versioned name. This
    # makes the cleanup run once more for exactly the affected installs
    # without ever re-running for everyone else on every boot.
    _mqtt_migration_marker = os.path.join(data_dir, ".mqtt_discovery_migrated_v2")
    if mqtt_pub._enabled and not os.path.exists(_mqtt_migration_marker):
        try:
            await mqtt_pub.cleanup_legacy_discovery(
                list(engine.list_chatbots().keys()),
                list(mqtt_pub._DISCOVERY_METRICS),
            )
            # The marker must only be written once the retraction publishes
            # above have actually reached the broker, not merely been
            # enqueued: if MQTT is unreachable at boot (HA host and add-ons
            # routinely start together), writing the marker right after
            # enqueueing would permanently skip the retraction, orphaning
            # the old hiris_<id>_* entities in HA forever. Bounded wait so a
            # genuinely-down broker doesn't hang startup; on timeout the
            # marker is left absent so the next boot retries.
            if await mqtt_pub.wait_drained(timeout=30.0):
                os.makedirs(data_dir, exist_ok=True)
                with open(_mqtt_migration_marker, "w", encoding="utf-8") as f:
                    f.write(datetime.now(timezone.utc).isoformat())
            else:
                logger.warning(
                    "MQTT legacy discovery cleanup: publish queue did not "
                    "drain within 30s (broker unreachable?) — marker not "
                    "written, retraction will retry on next boot"
                )
        except Exception as exc:
            logger.warning("MQTT legacy discovery cleanup failed: %s", exc)

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

    # Archivio delle segnalazioni del Brain. Il resto del cervello proattivo
    # (piu' sotto) usa lo stesso oggetto.
    from .brain.advisory_store import AdvisoryStore
    advisory_store = AdvisoryStore(os.path.join(data_dir, "advisory.db"))
    app["advisory_store"] = advisory_store

    from .brain.portrait_store import PortraitStore
    try:
        app["portrait_store"] = PortraitStore(os.path.join(data_dir, "portrait.db"))
        logger.info("PortraitStore ready")
    except Exception:
        # Un portrait.db corrotto (perdita di corrente, disco guasto) fa
        # sollevare sqlite3.DatabaseError da init_schema anche se connect()
        # riesce: senza questo try/except l'eccezione uscirebbe da
        # _on_startup e fermerebbe l'intero add-on (niente reasoner, niente
        # scheduler, niente chat) per un file che e' una cache ricostruibile.
        # I due consumatori del ritratto controllano gia' esplicitamente
        # `app.get("portrait_store") is None` e degradano a ""/skip: non
        # scriverla in app basta a innescare quella degradazione.
        logger.warning(
            "PortraitStore non disponibile (portrait.db corrotto o "
            "illeggibile): il ritratto della casa resta disattivato per "
            "questo avvio", exc_info=True,
        )

    # ── Sentinella (cervello proattivo, fetta 1) ──────────────────────────
    # Shares the SAME semaforo (execute_policy tiers) as the execute-API/gateway
    # — the single source of truth for what the AI is allowed to actuate.
    from .watcher.sentinel_store import SentinelStore
    from .watcher.guardian import Guardian
    from .watcher.policy import load_policy
    from .watcher.reasoner import reason
    from .watcher.executor import execute
    from .watcher.sentinel_proposal import propose_sentinel_script
    from .notifiche import send_notification
    import time as _time
    from datetime import datetime as _dt

    sentinel_store = SentinelStore(os.path.join(data_dir, "sentinel.db"))
    app["sentinel_store"] = sentinel_store

    from .brain.suggestions import SuggestionStore
    suggestion_store = SuggestionStore(os.path.join(data_dir, "suggestions.db"))
    app["suggestion_store"] = suggestion_store

    from .brain.reasoning_log import ReasoningLog
    reasoning_log = ReasoningLog(os.path.join(data_dir, "brain_reasoning.db"))
    app["reasoning_log"] = reasoning_log

    async def _gather_context(wake) -> dict:
        # Best-effort friendly_name from the entity cache; falls back to the
        # raw entity_id when unavailable. This part is unchanged from before
        # Task 4 and stays non-throwing on its own.
        try:
            cache = app.get("entity_cache")
            state = cache.get_state(wake.entity_id) if cache is not None else None
            fn = (state or {}).get("attributes", {}).get("friendly_name") if state else None
            friendly_name = fn or wake.entity_id
        except Exception:
            return {"friendly_name": wake.entity_id, "portrait": _portrait_context(app)}

        # Slice 6b Task 4: bounded, egress-gated memory recall added on top.
        # _reason_memory_context is itself failure-safe (never raises), but
        # this call is never allowed to prevent returning at least
        # {"friendly_name": ...} exactly like before Task 4.
        #
        # fetta 2b Task 2: `.snippets`/`.by_meaning` are read INSIDE this try
        # too (not just the await), so a malformed MemoryRecall can't raise
        # past this point either -- both fallback returns below stay reachable
        # only through this one except, never a second point of failure.
        # `memory_by_meaning` travels alongside `memory` in the context dict
        # so build_user_message can render the honest heading; it is popped
        # (like `memory`) before the context is JSON-dumped as "Contesto:".
        try:
            mem = await _reason_memory_context(app, embedder, wake, friendly_name)
            memory_snippets = mem.snippets
            memory_by_meaning = mem.by_meaning
            # Task 4 ("memoria unica 3a"): i DICHIARATI viaggiano insieme a
            # memory/memory_by_meaning, dentro lo stesso try -- un
            # MemoryRecall malformato non deve poter far fallire QUESTO
            # ramo diversamente dagli altri due campi.
            declared_items = mem.declared
        except Exception:
            return {"friendly_name": friendly_name, "portrait": _portrait_context(app)}
        return {"friendly_name": friendly_name, "memory": memory_snippets,
                "memory_by_meaning": memory_by_meaning,
                "declared": declared_items,
                "portrait": _portrait_context(app)}

    async def _llm_reason(system, user, *, model, max_tokens,
                          agent_id=None, allowed_entities=None, allowed_services=None):
        # allowed_tools=[] is falsy -> narrowing is SKIPPED (claude_runner.py:894-896):
        # this reasoning call receives every EVALUATION_ONLY_TOOLS entry
        # (claude_runner.py:210-222), create_task included -- NOT zero tools. The
        # real invariant is that set excludes the tools that ACT (call_ha_service,
        # send_notification, trigger_automation, toggle_automation, http_request).
        # The executor below does NOT act either since Task 6: `executor.execute()`
        # treats "green" like "yellow" (propose, never auto-act) -- see the comment
        # above `_act`'s removal, further down this function. Nothing downstream of
        # this reasoning call calls `ha.call_service` for the green tier anymore.
        #
        # Agenti v1.1 Fase 2 Task 3: `agent_id` + `allowed_entities`/
        # `allowed_services` are the reasoning agent's IDENTITY and PERIMETER.
        # They are `None` for every caller today (guardian wakes, briefing) --
        # the anonymous/unscoped call they always made. Situations/holistic/
        # coverage-review were also unscoped callers, and are gone entirely
        # since fetta E3 Task 4 (the ronda). The only supplier of a real
        # perimeter was a user-defined Agentbot with a perimeter block
        # (mode="objective"), via `_run_decision` -- that whole layer
        # (`watcher/agentbot_runner.py`, `_run_decision`'s own `agent_id`/
        # `perimeter` params) is gone since fetta E3 Task 3; `_run_decision`
        # itself (the last non-Agentbot caller of this shape) followed it out
        # in Task 4, once its own last caller (`_on_situation`) died with the
        # ronda.
        # Kept here, dormant, rather than stripped: the shape (identity +
        # allow-lists into the reasoning call) is exactly what a future
        # "Agenti" project would need to reintroduce, and every current
        # caller is already unaffected by its presence. `chatbot_id` is the
        # runner-side name of that identity: it used to
        # reach the tool dispatcher, which renamed it back to `agent_id` when
        # it stamped a freshly created Task (`tools/dispatcher.py`,
        # create_task branch) -- so passing it here is what would make an
        # emitted Task belong to the agent that emitted it instead of to
        # "hiris-default". fetta E2 Task 7: that dispatcher is gone and no
        # replacement calls create_task from this path, so today no Task is
        # ever actually emitted here -- the forwarding below is dead in
        # practice, kept only because removing it would be a second,
        # unrelated change (EVALUATION_ONLY_TOOLS/run_with_actions are
        # explicitly out of scope for this fetta, see
        # .superpowers/sdd/progress.md). Historically the two allow-lists
        # rode the SAME dispatcher parameters, ending up on the Task itself
        # -- where `task_engine._run_action`'s check used to enforce them at
        # execution time for `call_ha_service`. Review finale fetta E2, I-1:
        # that action type is gone from the engine entirely now, so even if
        # a Task were emitted here, nothing left in `_run_action` reads
        # these two allow-lists for enforcement.
        # La risoluzione del runner vive nel module-level `_reasoning_runner(app)`
        # invece che qui in linea, cosi' ogni chiamante guarda sempre lo
        # stesso oggetto (llm_router, poi engine._claude_runner).
        runner = _reasoning_runner(app)
        if runner is None or not hasattr(runner, "run_with_actions"):
            return ""
        try:
            out = await runner.run_with_actions(
                user_message=user, system_prompt=system,
                allowed_tools=[], model=model, max_tokens=max_tokens, agent_type="agent",
                chatbot_id=agent_id,
                allowed_entities=allowed_entities, allowed_services=allowed_services)
        except RunnerBackendError:
            # All backends failed (or a pinned-model call with no fallback,
            # review C/#13). Reasoning degrades to empty -> the reasoner treats
            # it as "no verdict" (alert-only/safe), never crashes the wake/round.
            logger.warning("_llm_reason: all LLM backends failed; degrading to empty verdict")
            return ""
        if isinstance(out, tuple):
            return out[0] or ""
        return out or ""

    # ── Daily butler briefing + deduped urgent nudges (Slice 7, Task 4) ────
    # Replaces the old per-obligation daily spam job (id "hiris_due_reminders",
    # one notification per due obligation, no dedup, template-only text)
    # with ONE consolidated grounded briefing
    # (build_briefing_bundle + compose_briefing, Tasks 1-2) at 08:00, plus a
    # separate deduped urgent-nudge job (Task 3's due_nudges/ReminderSeen)
    # that flags overdue/today/tomorrow deadlines between briefings without
    # re-sending ones already delivered. Both helpers (run_daily_briefing,
    # run_urgent_nudges) live at module level and are independently
    # unit-testable -- see test_briefing_wiring.py.
    #
    # Single long-lived ReminderSeen instance: its sidecar JSON file is a
    # read-modify-write (load, mutate, atomic replace) that is NOT safe to
    # race across concurrent instances (Task 3's concurrency note) -- one
    # instance shared by every _urgent_nudges tick avoids that.
    reminder_seen = ReminderSeen(data_dir)

    async def _briefing_notify(message: str) -> None:
        # SAME notification path the removed job used (ha_push channel).
        await send_notification(ha_client, message, "ha_push", notify_config)

    async def _daily_briefing() -> None:
        await run_daily_briefing(
            app, today=date.today(), llm_reason=_llm_reason, notify=_briefing_notify,
        )

    async def _nudge_notify(item: dict, threshold: str) -> None:
        # Deterministic message (NOT via the LLM) -- see _format_nudge_message
        # for why the raw due_date column is never echoed here.
        await send_notification(
            ha_client, _format_nudge_message(item, threshold), "ha_push", notify_config,
        )

    async def _urgent_nudges() -> None:
        store = app.get("knowledge_store")
        if store is None:
            return
        await run_urgent_nudges(
            store, today=date.today(), seen=reminder_seen, notify_item=_nudge_notify,
        )

    engine._scheduler.add_job(
        _daily_briefing,
        trigger="cron", hour=8, minute=0,
        id="hiris_daily_briefing", replace_existing=True, misfire_grace_time=3600,
    )
    # Interval (not a single daily cron) so an obligation that becomes urgent
    # BETWEEN morning briefings -- e.g. a document ingested midday creating a
    # deadline due tomorrow -- gets its punctual nudge within hours instead of
    # waiting for the next 08:00. Dedup (ReminderSeen) keeps each threshold to
    # one notification regardless of how many ticks see it.
    engine._scheduler.add_job(
        _urgent_nudges,
        trigger="interval", hours=6,
        id="hiris_urgent_nudges", replace_existing=True, misfire_grace_time=3600,
    )

    async def _notify(message, *, title):
        # Reuses the exact notify_config object passed to the dispatcher/
        # TaskEngine for send_notification — not a re-invented config shape.
        await send_notification(ha_client, message, "ha_persistent", notify_config, title=title)

    # `_act` (chiamava `dispatcher.dispatch("call_ha_service"/"create_task")`
    # per il tier verde con opt-in) e' uscita qui: fetta E2 Task 6, "la
    # Sentinella smette di usare il dispatcher". Non e' stata sostituita con
    # un'altra via d'attuazione: `executor.execute()` ora tratta il tier
    # "green" esattamente come "yellow" (propone, non agisce piu' da solo).
    # Con lei sono usciti anche il parametro `allow_green_auto` (ovunque lo
    # passasse: qui sotto, `_run_decision`, `_run_agentbot`,
    # `_execute_decision`) e l'opzione add-on `sentinel_allow_green_auto`.
    #
    # Review finale, I-1: questo NON era ancora il punto in cui "l'unica
    # attuazione automatica rimasta smette di esistere" -- `task_engine.py`
    # (`_run_action`) chiamava ancora `ha.call_service` per i task legacy
    # ricaricati da `/data/tasks.json` al boot (upgrade da un'installazione
    # 1.x, l'unico percorso di deploy previsto). Il fix di quel residuo e'
    # nel Task Engine stesso (vedi il commento in cima a `_run_action`,
    # task_engine.py): dopo il fix, `call_ha_service` non e' piu' un'azione
    # riconosciuta da NESSUN motore -- ne' dalla Sentinella (qui sopra),
    # ne' dai Task differiti (task_engine.py). Questo E' il punto in cui
    # l'unica attuazione automatica rimasta smette di esistere.

    async def _propose(decision, wake):
        # Consolidamento 1.2: cio' che la Sentinella propone e' UNA chiamata di
        # servizio (rimedio una-tantum), non una regola permanente. Prima
        # veniva salvata come proposta 'ha_automation' con dentro
        # {"suggested_action": ...}: all'approvazione finiva in HA come
        # automazione senza trigger ne' azioni. Ora la proposta e' di tipo
        # ha_script e contiene una vera config di script — vedi
        # watcher/sentinel_proposal.py per il perche' non un'automazione.
        #
        # L'esito ritornato e' quello che finisce nella timeline: "propose" solo
        # se una proposta esiste davvero, "alert" quando si e' ripiegato sulla
        # notifica (azione non confezionabile o salvataggio fallito).
        return await propose_sentinel_script(
            decision, wake,
            save=proposal_store.save, notify=_notify,
            notify_title="HIRIS Sentinella",
            routing_reason="Proposta dalla Sentinella (autonomia graduata)")

    async def _on_wake(wake):
        decision = None
        outcome = "error"
        try:
            decision = await reason(wake, gather_context=_gather_context, llm_reason=_llm_reason)
            # Semaforo source of truth: the SAME execute_policy the execute-API
            # and gateway use, never the sentinel detector policy. Empty tiers
            # → effective_tier() returns "off" → alert-only (SAFE default).
            _ep = app.get("execute_policy") or {}
            tiers = _ep.get("tiers") or {}
            entity_tiers = _ep.get("entity_tiers") or {}
            outcome = await execute(
                decision, wake,
                tiers=tiers, entity_tiers=entity_tiers,
                notify=_notify, propose=_propose)
        except Exception:
            logger.exception("sentinel on_wake failed")
            outcome = "error"
        sentinel_store.record_event({
            "ts": _time.time(), "kind": wake.signal_kind, "entity_id": wake.entity_id,
            "verdict": getattr(decision, "verdict", None), "severity": wake.severity_hint,
            "outcome": outcome, "message": getattr(decision, "message", "")})

    # fetta E3 Task 3: la cache in-memory degli Agentbot evento-triggerati
    # (`handlers_agentbots.set_agentbots`/`get_event_agentbots`) e il suo
    # ponte verso `Guardian.on_state_changed` sono usciti insieme al modulo
    # che li popolava: nessun codice legge piu' `app["user_agentbots"]`. Il
    # Guardian resta vivo (fino al Task 7) senza i due kwarg opzionali
    # `get_user_agentbots`/`run_agentbot` -- sono `Optional` di suo, quindi
    # continua a funzionare col solo percorso DETECTORS built-in.
    guardian = Guardian(
        sentinel_store, lambda: load_policy(data_dir), _on_wake,
        cooldown_sec=int(os.environ.get("SENTINEL_COOLDOWN_SEC", "1800")),
        daily_cap=int(os.environ.get("SENTINEL_DAILY_CAP", "20")))
    guardian.set_policy(load_policy(data_dir))
    app["guardian"] = guardian
    ha_client.add_state_listener(
        lambda evt: _spawn(guardian.on_state_changed(evt), name="guardian_on_state_changed")
    )

    def _reset_sentinel_counter() -> None:
        sentinel_store.reset_wakes(_dt.now().strftime("%Y-%m-%d"))

    engine._scheduler.add_job(
        _reset_sentinel_counter, trigger="cron", hour=0, minute=1,
        id="hiris_sentinel_reset", replace_existing=True, misfire_grace_time=3600)

    # fetta E3 Task 4 ("esce la casa vecchia, e con lei chi la guardava"): la
    # ronda periodica (snapshot + le due situazioni hot_and_away/
    # away_alarm_off + la revisione olistica) e' uscita per intero --
    # girava ogni 15 minuti con tutte le situazioni spente di fabbrica
    # (watcher/policy.py), consumando una GET /api/states e una chiamata
    # meteo a vuoto, e dalla fetta E2 il suo execute() non attuava piu'
    # nulla. Con lei sono usciti `_snap_deps`/`_snapshot` (watcher/snapshot.py
    # + watcher/evaluator.py + watcher/situations.py), e -- verificato che
    # nessun chiamante restava dopo aver tolto evaluator/situazioni/arrivo/
    # olistico sotto -- anche `_record_situation_event`, `_run_decision` e
    # `_on_situation`: erano tre gradini della stessa catena, orfani a
    # cascata. Il Guardian (sopra) ha sempre avuto la propria `_on_wake`
    # indipendente: non perde nulla.
    #
    # `_snap_deps["get_health"]` era l'ultima dipendenza reale che teneva
    # `health_monitor` agganciato a questa macchina -- tolta qui, libera il
    # Task 11 (che NON e' questo task: `health_monitor` resta orfano di
    # proposito, costruito e servito su /api/health esattamente come prima).
    #
    # Silenzio dichiarato: da qui la casa non viene piu' "guardata" ogni 15
    # minuti. Nessun log da aggiungere per questo -- non c'e' piu' codice che
    # possa accorgersene.

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
    # reasoning_queue.count_chat_today() -- independent of SENTINEL_DAILY_CAP.
    app["chat_daily_cap"] = int(os.environ.get("CHAT_DAILY_CAP", "50"))

    # fetta E3 Task 4: `_holistic_reason` (il cervello auto-proponente sulla
    # cadenza olistica: coverage-review, apply_suggestions, auto_tune_
    # detectors, il ramo bridge-enqueue) e' uscito con la ronda che lo
    # chiamava (`SituationEvaluator`/job `hiris_sentinel_ronda`, sopra).
    # Orfani DI PROPOSITO qui, non cancellati -- li raccoglie il Task 5, che
    # trova la checklist d'ingresso nel report di questo task:
    # `brain.coverage_review` (COVERAGE_REVIEW_SYSTEM, build_review_context,
    # build_review_message, parse_suggestions), `brain.suggestions`
    # (apply_suggestions, reconcile_proposal_outcome, SuggestionStore --
    # quest'ultima resta wired per l'API /api/suggestions), `brain.
    # cognitive_loop` (auto_tune_detectors, trace_applied_coverage),
    # `brain.learned_thresholds`, `reasoning_log.capture()` (l'oggetto e il
    # suo job di prune restano wired, solo `.capture()` non ha piu'
    # chiamanti), `tools.proposal_tools.create_automation_proposal`. Il
    # ramo bridge-enqueue di `_holistic_reason` era l'UNICO produttore di
    # job `kind="holistic"` in `reasoning_queue` -- da qui in poi quel kind
    # non viene piu' mai accodato (vedi `_reasoning_sweep` sotto).

    # SP-3 Task 8: periodic read-only health scan (8 checks: 5 sulla casa, 3
    # sul sistema tramite il Supervisor) reconciled into
    # the AdvisoryStore, plus a nightly prune of the reasoning capture log.
    from .brain.health_scan import run_health_scan

    async def _run_health_scan():
        try:
            pol = app.get("execute_policy") or {}
            await run_health_scan(
                ha_client=ha_client, entity_cache=app.get("entity_cache"),
                tiers=pol.get("tiers") or {}, entity_tiers=pol.get("entity_tiers") or {},
                store=advisory_store, now=datetime.now(timezone.utc),
                # Senza SUPERVISOR_TOKEN lo slot non esiste affatto: `.get`
                # restituisce None e i controlli di sistema restano muti.
                supervisor_client=app.get("supervisor_client"),
                # Notifica push per le sole segnalazioni gravi nuove o
                # riaperte: stesso `notify_config` (e stesso deep-link) del
                # briefing e dei solleciti. Disattivabile con l'opzione
                # `brain_notify_high`, attiva per impostazione predefinita.
                notify_config=notify_config,
                notify_enabled=env_bool("BRAIN_NOTIFY_HIGH", True))
        except Exception:
            logger.exception("health scan failed")

    engine._scheduler.add_job(
        _run_health_scan, trigger="interval",
        minutes=int(os.environ.get("HIRIS_HEALTH_SCAN_MINUTES", "30")),
        id="hiris_health_scan", replace_existing=True, misfire_grace_time=300)

    async def _portrait_observe_job():
        try:
            n = await _osserva_la_casa(app)
            if n:
                logger.info("ritratto: %d cambiamenti registrati", n)
        except Exception:
            logger.warning("portrait observe job failed", exc_info=True)

    engine._scheduler.add_job(
        _portrait_observe_job, "interval",
        minutes=int(os.environ.get("HIRIS_PORTRAIT_OBSERVE_MINUTES", "15")),
        id="hiris_portrait_observe", replace_existing=True,
        misfire_grace_time=300,
    )

    def _run_reasoning_prune():
        try:
            reasoning_log.prune(max_rows=500, max_age_days=30)
        except Exception:
            logger.exception("reasoning prune failed")

    engine._scheduler.add_job(
        _run_reasoning_prune, trigger="cron", hour=3, minute=15,
        id="hiris_reasoning_prune", replace_existing=True, misfire_grace_time=3600)

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
        engine.set_task_engine(task_engine)
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
    if "mqtt_publisher" in app:
        await app["mqtt_publisher"].stop()
    if "knowledge_store" in app:
        app["knowledge_store"].close()
    if "vault" in app:
        app["vault"].close()
    if "proposal_store" in app:
        app["proposal_store"].close()
    if "history_store" in app:
        app["history_store"].close()
    if "sentinel_store" in app:
        app["sentinel_store"].close()
    if "suggestion_store" in app:
        app["suggestion_store"].close()
    if "reasoning_log" in app:
        app["reasoning_log"].close()
    if "advisory_store" in app:
        app["advisory_store"].close()
    if "portrait_store" in app:
        app["portrait_store"].close()
    if "reasoning_queue" in app:
        app["reasoning_queue"].close()
    if "archivio_casa" in app:
        app["archivio_casa"].chiudi()
    if "archivio_memoria" in app:
        app["archivio_memoria"].chiudi()
    if "task_engine" in app:
        await app["task_engine"].stop()
    await app["engine"].stop()
    await app["ha_client"].stop()
    if app.get("supervisor_client") is not None:
        await app["supervisor_client"].stop()
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
    app.router.add_post("/api/chatbots/{agent_id}/run", handle_run_chatbot)
    app.router.add_get("/api/entities", handle_list_entities)
    app.router.add_get("/api/suggestions", handle_list_suggestions)
    app.router.add_post("/api/suggestions/{id}/undo", handle_undo_suggestion)
    app.router.add_get("/api/chatbots/{agent_id}/usage", handle_get_chatbot_usage)
    app.router.add_post("/api/chatbots/{agent_id}/usage/reset", handle_reset_chatbot_usage)
    app.router.add_get("/api/chatbots/{agent_id}/chat-history", handle_get_chat_history)
    app.router.add_delete("/api/chatbots/{agent_id}/chat-history", handle_clear_chat_history)
    app.router.add_get("/api/tasks", handle_list_tasks)
    app.router.add_get("/api/tasks/{task_id}", handle_get_task)
    app.router.add_delete("/api/tasks/{task_id}", handle_cancel_task)
    app.router.add_get("/api/models", handle_list_models)
    app.router.add_get("/api/models/config", handle_get_models_config)
    app.router.add_put("/api/models/config", handle_save_models_config)
    app.router.add_get("/api/health/ha", handle_get_ha_health)
    app.router.add_post("/api/health/ha/refresh", handle_refresh_ha_health)
    app.router.add_get("/api/proposals", handle_list_proposals)
    app.router.add_get("/api/proposals/{proposal_id}", handle_get_proposal)
    app.router.add_post("/api/proposals/{proposal_id}/apply", handle_apply_proposal)
    app.router.add_post("/api/proposals/{proposal_id}/reject", handle_reject_proposal)
    # "backups" e' un segmento fisso a un livello diverso da {url_path}/restore:
    # nessuna ambiguita' di routing fra le due rotte.
    app.router.add_get("/api/dashboards/backups", handle_list_dashboard_backups)
    app.router.add_post("/api/dashboards/{url_path}/restore", handle_restore_dashboard)
    app.router.add_get("/api/knowledge/pending", handle_list_pending)
    app.router.add_post("/api/knowledge/{id}/approve", handle_approve)
    app.router.add_post("/api/knowledge/{id}/reject", handle_reject)
    app.router.add_post("/api/knowledge", handle_manual_add)

    from .api.handlers_gateway_policy import (
        handle_get_gateway_policy, handle_save_gateway_policy, handle_autonomy_summary,
    )
    app.router.add_get("/api/gateway/policy", handle_get_gateway_policy)
    app.router.add_post("/api/gateway/policy", handle_save_gateway_policy)
    app.router.add_post("/api/gateway/autonomy-summary", handle_autonomy_summary)

    from .api.handlers_history_policy import (
        handle_get_history_policy, handle_save_history_policy,
    )
    app.router.add_get("/api/history/policy", handle_get_history_policy)
    app.router.add_post("/api/history/policy", handle_save_history_policy)

    from .api.handlers_sentinel import (
        handle_get_sentinel_policy, handle_save_sentinel_policy, handle_sentinel_timeline,
    )
    app.router.add_get("/api/sentinel/policy", handle_get_sentinel_policy)
    app.router.add_post("/api/sentinel/policy", handle_save_sentinel_policy)
    app.router.add_get("/api/sentinel/timeline", handle_sentinel_timeline)

    # fetta E3 Task 3: le quattro rotte CRUD /api/agentbots sono uscite
    # insieme ad api/handlers_agentbots.py. La pagina #/agentbots
    # (agentbot-route.js), il suo editor (agentbot-editor.js) e il wizard
    # (create-wizard.js: POST /api/agentbots) restano nello static/ (fetta
    # E5) e da qui in poi ricevono 404 -- non riparati, per costruzione.

    from .api.handlers_reasoning import handle_reasoning_claim, handle_reasoning_submit
    app.router.add_post("/api/reasoning/claim", handle_reasoning_claim)
    app.router.add_post("/api/reasoning/submit", handle_reasoning_submit)

    from .api.handlers_brain import (
        handle_brain_feed, handle_brain_reasoning, handle_list_advisories,
        handle_ack_advisory, handle_dismiss_advisory,
    )
    app.router.add_get("/api/brain/feed", handle_brain_feed)
    app.router.add_get("/api/brain/reasoning", handle_brain_reasoning)
    app.router.add_get("/api/brain/advisories", handle_list_advisories)
    app.router.add_post("/api/brain/advisories/{id}/ack", handle_ack_advisory)
    app.router.add_post("/api/brain/advisories/{id}/dismiss", handle_dismiss_advisory)

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
