# hiris/app/server.py
import asyncio
import contextlib
import hashlib
import json
import logging
import os
import re
import shutil
import time
from datetime import date, datetime, timezone
import aiohttp
import uvicorn
from aiohttp import web
from apscheduler.triggers.cron import CronTrigger
from .api.handlers_chat import handle_chat, handle_chat_reply_poll
from .api.handlers_chatbots import (
    handle_list_chatbots, handle_create_chatbot, handle_get_chatbot,
    handle_update_chatbot, handle_delete_chatbot, handle_run_chatbot,
    handle_get_chatbot_usage, handle_reset_chatbot_usage,
    handle_context_preview,
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
from .api.handlers_knowledge import (
    handle_list_pending, handle_approve, handle_reject, handle_manual_add,
)
from .api.handlers_gateway_pending import verify_otp, execute_pending, resolve_pending
from .proxy.health_monitor import HealthMonitor
from .proxy.proposal_store import ProposalStore
from .chatbot_engine import ChatbotEngine
from .task_engine import TaskEngine
from .version import read_version
from .proxy.ha_client import HAClient
from .env_util import env_bool
from .proxy.entity_cache import EntityCache
from .proxy.knowledge_db import KnowledgeDB
from .proxy.semantic_context_map import SemanticContextMap
from .backends.embeddings import build_embedding_provider
from .brain.knowledge_store import KnowledgeStore
from .brain.memory_migration import migrate_agent_memories
from .brain.privacy import VaultStore, Pseudonymizer
from .brain.reasoner_memory import relevant_memory
from .brain.briefing import build_briefing_bundle, compose_briefing
from .brain.reminders import ReminderSeen, due_nudges
from .watcher.policy import load_policy
from .watcher.signals import Decision
# Agenti v1.1 Fase 2 Task 5: STESSO predicato con cui `_validate_perimeter`
# accetta `budget_tokens`/`deadline_min` (intero > 0, `bool` deliberatamente
# escluso). Riusarlo invece di riscriverlo evita che il consumo del perimetro
# finisca a ragionare con regole diverse da quelle con cui e' stato validato.
from .watcher.agentbots import is_positive_int
from .api.middleware_internal_auth import internal_auth_middleware
from .api.middleware_csrf import csrf_middleware
from .mqtt_publisher import MQTTPublisher
from .llm_router import _VALID_BACKEND_NAMES as _VALID_POLICY_BACKENDS
from .watcher.detectors import make_generic_detector
from .watcher.agentbots import load_agentbots as _load_scheduled_agentbots
# to_apscheduler_crontab moved to watcher/agentbots.py (review L/1; this
# module file was renamed from its Fase A filename in SP-4 Fase B Task 5) so
# validate_agentbot() can reuse the exact same translation to reject a
# shape-valid-but-value-invalid cron (e.g. hour=99) AT CREATION time,
# instead of only failing later, silently, here at registration.
from .watcher.agentbots import to_apscheduler_crontab as _to_apscheduler_crontab

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


def _confirmation_push_message(label: str, inputs: dict, otp: str) -> str:
    """Build the phone-push confirmation message for a chat step-up action.

    This notification IS the entire human-in-the-loop safety check: the tap or
    typed OTP executes exactly the frozen ``inputs`` (denylist included), never
    re-derived. So the human on the phone must see WHICH entity is being
    actuated, not just ``domain.service`` — otherwise a prompt-injected LLM
    could request e.g. turn_on on ``switch.boiler`` while the chat discusses
    something unrelated, and the user would have no way to notice.

    Extracts the target entity id(s) from ``inputs["data"]["entity_id"]`` and/or
    ``inputs["target"]["entity_id"]`` (either a single string or a list), joins
    them for display, and falls back to a placeholder when no entity_id is
    present at all (e.g. a broadcast service call with no target). The OTP is
    interpolated here ONLY — this string is passed straight to ``notify(...)``
    (the phone push), never returned to the chat/LLM side.
    """
    # Show the UNION of data+target entities -- the exact set that actuates
    # after confirmation (review A/#5 I1). First-wins here would let a decoy
    # `data` entity hide a smuggled `target` entity the human is really
    # approving. Uses the same normalizer the gate/execution use.
    from .security.semaphore import normalize_target
    ids = normalize_target(inputs.get("data"), inputs.get("target")).entity_ids
    targets_str = ", ".join(ids) if ids else "(nessuna entità)"
    return (f'HIRIS: confermi "{label}" su {targets_str}? '
            f'Tocca Conferma, oppure usa il codice {otp}.')


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


# Chat OTP fallback: the LLM calls confirm_pending(code) when the user
# types the code from the phone notification. `code` is untrusted tool
# input from the LLM, so it is validated (exactly 6 ASCII digits) BEFORE it
# ever reaches verify_otp's comparison. On match, the FROZEN pending
# entry is executed via execute_pending — never anything re-derived from
# this tool call — so the OTP only unlocks the action, it cannot alter it.
#
# Module-level (rather than a closure captured inside _on_startup) so tests
# can exercise the real 6-digit gate directly instead of a hand-rebuilt
# replica of it.
async def confirm_pending_execute(app: web.Application, *, code: str, user: str) -> dict:
    if not (isinstance(code, str) and code.isascii() and code.isdigit() and len(code) == 6):
        return {"error": "Codice non valido."}
    data_dir = app["data_dir"]
    entry = verify_otp(data_dir, user, code)
    if entry is None:
        return {"error": "Codice non valido o scaduto."}
    res = await execute_pending(app, entry)
    resolve_pending(data_dir, entry["id"], "approved")
    return {"ok": True, "result": res}


# Step-up chat (Slice 2): when the semaforo gate returns "confirm" on a
# chat-initiated call_ha_service, freeze the action as a pending (never
# re-derived later — this exact `inputs` is what a later approve/OTP will
# execute) and push tap+OTP to the chatting user's phone. The OTP travels
# ONLY in the phone notification, never in this function's return value.
#
# Module-level (same rationale as confirm_pending_execute above) so tests
# can exercise the real no-identity guard and the yellow/red actionable
# split directly instead of a hand-rebuilt replica of it.
async def request_confirmation_stepup(
    app: web.Application, data_dir: str, *, tool: str, inputs: dict, tier: str, user: str | None,
) -> dict | None:
    from .api.handlers_gateway_pending import (
        create_pending, notify, invalidate_user_otp_pendings,
    )
    from .api.handlers_gateway_policy import private_notify_service_for_user

    # Safety (Fix 5): with no real identity (falsy user, or the "home"
    # no-identity fallback bucket — see brain/identity.py's `uid or "home"`)
    # there is no phone to target and no chat OTP flow that could ever
    # resolve this pending, since verify_otp() matches on `user`. Minting one
    # anyway would create a dead pending nobody can confirm. Return None so
    # the dispatcher falls back to the Slice-1 "richiede conferma" error.
    if not user or user == "home":
        return None
    # Safety (Review C/#1 + backlog #4): the OTP secret (and one-tap approval)
    # must land only on a channel bound to THIS user. `private_notify_service_
    # for_user` returns a service only when it comes from the explicit per-user
    # mapping; it returns None for the shared, globally-configured
    # `notify_service` (which may be a family group or a shared dashboard) and
    # for the `notify.persistent_notification` default. In those cases there is
    # no private channel to complete step-up, so fail closed exactly like the
    # no-identity guard above: mint no pending, and let the dispatcher fall
    # back to the Slice-1 "richiede conferma" error.
    svc = private_notify_service_for_user(app, user)
    if not svc:
        logger.warning(
            "step-up confirmation skipped for user=%s: no PRIVATE per-user "
            "notify target configured (a shared/global notify service must "
            "not carry the OTP secret; set notify_users[%s] to enable "
            "chat step-up)", user, user,
        )
        return None
    label = f"{inputs.get('domain')}.{inputs.get('service')}"
    # At most one OTP pending per user at a time: `verify_otp` resolves a
    # typed code by scanning for the first live pending bound to `user`, so a
    # second concurrent one would be ambiguous. Invalidate any prior chat OTP
    # pending for this user before minting the new one.
    invalidate_user_otp_pendings(data_dir, user)
    entry = create_pending(
        data_dir, tool=tool, inputs=inputs, tier=tier,
        origin="chat", label=label, user=user, with_otp=True,
    )
    msg = _confirmation_push_message(label, inputs, entry["otp"])
    # Owner decision (Fix 3): red/dangerous pendings are page/OTP-only — no
    # one-tap notification buttons (matches the gateway's execute-API
    # behaviour in handlers_execute.py, which uses actionable=(tier ==
    # "yellow")). Only yellow gets actionable=True. The OTP is included in
    # `msg` above unconditionally either way.
    otp_sent = await notify(app, message=msg, actionable=(tier == "yellow"),
                            nonce=entry["id"], service=svc)
    return {"id": entry["id"], "otp_sent": bool(otp_sent)}


def _make_task_stepup(*, app, data_dir: str, owner: str | None):
    """Fase 2.5 C2: chiusura di step-up per i Task autonomi. `owner` e'
    l'identita' (chiave di notify_users) a cui recapitare tap/OTP. Falsy ->
    None (TaskEngine fara' fail-closed allo skip). La guardia canale-privato
    vive dentro request_confirmation_stepup (private_notify_service_for_user)."""
    if not owner:
        return None

    async def _request_stepup(*, tool: str, inputs: dict, tier: str):
        return await request_confirmation_stepup(
            app, data_dir, tool=tool, inputs=inputs, tier=tier, user=owner)

    return _request_stepup


# ---------------------------------------------------------------------------
# Slice 5b Task 5: SCHEDULED (cron/interval) user Agentbots (renamed from
# "lens" in SP-4 Fase A Task 3) -- per-Agentbot jobs on `engine._scheduler`,
# the SAME AsyncIOScheduler instance the built-in ronda/reset/due-reminders
# jobs use (verified: `_on_startup` never creates a second scheduler).
# Module-level (same rationale as confirm_pending_execute/
# request_confirmation_stepup above) so tests can drive
# `register_agentbot_schedules` against a fake scheduler + fake entity_cache
# without booting the whole aiohttp app.
# ---------------------------------------------------------------------------

_AGENTBOT_JOB_PREFIX = "hiris_agentbot_"


def _condition_holds(condition: dict | None, cache) -> bool:
    """Evaluate a schedule trigger's optional `trigger.condition`
    (`{entity_id, operator, threshold}`, already whitelist-validated by
    `watcher.agentbots._validate_condition`) against the CURRENT cached state
    of `condition["entity_id"]` (`entity_cache.get_state`). Absent condition
    -> True (nothing to gate on).

    Reuses `make_generic_detector` (Task 2) with a synthesized one-shot
    trigger dict so the exact same operator/threshold comparison applies
    here as to a real event-triggered Agentbot -- including the no-data
    guard for "unavailable"/"unknown"/"" states and the numeric-vs-string
    fallback for ==/!= -- rather than a second, driftable implementation of
    the same comparison.

    Fail-safe: missing cache, missing entity_id, an entity never seen by the
    cache, or the detector raising all resolve to False -- a conditioned
    scheduled Agentbot must never fire when its condition can't be
    positively confirmed.
    """
    if not condition:
        return True
    if cache is None:
        return False
    entity_id = condition.get("entity_id")
    if not entity_id:
        return False
    try:
        state = cache.get_state(entity_id)
    except Exception:
        logger.debug("register_agentbot_schedules: cache.get_state(%s) failed", entity_id, exc_info=True)
        return False
    if state is None:
        return False
    detector = make_generic_detector({
        "entity_id": entity_id,
        "operator": condition.get("operator"),
        "threshold": condition.get("threshold"),
    })
    try:
        sig = detector(entity_id, None, state, {}, time.time())
    except Exception:
        logger.debug("register_agentbot_schedules: condition detector failed for %s", entity_id, exc_info=True)
        return False
    return sig is not None


async def _run_scheduled_agentbot(agentbot: dict, *, cache, run_agentbot) -> None:
    """The per-Agentbot job callback registered by
    `register_agentbot_schedules`. Wrapped end-to-end in try/except (log +
    return) so one broken scheduled Agentbot (a condition entity that
    vanished, `run_agentbot` raising, ...) can never take down the shared
    AsyncIOScheduler or any sibling job."""
    agentbot_id = agentbot.get("id", "-")
    try:
        trigger = agentbot.get("trigger") or {}
        condition = trigger.get("condition")
        if condition and not _condition_holds(condition, cache):
            return
        entity_id = condition.get("entity_id", "-") if condition else "-"
        # Task 5 review Fix 2: a scheduled Agentbot's own interval/cron
        # cadence IS its rate limiter -- bypass the ~30-min sentinel
        # cooldown here (cooldown_sec=0) so e.g. an interval_min=5 Agentbot
        # isn't silently suppressed by it. `run_agentbot`'s daily_cap (an
        # unrelated, unchanged safety net) and every other gate still apply
        # unchanged.
        await run_agentbot(agentbot, {"entity_id": entity_id}, cooldown_sec=0)
    except Exception:
        logger.exception("scheduled agentbot %s failed", agentbot_id)


async def register_agentbot_schedules(app: web.Application) -> None:
    """(Re)register per-Agentbot scheduler jobs for every enabled,
    SCHEDULE-triggered user Agentbot (Slice 5b Task 5), and remove any
    `hiris_agentbot_*` job whose Agentbot no longer exists, is disabled, or
    is no longer schedule-triggered. Idempotent -- safe to call at startup
    and again after every Agentbot save (Task 6, via
    `app["register_agentbot_schedules"]`).

    Reads `engine._scheduler` (the SAME scheduler instance the built-in
    ronda/reset jobs use), `data_dir` (to reload the current Agentbot set)
    and `entity_cache` (for the schedule trigger's optional `condition`,
    checked at fire time by `_run_scheduled_agentbot`/`_condition_holds`)
    straight off `app`, mirroring `confirm_pending_execute`'s
    "module-level, reads from app, testable without booting `_on_startup`"
    shape.
    """
    engine = app.get("engine")
    scheduler = getattr(engine, "_scheduler", None)
    if scheduler is None:
        return

    data_dir = app.get("data_dir")
    agentbots = _load_scheduled_agentbots(data_dir) if data_dir else []
    # Agenti v1.1 Fase 2 Task 4: the Fase 1 fix-wave `mode` gate that used to
    # sit here (mirroring `handlers_agentbots.get_event_agentbots`'s own gate)
    # is REMOVED for the planned path only, by design -- the plan's decision
    # is "gli eventi restano dominio delle regole" (that gate stays on
    # `get_event_agentbots`), but a schedule-triggered objective Agentbot is
    # a valid, intended combination (`validate_agentbot` allows objective+
    # schedule; only objective+event is forbidden) that must now actually
    # fire on its cadence. No other change: same job registration, same
    # `_run_scheduled_agentbot` callback, same `run_agentbot` call as any
    # schedule-triggered rule -- the security posture (EVALUATION_ONLY_TOOLS,
    # semaforo, force_notify_only) is entirely unrelated to this gate and is
    # unchanged.
    scheduled = {
        a["id"]: a for a in agentbots
        if a.get("enabled") and (a.get("trigger") or {}).get("type") == "schedule"
    }

    # Remove orphaned jobs: an Agentbot that was deleted, disabled, or
    # switched away from a schedule trigger since the last registration.
    # Enumeration pattern mirrors `chatbot_engine.py`'s `_unschedule_chatbot`.
    for job in list(scheduler.get_jobs()):
        if not job.id.startswith(_AGENTBOT_JOB_PREFIX):
            continue
        agentbot_id = job.id[len(_AGENTBOT_JOB_PREFIX):]
        if agentbot_id not in scheduled:
            try:
                scheduler.remove_job(job.id)
            except Exception:
                logger.debug("register_agentbot_schedules: remove_job(%s) failed", job.id, exc_info=True)

    cache = app.get("entity_cache")
    run_agentbot = app.get("run_agentbot")

    def _make_callback(agentbot: dict):
        # Bind `agentbot` via this factory's own parameter (a fresh scope
        # per call) rather than closing directly over the loop variable
        # below, which would otherwise let every job share the LAST
        # agentbot iterated.
        async def _cb() -> None:
            await _run_scheduled_agentbot(agentbot, cache=cache, run_agentbot=run_agentbot)
        return _cb

    for agentbot_id, agentbot in scheduled.items():
        trigger = agentbot.get("trigger") or {}
        job_id = f"{_AGENTBOT_JOB_PREFIX}{agentbot_id}"
        cron = trigger.get("cron")
        interval_min = trigger.get("interval_min")
        try:
            if cron:
                trigger = CronTrigger.from_crontab(_to_apscheduler_crontab(cron))
                scheduler.add_job(
                    _make_callback(agentbot), trigger=trigger, id=job_id,
                    replace_existing=True, misfire_grace_time=3600)
            elif interval_min:
                scheduler.add_job(
                    _make_callback(agentbot), trigger="interval", minutes=interval_min,
                    id=job_id, replace_existing=True, misfire_grace_time=3600)
            else:
                # Neither cron nor interval_min -- shouldn't happen for a
                # store-validated Agentbot (XOR enforced at validation
                # time), but skip defensively rather than register a no-op
                # job.
                continue
        except Exception:
            # A shape-valid but value-invalid cron (e.g. hour=99) surfaces
            # here as APScheduler's own ValueError at add_job time -- one
            # broken Agentbot's schedule must never crash registration for
            # the rest.
            logger.warning("register_agentbot_schedules: failed to schedule agentbot %s, skipping", agentbot_id, exc_info=True)
            continue


# ── Agenti v1.1 Fase 2 Task 5: bound PER ESECUZIONE ────────────────────────
# `perimeter.budget_tokens` e `perimeter.deadline_min` (validati e
# materializzati da `watcher.agentbots._validate_perimeter`, default 4096
# token e 5 minuti) limitano UNA SINGOLA esecuzione di ragionamento di un
# agente in modalita' obiettivo -- che dal Task 4 gira da sola, su
# pianificazione, senza nessuno a guardarla. NON sono contatori cumulativi: il
# cap giornaliero della sentinella (`wake.maybe_wake`) e i totali in
# `usage.json` misurano un'altra cosa e restano invariati.
#
# Sforare non e' un errore: e' un ESITO. L'esecuzione si ferma PRIMA di
# eseguire la Decision e lascia una riga dove questo percorso registra gia'
# ogni suo esito (`_record_situation_event` -> `sentinel_store.record_event`
# -> `/api/sentinel/timeline`, servita da `api/handlers_sentinel.
# handle_sentinel_timeline`), con `outcome` che dice che e' stata interrotta e
# `message` che dice perche' -- i due campi che la lista eventi dell'editor
# agentbot mostra all'utente (`static/config/agentbot-editor.js`, che chiama
# proprio quella rotta).
AGENT_RUN_STOP_BUDGET = "interrotto:budget"
AGENT_RUN_STOP_DEADLINE = "interrotto:scadenza"


def _reasoning_runner(app: web.Application):
    """L'oggetto a cui il percorso di ragionamento parla davvero: il router
    LLM, o -- se non c'e' -- il ClaudeRunner dell'engine.

    UNICA regola di risoluzione, condivisa da chi FA la chiamata
    (`_llm_reason`) e da chi ne misura il costo (il bound per esecuzione):
    due copie della stessa regola potrebbero finire a guardare due oggetti
    diversi, e il budget misurerebbe i token di qualcun altro."""
    runner = app.get("llm_router")
    if runner is None:
        eng = app.get("engine")
        runner = getattr(eng, "_claude_runner", None) if eng is not None else None
    return runner


def agent_run_bound(perimeter: dict | None) -> tuple[int | None, float | None]:
    """`(budget_tokens, deadline_sec)` per UNA esecuzione di ragionamento.

    `perimeter is None` -- ogni Agentbot `mode="rule"` (il validatore gli
    VIETA il blocco) e ogni chiamante built-in del percorso (guardiano,
    situazioni, olistico, ronda) -- significa "nessun bound": stessa
    esecuzione di prima di questo task, senza misure e senza scadenza.

    I due valori sono gia' stati validati da `_validate_perimeter`;
    ricontrollarli con lo STESSO `is_positive_int` non e' una seconda
    validazione ma un fail-safe di lettura -- un perimetro che arrivasse da
    altrove (un file scritto a mano, un test) con un valore non conforme vale
    "non dichiarato" = nessun bound, non un bound assurdo. I minuti diventano
    secondi qui, una volta sola."""
    if not perimeter:
        return (None, None)
    budget_tokens = perimeter.get("budget_tokens")
    deadline_min = perimeter.get("deadline_min")
    return (
        budget_tokens if is_positive_int(budget_tokens) else None,
        deadline_min * 60.0 if is_positive_int(deadline_min) else None,
    )


def agent_run_deadline(deadline_sec: float | None):
    """Il contesto `async with` che limita la DURATA di una esecuzione di
    ragionamento; `None` -> contesto inerte (nessuna scadenza).

    `asyncio.timeout` e non `asyncio.wait_for`: `wait_for` avvolge la
    coroutine in un Task NUOVO, che riceve una COPIA del contesto, e le
    ContextVar per-chiamata del runner (tool calls / thinking) diventerebbero
    invisibili a chi chiama. Stesso motivo per cui il timeout per-run del
    Chatbot usa `asyncio.timeout` (`chatbot_engine.py`, `_CHATBOT_RUN_TIMEOUT`)."""
    if deadline_sec is None:
        return contextlib.nullcontext()
    return asyncio.timeout(deadline_sec)


def agent_run_usage(runner, agent_id: str | None) -> tuple[int, int] | None:
    """UNA lettura dei contatori per-agente: `(token, richieste)`, o `None`
    quando non c'e' proprio nulla da leggere.

    Non sono contatori nuovi: sono gli stessi per-agente che `ClaudeRunner.chat`
    (`claude_runner.py`) e `OpenAICompatRunner` incrementano e che `LLMRouter`
    aggrega sui backend (`llm_router.get_chatbot_usage`). Il consumo di una
    singola esecuzione e' la differenza fra due letture attorno alla chiamata
    -- la stessa tecnica con cui `chatbot_engine` misura il costo di un run.
    Poiche' i contatori avanzano a ogni risposta, la misura copre l'intero
    giro agentico (piu' turni di tool use), non solo l'ultimo.

    Le RICHIESTE vengono lette insieme ai token perche' da sole dicono se una
    chiamata e' stata davvero attribuita a questo agente: entrambi i runner le
    incrementano all'INGRESSO della chiamata, prima di sapere cosa rispondera'
    il modello (`claude_runner.chat`, `openai_compat_runner.chat` -- e quindi
    anche `run_with_actions`, che passa da `chat`). I token invece dipendono
    da cosa la risposta riporta. Vedi `agent_run_tokens_spent`.

    L'attribuzione per-agente esiste perche' `_llm_reason` passa gia'
    `chatbot_id=agent_id` al runner (Task 3). Senza identita' -- ogni
    chiamante built-in, ogni regola -- non c'e' nulla da attribuire e questa
    funzione restituisce `None` = "nessuna misura", che chi chiama tratta come
    "nessun bound sul budget", MAI come "budget esaurito"."""
    if runner is None or not agent_id:
        return None
    get_usage = getattr(runner, "get_chatbot_usage", None)
    if get_usage is None:
        return None
    try:
        usage = get_usage(agent_id) or {}
        return (
            int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0)),
            int(usage.get("requests", 0)),
        )
    except Exception:
        # La misura e' un limite, non una funzionalita': se il backend non sa
        # rispondere si perde il bound sul budget (resta la scadenza), non
        # l'esecuzione.
        logger.debug("agent_run_usage(%s): misura non disponibile", agent_id, exc_info=True)
        return None


# Un tetto che non puo' misurare deve DIRLO -- ma una volta, non a ogni giro:
# questo percorso gira su pianificazione, e un warning per esecuzione
# diventerebbe rumore che nessuno legge piu'. Insieme per agente, perche' il
# backend che misura puo' essere diverso da agente ad agente (`model` per
# Agentbot -> backend diverso in `LLMRouter`) e il silenzio di uno non deve
# nascondere il silenzio di un altro.
_AGENT_UNMEASURED_WARNED: set[str] = set()


def _warn_agent_unmeasured(agent_id: str | None, reason: str) -> None:
    """Emette IL warning una-tantum per agente (vedi `_AGENT_UNMEASURED_WARNED`
    sopra) con un `reason` leggibile che dice PERCHE' la misura e' fallita.

    Estratto da `agent_run_tokens_spent` cosi' che i due rami che quella
    funzione copriva -- "richieste ferme" (misura c'e' ma non attribuita) -- e
    i due rami muti chiusi dal fix successivo -- "prima lettura assente" e
    "seconda lettura assente" (la misura stessa non esiste) -- condividano lo
    STESSO stato globale e la STESSA soglia una-per-agente, invece di avere
    ciascuno il proprio silenzio o il proprio contatore duplicato."""
    key = agent_id or "?"
    if key in _AGENT_UNMEASURED_WARNED:
        return
    _AGENT_UNMEASURED_WARNED.add(key)
    logger.warning(
        "agentbot %s: %s -- il consumo non e' misurabile, quindi il budget "
        "per esecuzione NON e' stato applicato e questa esecuzione ha girato "
        "senza tetto sui token. Resta la scadenza (deadline_min). Avviso "
        "emesso una sola volta per agente.", key, reason)


def agent_run_tokens_spent(
    before: tuple[int, int] | None, after: tuple[int, int] | None,
    agent_id: str | None,
) -> int | None:
    """Token spesi DA questa esecuzione (differenza fra due `agent_run_usage`),
    oppure `None` = "non misurabile" -> nessun bound sul budget.

    Il caso che questa funzione esiste per distinguere: un delta di ZERO token
    puo' voler dire due cose OPPOSTE. "Giro economico misurato" (legittimo: il
    bound resta in piedi, nessun rumore) oppure "non abbiamo misurato niente"
    -- e in quel secondo caso `0 > budget_tokens` non sara' mai vero e
    l'agente girerebbe senza alcun tetto, senza che nulla lo dica. Il
    contatore delle RICHIESTE separa i due: avanza all'ingresso di ogni
    chiamata attribuita a questo agente, su entrambi i runner, prima e
    indipendentemente da cosa la risposta riportera'. Richieste ferme
    attraverso l'esecuzione = nessuna chiamata e' stata attribuita a questo
    agente (identita' non propagata al runner, runner risolto diverso da
    quello che ha davvero chiamato, backend senza contabilita' per-agente):
    la lettura dei token e' un tetto solo apparente.

    `before is None` (prima lettura fallita, il chiamante ora ci arriva
    comunque -- vedi `_budget_tokens is not None` in `_run_decision`) o
    `after is None` (`agent_run_usage` e' fallita la SECONDA volta, a
    ragionamento gia' concluso) sono lo stesso caso di fondo: i contatori
    stessi non si leggono, non solo "non sono avanzati". Anche qui fail-open
    con lo stesso warning una-tantum, motivo diverso perche' chi legge il log
    capisca che il problema e' la lettura, non l'attribuzione.

    LIMITE NOTO, dichiarato invece che promesso (come `max_tier`): un backend
    che RISPONDE senza oggetto `usage` fa avanzare le richieste ma non i token
    (`OpenAICompatRunner._track_usage` esce subito, "token tracking skipped"),
    e per questa funzione e' indistinguibile da un giro economico -- il tetto
    sui token non scatta. Distinguerlo richiederebbe un contatore che i runner
    incrementino DENTRO `_track_usage` (cioe' solo quando la misura c'e'
    davvero): cambiare la forma di `per_agent` in `usage.json` non e' materia
    di questo fix. Resta la scadenza, che non dipende da nessuna misura.

    Resta il fail-open gia' scelto (non misurabile -> nessun bound, non
    "budget esaurito"): un tetto che non sa contare non deve fermare un agente.
    Ma diventa VISIBILE, con un `logger.warning`."""
    if before is None or after is None:
        _warn_agent_unmeasured(
            agent_id,
            "i contatori richieste/token per questo agente non sono "
            "leggibili (lettura fallita prima o dopo l'esecuzione)")
        return None
    tokens = after[0] - before[0]
    requests = after[1] - before[1]
    if requests > 0:
        # Misurato. Zero token qui e' un legittimo giro economico.
        return tokens
    _warn_agent_unmeasured(
        agent_id,
        "nessuna chiamata LLM risulta attribuita a questo agente (contatore "
        "richieste fermo attraverso l'esecuzione)")
    return None


def agent_run_stopped(why: str, severity: str | None) -> Decision:
    """L'esito di un'esecuzione FERMATA dal bound per esecuzione.

    E' una `Decision` perche' e' cio' che `_record_situation_event` sa
    registrare, ma non e' un giudizio del ragionatore: `verdict="interrotto"`
    la distingue da "anomalia"/"falso_positivo", e `action=None` fa si' che --
    anche se un domani un refactoring la facesse arrivare per sbaglio in
    `executor.execute()` -- non possa attuare nulla."""
    return Decision(verdict="interrotto", severity=severity or "info",
                    message=f"Esecuzione interrotta: {why}", action=None)


async def _reason_memory_context(
    app: web.Application, embedder, wake, friendly_name: str,
) -> list[str]:
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
    malformed `wake` could -- so this is wrapped too, degrading to []
    rather than ever bubbling an exception into `_gather_context`.
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
        return []


async def run_daily_briefing(app, *, today, llm_reason, notify) -> str | None:
    """Slice 7 (Maggiordomo) Task 4: the consolidated daily butler briefing
    job, replacing the old per-obligation spam (`hiris_due_reminders` /
    `_notify_due_obligations`, one notification per due obligation, no
    dedup) with ONE grounded resoconto per day.

    Module-level (not inlined in `_on_startup`) so it's unit-testable with a
    plain dict standing in for `app` -- same convention as
    `_reason_memory_context` above; `app` only needs `.get("knowledge_store")`,
    `.get("entity_cache")`, `.get("llm_router")` and `.get("data_dir")`.

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
            load_policy(app.get("data_dir")),
            today=today, allow_sensitive=allow_sensitive,
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


async def _run_internal_mcp(server) -> None:
    """Run the internal MCP server, containing a bind/startup failure to this
    optional feature instead of letting SystemExit kill the whole addon.

    uvicorn.Server.serve() calls sys.exit() when it can't bind its port (e.g.
    INTERNAL_MCP_PORT already in use). Since this task is scheduled on the
    SAME asyncio loop as the aiohttp app (see _on_startup below), an
    unwrapped SystemExit would propagate through that shared loop and take
    down the entire HIRIS process over what should be an optional, isolated
    feature. Module-level (not inlined in _on_startup) so tests can exercise
    the containment directly without booting the whole app.
    """
    try:
        await server.serve()
    except SystemExit as exc:
        logger.error("Internal MCP server non avviato (porta occupata?): %s", exc)
    except Exception:
        logger.exception("Internal MCP server terminato con errore")


class _EmbeddedMCPServer(uvicorn.Server):
    """uvicorn.Server subclass for the embedded internal MCP server.

    install_signal_handlers() is a no-op here: the internal MCP server runs
    as a background asyncio task on the SAME event loop/process as the
    aiohttp addon (see _on_startup/_on_cleanup below). uvicorn.Server.serve()
    normally calls install_signal_handlers() and replaces the process-wide
    SIGTERM/SIGINT handlers for the whole lifetime of the process -- that
    would hijack the addon's own shutdown signals. The aiohttp app + s6 own
    process shutdown; this task's cleanup is already driven by _on_cleanup
    cancelling internal_mcp_task, so the embedded uvicorn must never touch
    process signals.
    """

    def install_signal_handlers(self) -> None:
        return


def build_internal_mcp_server(*, hiris_base_url: str = "http://127.0.0.1:8099"):
    """Costruisce (client, uvicorn.Config, guard) per il server MCP interno su
    loopback. Isolato dall'avvio dell'app cosi' e' testabile senza bootare
    tutto.

    I-2 partial (Plan 2B final review, fast-follow): also returns `guard` so
    callers can reach it -- previously `McpGuard()` was built here and handed
    straight to `build_mcp`, with no reference kept anywhere else, so nothing
    outside this function could ever inspect its audit trail or flip its
    kill-switch. `_on_startup` below stores it on `app["mcp_guard"]`. No HTTP
    endpoint/UI is added here (that remains a later gate) -- this only makes
    the guard reachable in-process."""
    from .mcp.guard import McpGuard
    from .mcp.local_client import LocalExecuteClient
    from .mcp.server import build_mcp, make_asgi_app
    port = int(os.environ.get("INTERNAL_MCP_PORT", "8199"))
    token = os.environ.get("INTERNAL_TOKEN", "")
    client = LocalExecuteClient(hiris_base_url, token)
    guard = McpGuard()
    asgi = make_asgi_app(build_mcp(client, guard))
    config = uvicorn.Config(asgi, host="127.0.0.1", port=port, log_level="warning")
    return client, config, guard


def should_start_agent_worker() -> bool:
    """Gate worker chat-via-abbonamento in-addon (SP-2): attivo quando
    l'abbonamento è attivo (provider_subscription, o il legacy
    chat_via_subscription) E un token OAuth è presente."""
    sub_on = (
        env_bool("PROVIDER_SUBSCRIPTION")
        or env_bool("CHAT_VIA_SUBSCRIPTION")
    )
    return sub_on and bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip())


async def _on_startup(app: web.Application) -> None:
    from .claude_runner import ClaudeRunner, RunnerBackendError
    from .proxy.semantic_map import SemanticMap
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
    from .api.handlers_execute import parse_execute_policy
    app["execute_policy"] = parse_execute_policy(
        tools=os.environ.get("EXECUTE_API_TOOLS", ""),
        entities=os.environ.get("EXECUTE_API_ENTITIES", ""),
        services=os.environ.get("EXECUTE_API_SERVICES", ""),
    )
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
    # If the user manages the gateway policy from the UI, it overrides the env CSV.
    from .api.handlers_gateway_policy import apply_saved_policy
    apply_saved_policy(app)
    # Yellow approval: route iPhone notification-action button taps to approve/reject.
    # review C/#15: this is the approval-critical listener -- go through
    # _spawn() (strong ref) so a phone-tap Approve/Reject can't be silently
    # dropped by GC mid-flight.
    from .api.handlers_gateway_pending import on_notification_action
    ha_client.add_action_listener(
        lambda ev: _spawn(on_notification_action(app, ev), name="notification_action")
    )

    # Build semantic map
    semantic_map = SemanticMap(data_dir=data_dir)
    semantic_map.load()
    ambiguous = semantic_map.build_from_cache(entity_cache)
    app["semantic_map"] = semantic_map
    ha_client.add_registry_listener(semantic_map.on_entity_added)

    engine = ChatbotEngine(ha_client=ha_client, data_path=data_path)
    engine.set_entity_cache(entity_cache)
    await engine.start()
    app["engine"] = engine

    health_monitor = HealthMonitor(
        ha_client=ha_client,
        data_path=os.path.join(data_dir, "ha_health.json"),
        scheduler=engine._scheduler,
    )
    await health_monitor.start()
    app["health_monitor"] = health_monitor

    proposal_store = ProposalStore(
        db_path=os.path.join(data_dir, "proposals.db"),
        scheduler=engine._scheduler,
    )
    app["proposal_store"] = proposal_store

    knowledge_db = KnowledgeDB(
        db_path=os.path.join(data_dir, "home_map.db")
    )
    app["knowledge_db"] = knowledge_db

    context_map = SemanticContextMap(
        cache_path=os.path.join(data_dir, "semantic_context_map.json")
    )
    context_map.load()
    context_map.build(entity_cache, knowledge_db=knowledge_db)
    app["context_map"] = context_map
    logger.info("SemanticContextMap ready")

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
    # (ha_push) e da handlers_gateway_pending (pending step-up).
    _slug = await _fetch_addon_slug(os.environ.get("SUPERVISOR_TOKEN", ""))
    _ingress_click_path = f"/hassio/ingress/{_slug}" if _slug else None
    notify_config["ingress_click_path"] = _ingress_click_path
    app["ingress_click_path"] = _ingress_click_path
    app["theme"] = os.environ.get("THEME", "auto")

    tasks_data_path = os.environ.get("TASKS_DATA_PATH", "/data/tasks.json")
    _agent_owner = os.environ.get("AGENT_OWNER", "").strip()
    task_engine = TaskEngine(
        ha_client=ha_client,
        entity_cache=entity_cache,
        notify_config=notify_config,
        data_path=tasks_data_path,
        execute_policy=app["execute_policy"],
        request_stepup=_make_task_stepup(app=app, data_dir=app["data_dir"], owner=_agent_owner),
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
    # (_holistic_reason, _reasoning_sweep, il wiring di chat_via_subscription
    # poco più in basso), così ognuno di quei tre punti vede l'abbonamento
    # senza duplicare il parsing env. Vedi task-3-report.md per il grep
    # BRIDGE_ENABLED che ha individuato tutti e tre i gate.
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
    _mem_ret_raw = os.environ.get("MEMORY_RETENTION_DAYS", "90")
    memory_retention_days: int | None = None if _mem_ret_raw == "0" else int(_mem_ret_raw)

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

    # Daily retention job (chat messages + expired memories)
    from .chat_store import delete_old_messages as _delete_old_messages

    def _run_retention() -> None:
        from .chat_store import HISTORY_RETENTION_DAYS
        if HISTORY_RETENTION_DAYS > 0:
            n = _delete_old_messages(data_dir, HISTORY_RETENTION_DAYS)
            if n:
                logger.info("Retention: deleted %d old chat messages", n)
        n2 = knowledge_store.purge_expired_chatbot()
        if n2:
            logger.info("Retention: purged %d expired chatbot memories", n2)

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

    from .tools.dispatcher import ToolDispatcher
    from .backends.openai_compat_runner import OpenAICompatRunner
    from .backends.openrouter_runner import OpenRouterRunner
    # Thin wrapper binding the module-level request_confirmation_stepup to
    # this app instance; see request_confirmation_stepup for the actual
    # no-identity guard and yellow/red actionable logic.
    async def _request_confirmation(*, tool, inputs, tier, user):
        return await request_confirmation_stepup(
            app, data_dir, tool=tool, inputs=inputs, tier=tier, user=user,
        )

    # Thin wrapper binding the module-level confirm_pending_execute to this
    # app instance; see confirm_pending_execute for the actual 6-digit gate
    # and pending-execution logic.
    async def _confirm_executor(*, code, user):
        return await confirm_pending_execute(app, code=code, user=user)

    dispatcher = ToolDispatcher(
        ha_client=ha_client,
        notify_config=notify_config,
        entity_cache=entity_cache,
        semantic_map=semantic_map,
        embedding_provider=embedder,
        memory_retention_days=memory_retention_days,
        health_monitor=health_monitor,
        proposal_store=proposal_store,
        knowledge_store=knowledge_store,
        embedder=embedder,
        pseudonymizer=pseudonymizer,
        history_store=history_store,
        execute_policy=app["execute_policy"],
        request_confirmation=_request_confirmation,
        confirm_executor=_confirm_executor,
        data_dir=data_dir,
    )
    dispatcher.set_task_engine(task_engine)
    app["tool_dispatcher"] = dispatcher

    # ── Sentinella (cervello proattivo, fetta 1) ──────────────────────────
    # Shares the SAME semaforo (execute_policy tiers) as the execute-API/gateway
    # — the single source of truth for what the AI is allowed to actuate.
    from .watcher.sentinel_store import SentinelStore
    from .watcher.guardian import Guardian
    from .watcher.policy import load_policy
    from .watcher.reasoner import reason, SENTINEL_SYSTEM, SITUATION_HOLISTIC_SYSTEM
    from .watcher.executor import execute
    from .watcher.off_task import build_off_task
    from .watcher.signals import WakeEvent
    from .tools.notify_tools import send_notification
    from .tools.proposal_tools import create_automation_proposal
    import time as _time
    from datetime import datetime as _dt

    sentinel_store = SentinelStore(os.path.join(data_dir, "sentinel.db"))
    app["sentinel_store"] = sentinel_store

    from .brain.suggestions import SuggestionStore
    suggestion_store = SuggestionStore(os.path.join(data_dir, "suggestions.db"))
    app["suggestion_store"] = suggestion_store

    from .brain.reasoning_log import ReasoningLog
    from .brain.advisory_store import AdvisoryStore
    reasoning_log = ReasoningLog(os.path.join(data_dir, "brain_reasoning.db"))
    app["reasoning_log"] = reasoning_log
    advisory_store = AdvisoryStore(os.path.join(data_dir, "advisory.db"))
    app["advisory_store"] = advisory_store

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
            return {"friendly_name": wake.entity_id}

        # Slice 6b Task 4: bounded, egress-gated memory recall added on top.
        # _reason_memory_context is itself failure-safe (never raises), but
        # this call is never allowed to prevent returning at least
        # {"friendly_name": ...} exactly like before Task 4.
        try:
            mem = await _reason_memory_context(app, embedder, wake, friendly_name)
        except Exception:
            return {"friendly_name": friendly_name}
        return {"friendly_name": friendly_name, "memory": mem}

    async def _llm_reason(system, user, *, model, max_tokens,
                          agent_id=None, allowed_entities=None, allowed_services=None):
        # allowed_tools=[] is falsy -> narrowing is SKIPPED (claude_runner.py:894-896):
        # this reasoning call receives every EVALUATION_ONLY_TOOLS entry
        # (claude_runner.py:210-222), create_task included -- NOT zero tools. The
        # real invariant is that set excludes the tools that ACT (call_ha_service,
        # send_notification, trigger_automation, toggle_automation, http_request).
        # The executor below is the only thing that acts, gated by the semaforo.
        #
        # Agenti v1.1 Fase 2 Task 3: `agent_id` + `allowed_entities`/
        # `allowed_services` are the reasoning agent's IDENTITY and PERIMETER.
        # They are `None` for every built-in sentinel caller (guardian wakes,
        # situations, holistic, briefing, coverage review) -- those keep the
        # exact anonymous/unscoped call they always made. Only an Agentbot
        # that HAS a perimeter block (i.e. mode="objective", see
        # `watcher/agentbot_runner.py`) supplies them, via `_run_decision`.
        # `chatbot_id` is the runner-side name of that identity: the tool
        # dispatcher already renames it back to `agent_id` when it stamps a
        # freshly created Task (`tools/dispatcher.py`, create_task branch),
        # so passing it here is what makes an emitted Task belong to the
        # agent that emitted it instead of to "hiris-default". The two
        # allow-lists ride the SAME dispatcher parameters, ending up on the
        # Task itself -- where `task_engine._run_action`'s ALREADY EXISTING
        # check enforces them at execution time. Nothing new enforces
        # anything here.
        # Fase 2 Task 5: la risoluzione del runner e' passata nel
        # module-level `_reasoning_runner(app)` perche' ora la usa anche il
        # bound per esecuzione, che deve misurare i token PROPRIO
        # sull'oggetto che ha servito questa chiamata. Comportamento
        # identico a prima (llm_router, poi engine._claude_runner).
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

    async def _act(action):
        # Dispatched through the normal tool dispatcher (call_ha_service), same
        # code path as every other actuation. Primary enforcement (tier gate +
        # dangerous-domain denylist) already happened upstream in
        # executor.execute() — this only ever runs for a green, non-dangerous
        # action. As defense-in-depth, also pass a per-call allowlist scoped
        # to exactly this action's domain.service and entity_id, so the
        # dispatcher's own allowlist check (otherwise inert here) is a second,
        # independent layer instead of a no-op.
        #
        # Action-shape fix: Decision.action carries entity_id as a top-level
        # sibling of "data" (see reasoner.py's SENTINEL_SYSTEM contract), but
        # ToolDispatcher.dispatch's call_ha_service branch reads the target
        # entity from INSIDE inputs["data"]/inputs["target"]
        # (dispatcher.py:213-224) and forwards inputs["data"] verbatim to
        # self._ha.call_service(domain, service, data). Copy entity_id into
        # data so the actuation actually reaches HA with a target, and so the
        # allowed_entities check below (which also reads from data/target)
        # has something to match against instead of always failing closed.
        domain = action.get("domain") or action["entity_id"].split(".", 1)[0]
        service = action.get("service", "")
        eid = action.get("entity_id")
        data = dict(action.get("data") or {})
        if eid:
            data["entity_id"] = eid
        await dispatcher.dispatch(
            "call_ha_service", {"domain": domain, "service": service, "data": data},
            allowed_services=[f"{domain}.{service}"] if service else None,
            allowed_entities=[eid] if eid else None,
        )
        # Irrigation-style actions (turn_on with off_after_min) get a matching
        # delayed turn_off scheduled through the TaskEngine. build_off_task()
        # already refuses to build anything unless service=="turn_on" and
        # off_after_min is a positive number, so this is a no-op for every
        # other action. create_task's own allowlist (below) scopes the
        # scheduled task to exactly this domain.turn_off + entity_id — same
        # defense-in-depth pattern as the turn_on dispatch above.
        if action.get("off_after_min"):
            off = build_off_task(action)
            if off is not None:
                await dispatcher.dispatch(
                    "create_task", off,
                    allowed_services=[f"{domain}.turn_off"],
                    allowed_entities=[eid] if eid else None,
                )

    async def _propose(decision, wake):
        await create_automation_proposal(
            proposal_store, proposal_type="ha_automation",
            name=f"Sentinella: {wake.signal_kind} {wake.entity_id}",
            description=decision.message,
            config={"suggested_action": decision.action},
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
                notify=_notify, act=_act, propose=_propose,
                allow_green_auto=env_bool("SENTINEL_ALLOW_GREEN_AUTO"))
        except Exception:
            logger.exception("sentinel on_wake failed")
            outcome = "error"
        sentinel_store.record_event({
            "ts": _time.time(), "kind": wake.signal_kind, "entity_id": wake.entity_id,
            "verdict": getattr(decision, "verdict", None), "severity": wake.severity_hint,
            "outcome": outcome, "message": getattr(decision, "message", "")})

    # Slice 5b / Task 4: EVENT-triggered user Agentbots (renamed from "lens"
    # in SP-4 Fase A Task 3), dispatched by the SAME Guardian.on_state_changed
    # alongside (not instead of) the built-in DETECTORS above.
    # `get_user_agentbots` reads the in-memory Agentbot cache (Task 6,
    # `handlers_agentbots.set_agentbots`/`get_event_agentbots` -- SP-4 Fase A
    # Task 4 of the rename plan) instead of re-reading+re-validating
    # agentbots.json on every single state_changed event (Task 4 review
    # finding). The cache is populated right here from the current disk
    # contents, and refreshed after every CRUD mutation by the
    # `/api/agentbots` handlers -- so freshly-saved Agentbots are still
    # live without a restart, just without the per-event disk hit.
    from .watcher.agentbots import load_agentbots as _load_agentbots
    from .api.handlers_agentbots import set_agentbots as _set_agentbots_cache
    from .api.handlers_agentbots import get_event_agentbots as _get_event_agentbots_cache

    _set_agentbots_cache(app, _load_agentbots(data_dir))

    def _get_event_agentbots() -> list:
        return _get_event_agentbots_cache(app)

    async def _dispatch_run_agentbot(agentbot: dict, evidence: dict) -> str:
        return await app["run_agentbot"](agentbot, evidence)

    guardian = Guardian(
        sentinel_store, lambda: load_policy(data_dir), _on_wake,
        cooldown_sec=int(os.environ.get("SENTINEL_COOLDOWN_SEC", "1800")),
        daily_cap=int(os.environ.get("SENTINEL_DAILY_CAP", "20")),
        get_user_agentbots=_get_event_agentbots,
        run_agentbot=_dispatch_run_agentbot)
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

    # ── Situazioni (ronda periodica + revisione olistica, fetta 2) ──────────
    # Same semaforo (execute_policy) and same Fetta-1 adapters (_gather_context,
    # _llm_reason, _notify, _act, _propose) as the guardian above — situations
    # are just another wake source feeding the identical reason→execute path.
    from .watcher.snapshot import build_snapshot as _build_snapshot
    from .watcher.evaluator import SituationEvaluator
    from .tools.weather_tools import get_weather_forecast

    _snap_deps = {
        "get_states": lambda ids: ha_client.get_states(ids),
        "get_weather": lambda: get_weather_forecast(hours=6),
        "get_health": (lambda: health_monitor.get_snapshot(["all"])) if health_monitor is not None else (lambda: None),
    }

    async def _snapshot():
        return await _build_snapshot(_snap_deps, load_policy(data_dir).get("situations", {}))

    async def _record_situation_event(kind, entity_id, decision, outcome):
        sentinel_store.record_event({
            "ts": _time.time(), "kind": kind, "entity_id": entity_id,
            "verdict": getattr(decision, "verdict", None), "severity": getattr(decision, "severity", None),
            "outcome": outcome, "message": getattr(decision, "message", "")})

    async def _run_decision(wake, suggested, system, force_notify_only=False, model="auto",
                            agent_id=None, perimeter=None):
        # Task 4B: `model` lets a per-Agentbot `reasoning.model` (threaded in
        # by `watcher/agentbot_runner.py`'s `_on_wake`) pick its OWN model for
        # this single reason() call. Callers that don't pass it (the
        # built-in situations path, `_on_situation`/holistic below -- Task
        # 4's brain path, UNCHANGED) keep the "auto" default, exactly as
        # before.
        #
        # Agenti v1.1 Fase 2 Task 3: `agent_id` + `perimeter` arrive TOGETHER
        # or not at all -- `watcher/agentbot_runner.py` only sends them for an
        # Agentbot that HAS a perimeter block, which `validate_agentbot`
        # materializes for mode="objective" and forbids for mode="rule". So
        # every pre-existing caller (rule Agentbots, situations, holistic,
        # the fallback sweep) lands here with both `None` and reasons exactly
        # as before: anonymous, unscoped, same `reason()` call as ever.
        #
        # `reason()`'s contract with `llm_reason` (system, user, model,
        # max_tokens) is deliberately left untouched: the identity/perimeter
        # are BOUND onto the callable here instead of being threaded through
        # `reason()`, which has no business knowing about agents.
        llm_reason = _llm_reason
        if perimeter is not None:
            # The lists are passed through VERBATIM, `None` and empty
            # included -- NO normalization in either direction. The whole
            # chain (`tools/dispatcher.py` -> Task ->
            # `task_engine._run_action`) agrees on one semantics:
            # `None` = "no boundary on this axis", `[]` = "nothing granted".
            # `validate_agentbot` already materializes the perimeter with
            # `None` for an axis the user left undeclared, so an `or []`
            # here would turn "no limits" into "deny everything" -- and a
            # `or None` would do the exact opposite. Both are silent
            # semantic changes; copying the list is all that's allowed.
            _ae = perimeter.get("allowed_entities")
            _as = perimeter.get("allowed_services")
            _allowed_entities = list(_ae) if _ae is not None else None
            _allowed_services = list(_as) if _as is not None else None

            async def llm_reason(system, user, *, model, max_tokens):
                # `system`/`user` deliberately shadow the enclosing
                # `_run_decision` locals of the same name: this closure
                # replaces `_llm_reason` in `reason()`'s eyes, so its
                # signature must MATCH `_llm_reason`'s parameter names
                # rather than diverge from them (review, minor #4 -- the
                # old `_system`/`_user` only worked because every caller
                # happened to pass positionally).
                return await _llm_reason(
                    system, user, model=model, max_tokens=max_tokens,
                    agent_id=agent_id,
                    allowed_entities=_allowed_entities,
                    allowed_services=_allowed_services)

        # Agenti v1.1 Fase 2 Task 5: bound PER ESECUZIONE (vedi
        # `agent_run_bound` & co. a livello di modulo). Senza perimetro --
        # regole e chiamanti built-in -- `agent_run_bound` restituisce
        # `(None, None)`: nessuna misura dei token, contesto di scadenza
        # inerte, stessa identica chiamata di prima.
        _budget_tokens, _deadline_sec = agent_run_bound(perimeter)
        # Lo STESSO oggetto runner per le due letture: risolverlo due volte
        # rischierebbe di misurare la differenza fra i contatori di due
        # backend diversi se il router venisse sostituito nel frattempo.
        #
        # ASSUNZIONE (review Task 5, minor #4): i contatori per-agente sono
        # CUMULATIVI e condivisi, quindi la differenza fra due letture e' il
        # consumo di questa esecuzione solo se non ce n'e' un'altra dello
        # STESSO agente in volo nello stesso momento (si attribuirebbero i
        # token a vicenda: la piu' lenta pagherebbe anche per la piu' veloce).
        # Oggi non succede -- un agente in modalita' obiettivo non e'
        # event-triggered (Task 4: solo pianificazione) e il suo callback
        # `_run_scheduled_agentbot` e' awaited inline sotto `max_instances=1`
        # di APScheduler, che non ne fa partire una seconda finche' la prima
        # non e' finita. Se un domani gli obiettivi diventassero anche
        # event-triggered, o il callback smettesse di essere serializzato,
        # questa misura andrebbe resa per-esecuzione (un contatore passato
        # dentro alla chiamata) invece che per differenza.
        _runner = _reasoning_runner(app) if _budget_tokens is not None else None
        _usage_before = agent_run_usage(_runner, agent_id)
        _deadline = agent_run_deadline(_deadline_sec)
        try:
            async with _deadline:
                decision = await reason(wake, gather_context=_gather_context, llm_reason=llm_reason, system=system, model=model)
        except TimeoutError:
            # Solo la NOSTRA scadenza si ferma qui. `expired()` distingue il
            # nostro timeout da un TimeoutError nato piu' in basso (una
            # richiesta HTTP verso l'LLM, per dire), che deve continuare a
            # risalire esattamente come ha sempre fatto: senza questo
            # controllo il bound assorbirebbe in silenzio errori altrui e li
            # racconterebbe come "scadenza superata".
            if _deadline_sec is None or not _deadline.expired():
                raise
            await _record_situation_event(
                wake.signal_kind, wake.entity_id,
                agent_run_stopped(
                    f"superata la scadenza di {_deadline_sec / 60:g} min per questa esecuzione",
                    wake.severity_hint),
                AGENT_RUN_STOP_DEADLINE)
            return
        if _budget_tokens is not None:
            # Cancello su `_budget_tokens`, NON su `_usage_before`: quando non
            # c'e' bound (`_budget_tokens is None` -- mode="rule", o objective
            # senza perimetro) questo blocco resta zitto esattamente come
            # prima, nessun warning. Quando invece un bound e' stato
            # richiesto, vogliamo arrivare ad `agent_run_tokens_spent` anche
            # se la PRIMA lettura (`_usage_before`) e' gia' fallita -- prima
            # di questo fix quel caso saltava il blocco intero (nessun
            # warning, solo il `logger.debug` di `agent_run_usage`).
            # `agent_run_tokens_spent` restituisce `None` quando la misura non
            # e' avvenuta (prima o seconda lettura assente, oppure nessuna
            # chiamata risulta attribuita a questo agente): fail-open, nessun
            # bound -- ma con un warning, non in silenzio. Un delta di zero
            # token MISURATO resta invece un giro economico e non ferma nulla.
            _tokens_run = agent_run_tokens_spent(
                _usage_before, agent_run_usage(_runner, agent_id), agent_id)
            if _tokens_run is not None and _tokens_run > _budget_tokens:
                # Il ragionamento ha gia' risposto, ma e' costato piu' del
                # concesso: la sua Decision NON viene eseguita (niente
                # notifica, niente attuazione, niente proposta) e al suo
                # posto resta il motivo. La domanda all'80% del budget e il
                # resoconto strutturato sono Fase 3, non qui.
                await _record_situation_event(
                    wake.signal_kind, wake.entity_id,
                    agent_run_stopped(
                        f"superato il budget di {_budget_tokens} token per questa "
                        f"esecuzione ({_tokens_run} consumati)",
                        wake.severity_hint),
                    AGENT_RUN_STOP_BUDGET)
                return
        if suggested and getattr(decision, "verdict", "") != "falso_positivo":
            decision.action = suggested  # target deterministico dalla config, non dall'LLM
        if force_notify_only:
            # Task 3 review fix: a notify-type Agentbot has `suggested is
            # None` (agentbot_action() returns None for
            # action.type=="notify"), so the guard above never fires and the
            # LLM's OWN parsed action would otherwise survive onto the
            # Decision. Force it back to None here, BEFORE execute() runs,
            # so a notify Agentbot can never actuate -- the AI still gets to
            # pick verdict/severity/message.
            decision.action = None
        _ep = app.get("execute_policy") or {}
        outcome = await execute(
            decision, wake,
            tiers=_ep.get("tiers") or {}, entity_tiers=_ep.get("entity_tiers") or {},
            notify=_notify, act=_act, propose=_propose,
            allow_green_auto=env_bool("SENTINEL_ALLOW_GREEN_AUTO"))
        await _record_situation_event(wake.signal_kind, wake.entity_id, decision, outcome)

    async def _on_situation(wake, suggested):
        await _run_decision(wake, suggested, SENTINEL_SYSTEM)

    # ── Agentbot definiti dall'utente (Slice 5b, Task 3; rinominati da
    # "lenti" in SP-4 Fase A Task 3): flusso condiviso ─────────────────────
    # `_run_agentbot` è un thin wiring del vero flusso (in
    # `watcher/agentbot_runner.py`, testabile in isolamento) sugli stessi
    # adapter reali già usati sopra (sentinel_store, _run_decision, execute,
    # _notify/_act/_propose, execute_policy) — nessun path di actuation
    # nuovo: stesso semaforo, stesso allowed_tools=[] della reasoning (via
    # _run_decision → reason → _llm_reason), stessa denylist domini
    # pericolosi (via executor.execute).
    from .watcher.agentbot_runner import run_agentbot as _run_agentbot_flow

    async def _run_agentbot(agentbot: dict, evidence: dict, *, cooldown_sec: int | None = None) -> str:
        # Task 5 review Fix 2: `cooldown_sec` is None for every EVENT-Agentbot
        # caller (`_dispatch_run_agentbot` above never passes it), so
        # behavior there is UNCHANGED -- the env-configured (default 1800s)
        # cooldown still applies. `_run_scheduled_agentbot` (server.py,
        # schedule-trigger callback) is the only caller that overrides it,
        # with 0.
        return await _run_agentbot_flow(
            agentbot, evidence,
            store=sentinel_store, run_decision=_run_decision, execute=execute,
            notify=_notify, act=_act, propose=_propose,
            get_execute_policy=lambda: app.get("execute_policy") or {},
            allow_green_auto=env_bool("SENTINEL_ALLOW_GREEN_AUTO"),
            record_event=sentinel_store.record_event,
            sentinel_system=SENTINEL_SYSTEM,
            cooldown_sec=cooldown_sec if cooldown_sec is not None
            else int(os.environ.get("SENTINEL_COOLDOWN_SEC", "1800")),
            daily_cap=int(os.environ.get("SENTINEL_DAILY_CAP", "20")),
        )

    app["run_agentbot"] = _run_agentbot

    # ── Agentbot definiti dall'utente (Slice 5b, Task 5): trigger
    # SCHEDULATO ──────────────────────────────────────────────────────────
    # `register_agentbot_schedules` (module-level, above) reads
    # `app["run_agentbot"]` (just bound) and `engine._scheduler` (already
    # started, `engine.start()` ran earlier in this function) to
    # (re)register a per-Agentbot cron/interval job for every enabled
    # schedule-type Agentbot. Exposed on `app` so Task 6's CRUD handlers can
    # re-invoke it after every Agentbot save/delete without a server.py
    # import (avoids a circular import back from api/handlers_*.py).
    app["register_agentbot_schedules"] = register_agentbot_schedules
    await register_agentbot_schedules(app)

    # ── Ponte push (Piano A, fetta 3): coda di lavori di reasoning per il
    # runner remoto. execute_decision applica una Decisione GIA' PRESA dal
    # runner attraverso lo STESSO executor.execute()/semaforo/adapters usati
    # sopra — nessun path di actuation nuovo, solo un altro chiamante.
    from .reasoning.queue import ReasoningQueue
    from .watcher.signals import Decision
    try:
        from .proxy._sanitize import sanitize_ha_value as _san
    except Exception:
        _san = lambda v: v  # noqa: E731

    reasoning_queue = ReasoningQueue(os.path.join(data_dir, "reasoning.db"))
    app["reasoning_queue"] = reasoning_queue

    async def _execute_decision(decision_dict, wake_dict):
        # Fail-CLOSED on the verdict: the runner submits this over the
        # network, so a missing/malformed/unknown verdict must NOT default to
        # the actuation-eligible "anomalia" — it degrades to "falso_positivo",
        # which execute() turns into a no-op "skip".
        _v = decision_dict.get("verdict")
        verdict = _v if _v in ("anomalia", "falso_positivo") else "falso_positivo"
        d = Decision(verdict=verdict,
                     severity=decision_dict.get("severity", "info"),
                     message=decision_dict.get("message", ""),
                     action=decision_dict.get("action"))
        wake = WakeEvent(signal_kind=wake_dict.get("signal_kind", "holistic"),
                          entity_id=wake_dict.get("entity_id", "home"),
                          severity_hint=wake_dict.get("severity_hint", "info"),
                          evidence=wake_dict.get("evidence") or {},
                          ts=wake_dict.get("ts") or _time.time())
        _ep = app.get("execute_policy") or {}
        outcome = await execute(
            d, wake,
            tiers=_ep.get("tiers") or {}, entity_tiers=_ep.get("entity_tiers") or {},
            notify=_notify, act=_act, propose=_propose,
            allow_green_auto=env_bool("SENTINEL_ALLOW_GREEN_AUTO"))
        sentinel_store.record_event({
            "ts": _time.time(), "kind": wake.signal_kind, "entity_id": wake.entity_id,
            "verdict": d.verdict, "severity": d.severity,
            "outcome": outcome, "message": d.message})
        return outcome
    app["execute_decision"] = _execute_decision

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

    async def _holistic_reason(snapshot):
        # Cervello auto-proponente: revisione di copertura sulla cadenza olistica.
        # Gira SEMPRE (anche quando BRIDGE_ENABLED e' attivo, prima del branch
        # sotto) perche' riusa direttamente _llm_reason (locale/metered) — non
        # instrada nessuna azione sulla casa, solo config detector (gated,
        # apply_suggestions) e proposte. Wrapped in try/except: non deve mai
        # rompere il giro olistico.
        try:
            _store = app.get("suggestion_store")
            _cache = app.get("entity_cache")
            if _store is not None and _cache is not None and hasattr(_cache, "all_states"):
                from .brain.coverage_review import (
                    COVERAGE_REVIEW_SYSTEM, build_review_context,
                    build_review_message, parse_suggestions)
                from .brain.suggestions import apply_suggestions
                from .brain.cognitive_loop import auto_tune_detectors, trace_applied_coverage
                from .api.handlers_entities import filter_entities
                _inventory = filter_entities(_cache.all_states(), None, None)
                _current = load_policy(data_dir)
                # Slice 6b Task 5: same bounded, home-scoped memory enrichment
                # as the per-wake sentinel path (_reason_memory_context /
                # Task 4), applied to the holistic coverage-review context.
                # Memory enrichment degrades to no-memory on ANY failure and
                # must never abort the holistic pass (coverage review + auto-
                # tune + guardian refresh below). relevant_memory() is already
                # non-throwing for the real store, but wrap independently so a
                # nonconforming store/embedder can't take the whole round down.
                _mem = []
                try:
                    _llm_router = app.get("llm_router")
                    _allow_sensitive = _llm_router.automatic_allows_sensitive() if _llm_router is not None else False
                    _mem = await relevant_memory(
                        knowledge_store, embedder,
                        query_text="stato generale della casa", allow_sensitive=_allow_sensitive,
                        limit=5)
                except Exception:
                    logger.warning("holistic memory retrieval failed", exc_info=True)
                _ctx = build_review_context(snapshot, _inventory, _current, memory=_mem)
                # SP-2 Task 4: il Brain (questo passaggio olistico) usa il
                # modello scelto per il Brain, se esplicito; "auto" (default)
                # -> catena, invariato.
                _brain_model = (app.get("models_config") or {}).get("brain_model", "auto")
                _text = await _llm_reason(COVERAGE_REVIEW_SYSTEM, build_review_message(_ctx),
                                          model=_brain_model, max_tokens=1536)
                _suggs = parse_suggestions(_text)

                try:
                    _rlog = app.get("reasoning_log")
                    if _rlog is not None and _text and _text.strip():
                        _rlog.capture(mode="holistic", text=_text)
                except Exception:
                    logger.warning("reasoning capture failed", exc_info=True)

                def _mk_proposal(c):
                    return _spawn(create_automation_proposal(
                        proposal_store, proposal_type="ha_automation",
                        name=str(c.get("name") or "Brain coverage-review"),
                        description=str(c.get("description") or ""),
                        config=c, routing_reason="brain coverage-review"),
                        name="create_automation_proposal")

                _applied_coverage = apply_suggestions(
                    _suggs, data_dir=data_dir, store=_store,
                    inventory_ids={e["entity_id"] for e in _inventory},
                    current_config=_current, create_proposal=_mk_proposal,
                    cap=int(os.environ.get("BRAIN_SUGGEST_CAP", "5")))

                # Slice 6 Task 4: write-back a recallable brain-action trace
                # for every coverage suggestion just auto-applied above, so
                # the chat can later explain what the brain did on its own.
                await trace_applied_coverage(knowledge_store, embedder, _applied_coverage)

                # Slice 6 Task 4: auto-tune enabled LEARNABLE detectors (v1:
                # "power") from history baselines. Deterministic-action
                # discipline: the tuning value comes ONLY from
                # learned_threshold (pure/deterministic), never from the
                # LLM/reasoner above -- re-read the policy so a detector/
                # entity apply_suggestions just enabled above is considered.
                await auto_tune_detectors(
                    data_dir=data_dir, policy=load_policy(data_dir),
                    history_store=history_store, knowledge_store=knowledge_store,
                    embedder=embedder,
                    cap=int(os.environ.get("BRAIN_TUNE_CAP", "5")),
                    # Slice 6 Task 5: surface applied tunings in the same
                    # "Suggerimenti del cervello" store/UI as coverage
                    # suggestions, so they are undoable via the existing
                    # /api/suggestions/{id}/undo route.
                    store=_store)

                # Slice 6 (whole-branch review I1): the running guardian holds
                # a policy override snapshot (set at startup / on UI save), so
                # threshold tunings and coverage detectors just written to disk
                # above are invisible to the live DETECTORS loop until the next
                # UI save or restart -- making the auto-tune (and its undo)
                # behaviorally inert live. Refresh the override from disk so the
                # brain's changes take effect immediately.
                guardian.set_policy(load_policy(data_dir))
        except Exception:
            logger.exception("coverage-review failed")

        if env_bool("BRIDGE_ENABLED") or _sub_first_class:
            wake = {"signal_kind": "holistic", "entity_id": "home", "severity_hint": "info",
                    "evidence": {}, "ts": _time.time()}
            ctx = {"snapshot": {k: (_san(v) if isinstance(v, str) else v) for k, v in (snapshot or {}).items()}}
            deadline = _time.time() + int(os.environ.get("BRIDGE_DEADLINE_MIN", "5")) * 60
            reasoning_queue.enqueue("holistic", wake, ctx, deadline, now=_time.time())
            return
        wake = WakeEvent("holistic", "home", "info", {"snapshot": snapshot}, _time.time())
        await _run_decision(wake, None, SITUATION_HOLISTIC_SYSTEM)

    situation_evaluator = SituationEvaluator(
        sentinel_store, lambda: load_policy(data_dir),
        build_snapshot=_snapshot, on_situation=_on_situation, holistic_reason=_holistic_reason,
        cooldown_sec=int(os.environ.get("SENTINEL_COOLDOWN_SEC", "1800")),
        daily_cap=int(os.environ.get("SENTINEL_DAILY_CAP", "20")))
    app["situation_evaluator"] = situation_evaluator

    engine._scheduler.add_job(
        situation_evaluator.run_evaluation, trigger="interval",
        minutes=int(os.environ.get("SENTINEL_RONDA_MINUTES", "15")),
        id="hiris_sentinel_ronda", replace_existing=True, misfire_grace_time=300)

    # SP-3 Task 8: periodic read-only health scan (5 checks) reconciled into
    # the AdvisoryStore, plus a nightly prune of the reasoning capture log.
    from .brain.health_scan import run_health_scan

    async def _run_health_scan():
        try:
            pol = app.get("execute_policy") or {}
            await run_health_scan(
                ha_client=ha_client, entity_cache=app.get("entity_cache"),
                tiers=pol.get("tiers") or {}, entity_tiers=pol.get("entity_tiers") or {},
                store=advisory_store, now=datetime.now(timezone.utc))
        except Exception:
            logger.exception("health scan failed")

    engine._scheduler.add_job(
        _run_health_scan, trigger="interval",
        minutes=int(os.environ.get("HIRIS_HEALTH_SCAN_MINUTES", "30")),
        id="hiris_health_scan", replace_existing=True, misfire_grace_time=300)

    def _run_reasoning_prune():
        try:
            reasoning_log.prune(max_rows=500, max_age_days=30)
        except Exception:
            logger.exception("reasoning prune failed")

    engine._scheduler.add_job(
        _run_reasoning_prune, trigger="cron", hour=3, minute=15,
        id="hiris_reasoning_prune", replace_existing=True, misfire_grace_time=3600)

    # ── Ponte push (Piano A): spazzata di fallback per i job scaduti senza risposta dal
    # runner remoto. Se BRIDGE_FALLBACK è attivo, ragiona in locale riusando
    # lo stesso _run_decision (e quindi lo stesso cap del router LLM) delle
    # situazioni sopra — nessun path metrico/actuation nuovo.
    async def _reasoning_sweep() -> None:
        if not env_bool("BRIDGE_ENABLED") and not _sub_first_class:
            return
        fallback = env_bool("BRIDGE_FALLBACK", default=True)
        for job in reasoning_queue.sweep_expired(_time.time()):
            if job.get("kind") != "holistic":
                # Non-holistic jobs (e.g. kind="chat") must never be routed
                # into holistic reasoning: they simply stay 'expired' and are
                # surfaced to their own caller (e.g. the chat poll route).
                continue
            if not fallback:
                continue
            jw = job.get("wake") or {}
            wake = WakeEvent(jw.get("signal_kind", "holistic"), jw.get("entity_id", "home"),
                              jw.get("severity_hint", "info"),
                              {"snapshot": (job.get("context") or {}).get("snapshot", {})}, _time.time())
            try:
                await _run_decision(wake, None, SITUATION_HOLISTIC_SYSTEM)  # metered/locale, già capato dal router
            except Exception:
                logger.exception("reasoning fallback failed for %s", job.get("job_id"))
        reasoning_queue.prune(_time.time() - 7 * 86400)

    engine._scheduler.add_job(
        _reasoning_sweep, trigger="interval", minutes=2,
        id="hiris_reasoning_sweep", replace_existing=True, misfire_grace_time=120)

    # Slice 4b Task 5: the chat_via_subscription addon option only takes
    # effect when the bridge is ALSO truly usable. handlers_chat._bridge_on
    # just checks that app["reasoning_queue"] is wired -- and it always is in
    # prod (created unconditionally a few lines above) -- so on its own it's
    # not a signal that anything actually claims/sweeps/prunes those jobs.
    # That sweeping/pruning (both _holistic_reason's enqueue above and
    # _reasoning_sweep just above) is gated on BRIDGE_ENABLED, read the same
    # way here as everywhere else in this module. Gating the flag itself at
    # this single wiring point -- rather than teaching _bridge_on about
    # BRIDGE_ENABLED -- keeps handlers_chat.py's tests able to wire/unwire
    # the queue directly without touching env vars, while still making sure
    # chat_via_subscription=true + BRIDGE_ENABLED=0 enqueues nothing that
    # would sit pending forever and grow the DB.
    #
    # SP-2 T3: provider_subscription (first-class) must ALSO force the bridge
    # on, everywhere BRIDGE_ENABLED is read -- not just here. _sub_first_class
    # (computed once, right after _active above) is OR'd into all THREE
    # BRIDGE_ENABLED reads in this module: _holistic_reason's enqueue gate,
    # _reasoning_sweep's early-return, and this cfg/bridge derivation. Missing
    # any one of them would leave a hole where the fail-safe below
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

    # ── Arrivo serale (fetta 3): riusa lo stesso adapter _on_situation ──────
    # (reason→inietta suggested_action→execute→record), stessa gate del
    # semaforo (execute_policy) delle situazioni sopra. Nessun path di
    # actuation nuovo: instrada solo attraverso _on_situation.
    from .watcher.arrival import ArrivalWatcher

    _arrival_deps = {
        "get_states": lambda ids: ha_client.get_states(ids),
        "now_hour": lambda: _dt.now().hour,
    }
    arrival_watcher = ArrivalWatcher(
        sentinel_store, lambda: load_policy(data_dir), deps=_arrival_deps,
        on_arrival=_on_situation,  # riuso identico: (wake, suggested) → reason→inietta→execute→record
        cooldown_sec=int(os.environ.get("SENTINEL_COOLDOWN_SEC", "1800")),
        daily_cap=int(os.environ.get("SENTINEL_DAILY_CAP", "20")))
    app["arrival_watcher"] = arrival_watcher
    ha_client.add_state_listener(
        lambda evt: _spawn(arrival_watcher.on_state_changed(evt), name="arrival_watcher_on_state_changed")
    )

    # SP-2 T5C: per-provider DEFAULT model chosen by the user (used when an
    # entity's model is "auto"); Ollama excluded — it uses local_model.model
    # via fixed_model instead. Empty string ("") preserves today's behaviour
    # (fall back to AUTO_MODEL_MAP).
    _pm = app["models_config"].get("provider_models", {})

    claude_runner = None
    if api_key and _active["claude"]:
        claude_runner = ClaudeRunner(
            api_key=api_key,
            dispatcher=dispatcher,
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
            dispatcher=dispatcher,
            usage_path=f"{_usage_base}_openai{_usage_ext}",
            default_model=_pm.get("openai", ""),
        )

    ollama_runner = None
    if local_model_url and local_model_name and _active["ollama"]:
        ollama_runner = OpenAICompatRunner(
            base_url=local_model_url.rstrip("/") + "/v1",
            api_key="ollama",
            dispatcher=dispatcher,
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
            dispatcher=dispatcher,
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
        semantic_map.set_router(router)
        app["claude_runner"] = claude_runner  # backward compat (may be None)
        app["llm_router"] = router
        engine.set_claude_runner(router)
        engine.set_task_engine(task_engine)

        # Kick off LLM classification for ambiguous entities (background, non-blocking)
        if ambiguous:
            _spawn(
                semantic_map._classify_unknown_batch(),
                name="semantic_map_initial_classify",
            )
    else:
        app["claude_runner"] = None
        app["llm_router"] = None

    # ── Internal MCP server (loopback-only, Plan 2A Task 3) ────────────────
    # Serves the MCP tool surface over the local execute-API to an MCP-aware
    # LLM client (e.g. Claude Desktop/Code via a local bridge), bound to
    # 127.0.0.1 only -- never reachable off-box. Runs as a background asyncio
    # task on the SAME event loop as the rest of the app; cancelled + the
    # client's aiohttp session closed in _on_cleanup below.
    _mcp_client, _mcp_config, _mcp_guard = build_internal_mcp_server()
    await _mcp_client.start()
    _mcp_server = _EmbeddedMCPServer(_mcp_config)
    app["internal_mcp_client"] = _mcp_client
    # I-2 partial (Plan 2B final review, fast-follow): store the guard on the
    # app so it's reachable (e.g. by a future admin endpoint or diagnostics)
    # instead of being trapped inside build_internal_mcp_server's closure.
    app["mcp_guard"] = _mcp_guard
    # Through _spawn() (not a bare asyncio.create_task) per review C/#15's
    # convention for every fire-and-forget task in this module -- _spawn's
    # strong reference is redundant here (app already holds one via
    # internal_mcp_task) but keeps this the ONE call site the AST-enforced
    # test_only_spawn_itself_calls_asyncio_create_task expects.
    app["internal_mcp_task"] = _spawn(
        _run_internal_mcp(_mcp_server), name="internal_mcp_server"
    )
    logger.info("Internal MCP server avviato su 127.0.0.1:%s", _mcp_config.port)

    # ── Chat-via-abbonamento worker in-addon (Plan 2B Task 4) ──────────────
    # Polls the internal reasoning queue and reasons via `claude -p` under the
    # user's Claude subscription (CLAUDE_CODE_OAUTH_TOKEN) instead of metered
    # API spend. Off unless both the feature flag and the token are present
    # (should_start_agent_worker); gated separately from the MCP server above
    # since a subscription may be absent even when the MCP tool surface is
    # up. Same _spawn()/app[...] cancel-in-cleanup convention as
    # internal_mcp_task.
    if should_start_agent_worker():
        from .agent import runner as _agent_runner

        _agent_runner.configure_chat_mcp()
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
    # CONSUMER (agent_worker_task) before the internal_mcp_task producer, and
    # bound the wait. A claimed job can be sitting inside run_loop's
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
    task = app.get("internal_mcp_task")
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    client = app.get("internal_mcp_client")
    if client is not None:
        await client.stop()
    if app.get("mayan_client") is not None:
        await app["mayan_client"].aclose()
    if "mqtt_publisher" in app:
        await app["mqtt_publisher"].stop()
    if "knowledge_db" in app:
        app["knowledge_db"].close()
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
    if "reasoning_queue" in app:
        app["reasoning_queue"].close()
    if "task_engine" in app:
        await app["task_engine"].stop()
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
    app.router.add_get("/api/chatbots/{agent_id}/context-preview", handle_context_preview)
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
    app.router.add_get("/api/knowledge/pending", handle_list_pending)
    app.router.add_post("/api/knowledge/{id}/approve", handle_approve)
    app.router.add_post("/api/knowledge/{id}/reject", handle_reject)
    app.router.add_post("/api/knowledge", handle_manual_add)

    from .api.handlers_execute import handle_execute
    app.router.add_post("/api/execute", handle_execute)

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

    # Slice 5b Task 6: user-Agentbot CRUD (renamed from "lens" in SP-4 Fase A
    # Task 4). Same app-level internal_auth_middleware + csrf_middleware
    # protection as every other /api/* route above -- no per-route auth
    # here, just registration under the same app.router.
    from .api.handlers_agentbots import (
        handle_list_agentbots, handle_create_agentbot, handle_update_agentbot, handle_delete_agentbot,
    )
    app.router.add_get("/api/agentbots", handle_list_agentbots)
    app.router.add_post("/api/agentbots", handle_create_agentbot)
    app.router.add_put("/api/agentbots/{id}", handle_update_agentbot)
    app.router.add_delete("/api/agentbots/{id}", handle_delete_agentbot)

    from .api.handlers_gateway_pending import (
        handle_list_pending as _gw_list_pending,
        handle_approve_pending as _gw_approve_pending,
        handle_reject_pending as _gw_reject_pending,
    )
    app.router.add_get("/api/gateway/pending", _gw_list_pending)
    app.router.add_post("/api/gateway/pending/{nonce}/approve", _gw_approve_pending)
    app.router.add_post("/api/gateway/pending/{nonce}/reject", _gw_reject_pending)

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
    return web.json_response({"status": "ok", "version": read_version()})
