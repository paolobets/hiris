# hiris/app/server.py
import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import time
import aiohttp
from aiohttp import web
from apscheduler.triggers.cron import CronTrigger
from .api.handlers_chat import handle_chat, handle_chat_reply_poll
from .api.handlers_agents import (
    handle_list_agents, handle_create_agent, handle_get_agent,
    handle_update_agent, handle_delete_agent, handle_run_agent,
    handle_get_agent_usage, handle_reset_agent_usage,
    handle_context_preview,
)
from .api.handlers_entities import handle_list_entities
from .api.handlers_suggestions import handle_list_suggestions, handle_undo_suggestion
from .api.handlers_status import handle_status
from .api.handlers_config import handle_config
from .api.handlers_usage import handle_usage, handle_reset_usage
from .api.handlers_chat_history import handle_get_chat_history, handle_clear_chat_history
from .api.handlers_tasks import handle_list_tasks, handle_get_task, handle_cancel_task
from .api.handlers_models import handle_list_models
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
from .agent_engine import AgentEngine
from .task_engine import TaskEngine
from .version import read_version
from .proxy.ha_client import HAClient
from .proxy.entity_cache import EntityCache
from .proxy.knowledge_db import KnowledgeDB
from .proxy.semantic_context_map import SemanticContextMap
from .backends.embeddings import build_embedding_provider
from .brain.knowledge_store import KnowledgeStore
from .brain.memory_migration import migrate_agent_memories
from .brain.privacy import VaultStore, Pseudonymizer
from .api.middleware_internal_auth import internal_auth_middleware
from .api.middleware_csrf import csrf_middleware
from .mqtt_publisher import MQTTPublisher
from .llm_router import _VALID_BACKEND_NAMES as _VALID_POLICY_BACKENDS
from .watcher.detectors import make_generic_detector
from .watcher.lenses import load_lenses as _load_scheduled_lenses

logger = logging.getLogger(__name__)


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
    data = inputs.get("data") if isinstance(inputs.get("data"), dict) else {}
    target = inputs.get("target") if isinstance(inputs.get("target"), dict) else {}
    raw = data.get("entity_id") if isinstance(data, dict) else None
    if raw is None:
        raw = target.get("entity_id") if isinstance(target, dict) else None
    if isinstance(raw, str):
        ids = [raw]
    elif isinstance(raw, list):
        ids = [e for e in raw if isinstance(e, str)]
    else:
        ids = []
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
    from .api.handlers_gateway_policy import notify_service_for_user

    # Safety (Fix 5): with no real identity (falsy user, or the "home"
    # no-identity fallback bucket — see brain/identity.py's `uid or "home"`)
    # there is no phone to target and no chat OTP flow that could ever
    # resolve this pending, since verify_otp() matches on `user`. Minting one
    # anyway would create a dead pending nobody can confirm. Return None so
    # the dispatcher falls back to the Slice-1 "richiede conferma" error.
    if not user or user == "home":
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
    svc = notify_service_for_user(app, user)
    msg = _confirmation_push_message(label, inputs, entry["otp"])
    # Owner decision (Fix 3): red/dangerous pendings are page/OTP-only — no
    # one-tap notification buttons (matches the gateway's execute-API
    # behaviour in handlers_execute.py, which uses actionable=(tier ==
    # "yellow")). Only yellow gets actionable=True. The OTP is included in
    # `msg` above unconditionally either way.
    otp_sent = await notify(app, message=msg, actionable=(tier == "yellow"),
                            nonce=entry["id"], service=svc)
    return {"id": entry["id"], "otp_sent": bool(otp_sent)}


# ---------------------------------------------------------------------------
# Slice 5b Task 5: SCHEDULED (cron/interval) user lenses -- per-lens jobs on
# `engine._scheduler`, the SAME AsyncIOScheduler instance the built-in
# ronda/reset/due-reminders jobs use (verified: `_on_startup` never creates a
# second scheduler). Module-level (same rationale as
# confirm_pending_execute/request_confirmation_stepup above) so tests can
# drive `register_lens_schedules` against a fake scheduler + fake
# entity_cache without booting the whole aiohttp app.
# ---------------------------------------------------------------------------

_LENS_JOB_PREFIX = "hiris_lens_"


def _condition_holds(condition: dict | None, cache) -> bool:
    """Evaluate a schedule trigger's optional `trigger.condition`
    (`{entity_id, operator, threshold}`, already whitelist-validated by
    `watcher.lenses._validate_condition`) against the CURRENT cached state
    of `condition["entity_id"]` (`entity_cache.get_state`). Absent condition
    -> True (nothing to gate on).

    Reuses `make_generic_detector` (Task 2) with a synthesized one-shot
    trigger dict so the exact same operator/threshold comparison applies
    here as to a real event-triggered lens -- including the no-data guard
    for "unavailable"/"unknown"/"" states and the numeric-vs-string
    fallback for ==/!= -- rather than a second, driftable implementation of
    the same comparison.

    Fail-safe: missing cache, missing entity_id, an entity never seen by the
    cache, or the detector raising all resolve to False -- a conditioned
    scheduled lens must never fire when its condition can't be positively
    confirmed.
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
        logger.debug("register_lens_schedules: cache.get_state(%s) failed", entity_id, exc_info=True)
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
        logger.debug("register_lens_schedules: condition detector failed for %s", entity_id, exc_info=True)
        return False
    return sig is not None


async def _run_scheduled_lens(lens: dict, *, cache, run_lens) -> None:
    """The per-lens job callback registered by `register_lens_schedules`.
    Wrapped end-to-end in try/except (log + return) so one broken scheduled
    lens (a condition entity that vanished, `run_lens` raising, ...) can
    never take down the shared AsyncIOScheduler or any sibling job."""
    lens_id = lens.get("id", "-")
    try:
        trigger = lens.get("trigger") or {}
        condition = trigger.get("condition")
        if condition and not _condition_holds(condition, cache):
            return
        entity_id = condition.get("entity_id", "-") if condition else "-"
        # Task 5 review Fix 2: a scheduled lens's own interval/cron cadence
        # IS its rate limiter -- bypass the ~30-min sentinel cooldown here
        # (cooldown_sec=0) so e.g. an interval_min=5 lens isn't silently
        # suppressed by it. `run_lens`'s daily_cap (an unrelated, unchanged
        # safety net) and every other gate still apply unchanged.
        await run_lens(lens, {"entity_id": entity_id}, cooldown_sec=0)
    except Exception:
        logger.exception("scheduled lens %s failed", lens_id)


def _translate_cron_dow(field: str) -> str:
    """Remap a cron day-of-week FIELD from STANDARD crontab numbering
    (POSIX cron(5): 0 or 7 = Sunday, 1 = Monday, ..., 6 = Saturday -- what
    every SCHEDULE-trigger user lens is authored against, and what
    `watcher.lenses._CRON_RE` whitelists) to APScheduler's OWN CronTrigger
    day_of_week numbering (0 = Monday, ..., 6 = Sunday, i.e. Python's
    `datetime.weekday()`).

    This translation is REQUIRED even though the caller builds the trigger
    via `CronTrigger.from_crontab` -- verified against the installed
    apscheduler==3.10.4, `from_crontab` does NOT perform any day_of_week
    remapping itself: it feeds a numeric day_of_week token straight into
    APScheduler's own field parser unchanged. Confirmed empirically: an
    UNTRANSLATED `CronTrigger.from_crontab("0 3 * * 0")` (standard-crontab
    Sunday) computes its next fire time on APScheduler's day_of_week=0,
    which is MONDAY, not Sunday; and a POSIX-legal "7" raises outright
    (APScheduler's day_of_week max is 6). This function runs BEFORE the
    cron string ever reaches `from_crontab`, fixing both at the source
    rather than relying on upstream translation that doesn't exist.

    Supports exactly the charset `_CRON_RE` allows for a cron field --
    digits, `*`, `,`, `/`, `-` -- i.e. bare values, comma-lists, ranges, and
    step values, in any combination (e.g. "1-5", "0,6", "*/2"). Any field
    this can't parse, or that resolves to a value outside 0-7, raises
    ValueError -- the caller (`register_lens_schedules`) catches this
    per-lens so one broken cron never blocks the others.
    """
    field = field.strip()
    if field == "*":
        return "*"
    crontab_days: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"empty day_of_week token in {field!r}")
        step = 1
        base = part
        if "/" in part:
            base, step_s = part.split("/", 1)
            step = int(step_s)
            if step <= 0:
                raise ValueError(f"non-positive step in {part!r}")
        if base == "*":
            lo, hi = 0, 7
        elif "-" in base:
            lo_s, hi_s = base.split("-", 1)
            lo, hi = int(lo_s), int(hi_s)
        else:
            lo = hi = int(base)
        if lo > hi:
            raise ValueError(f"backwards range in {part!r}")
        v = lo
        while v <= hi:
            crontab_days.add(v)
            v += step
    if not crontab_days or any(d < 0 or d > 7 for d in crontab_days):
        raise ValueError(f"day_of_week value out of range 0-7 in {field!r}")
    # 0 and 7 both denote Sunday in standard crontab -- collapse them onto
    # the SAME APScheduler day (6) rather than two separate ones.
    normalized = {0 if d == 7 else d for d in crontab_days}
    apscheduler_days = sorted((d - 1) % 7 for d in normalized)
    return ",".join(str(d) for d in apscheduler_days)


def _to_apscheduler_crontab(cron: str) -> str:
    """Rewrite a whitelist-validated 5-field standard-crontab string
    (`watcher.lenses._CRON_RE` already confirmed the charset/shape) into
    the equivalent string for `CronTrigger.from_crontab`, remapping ONLY
    the day_of_week field (`_translate_cron_dow`) -- minute/hour/day/month
    use the same numbering in both conventions and pass through untouched.
    Raises ValueError if the field count is off (defensive -- the store's
    regex already guarantees exactly 5 whitespace-separated fields) or the
    day_of_week field doesn't parse; the caller's try/except turns either
    into "skip this lens" without crashing registration of the rest.
    Per-field VALUE validity of minute/hour/day/month (e.g. an out-of-range
    hour) is left to `CronTrigger.from_crontab` itself, raised at
    `add_job` time and caught there."""
    parts = cron.split()
    if len(parts) != 5:
        raise ValueError(f"expected 5 cron fields, got {len(parts)}: {cron!r}")
    minute, hour, day, month, dow = parts
    return f"{minute} {hour} {day} {month} {_translate_cron_dow(dow)}"


async def register_lens_schedules(app: web.Application) -> None:
    """(Re)register per-lens scheduler jobs for every enabled,
    SCHEDULE-triggered user lens (Slice 5b Task 5), and remove any
    `hiris_lens_*` job whose lens no longer exists, is disabled, or is no
    longer schedule-triggered. Idempotent -- safe to call at startup and
    again after every lens save (Task 6, via `app["register_lens_schedules"]`).

    Reads `engine._scheduler` (the SAME scheduler instance the built-in
    ronda/reset jobs use), `data_dir` (to reload the current lens set) and
    `entity_cache` (for the schedule trigger's optional `condition`, checked
    at fire time by `_run_scheduled_lens`/`_condition_holds`) straight off
    `app`, mirroring `confirm_pending_execute`'s "module-level, reads from
    app, testable without booting `_on_startup`" shape.
    """
    engine = app.get("engine")
    scheduler = getattr(engine, "_scheduler", None)
    if scheduler is None:
        return

    data_dir = app.get("data_dir")
    lenses = _load_scheduled_lenses(data_dir) if data_dir else []
    scheduled = {
        l["id"]: l for l in lenses
        if l.get("enabled") and (l.get("trigger") or {}).get("type") == "schedule"
    }

    # Remove orphaned jobs: a lens that was deleted, disabled, or switched
    # away from a schedule trigger since the last registration. Enumeration
    # pattern mirrors `agent_engine.py:350-353`'s `_unschedule_agent`.
    for job in list(scheduler.get_jobs()):
        if not job.id.startswith(_LENS_JOB_PREFIX):
            continue
        lens_id = job.id[len(_LENS_JOB_PREFIX):]
        if lens_id not in scheduled:
            try:
                scheduler.remove_job(job.id)
            except Exception:
                logger.debug("register_lens_schedules: remove_job(%s) failed", job.id, exc_info=True)

    cache = app.get("entity_cache")
    run_lens = app.get("run_lens")

    def _make_callback(lens: dict):
        # Bind `lens` via this factory's own parameter (a fresh scope per
        # call) rather than closing directly over the loop variable below,
        # which would otherwise let every job share the LAST lens iterated.
        async def _cb() -> None:
            await _run_scheduled_lens(lens, cache=cache, run_lens=run_lens)
        return _cb

    for lens_id, lens in scheduled.items():
        trigger = lens.get("trigger") or {}
        job_id = f"{_LENS_JOB_PREFIX}{lens_id}"
        cron = trigger.get("cron")
        interval_min = trigger.get("interval_min")
        try:
            if cron:
                trigger = CronTrigger.from_crontab(_to_apscheduler_crontab(cron))
                scheduler.add_job(
                    _make_callback(lens), trigger=trigger, id=job_id,
                    replace_existing=True, misfire_grace_time=3600)
            elif interval_min:
                scheduler.add_job(
                    _make_callback(lens), trigger="interval", minutes=interval_min,
                    id=job_id, replace_existing=True, misfire_grace_time=3600)
            else:
                # Neither cron nor interval_min -- shouldn't happen for a
                # store-validated lens (XOR enforced at validation time),
                # but skip defensively rather than register a no-op job.
                continue
        except Exception:
            # A shape-valid but value-invalid cron (e.g. hour=99) surfaces
            # here as APScheduler's own ValueError at add_job time -- one
            # broken lens's schedule must never crash registration for the
            # rest.
            logger.warning("register_lens_schedules: failed to schedule lens %s, skipping", lens_id, exc_info=True)
            continue


async def _on_startup(app: web.Application) -> None:
    from .claude_runner import ClaudeRunner
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

    data_path = os.environ.get("AGENTS_DATA_PATH", "/data/agents.json")
    data_dir = os.path.dirname(os.path.abspath(data_path))
    app["data_dir"] = data_dir
    # If the user manages the gateway policy from the UI, it overrides the env CSV.
    from .api.handlers_gateway_policy import apply_saved_policy
    apply_saved_policy(app)
    # Yellow approval: route iPhone notification-action button taps to approve/reject.
    import asyncio as _asyncio
    from .api.handlers_gateway_pending import on_notification_action
    ha_client.add_action_listener(
        lambda ev: _asyncio.create_task(on_notification_action(app, ev))
    )

    # Build semantic map
    semantic_map = SemanticMap(data_dir=data_dir)
    semantic_map.load()
    ambiguous = semantic_map.build_from_cache(entity_cache)
    app["semantic_map"] = semantic_map
    ha_client.add_registry_listener(semantic_map.on_entity_added)

    engine = AgentEngine(ha_client=ha_client, data_path=data_path)
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
    app["theme"] = os.environ.get("THEME", "auto")

    tasks_data_path = os.environ.get("TASKS_DATA_PATH", "/data/tasks.json")
    task_engine = TaskEngine(
        ha_client=ha_client,
        entity_cache=entity_cache,
        notify_config=notify_config,
        data_path=tasks_data_path,
        execute_policy=app["execute_policy"],
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
        n2 = knowledge_store.purge_expired_lens()
        if n2:
            logger.info("Retention: purged %d expired lens memories", n2)

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
        asyncio.create_task(_run_mayan_ingest(), name="mayan_ingest_initial")
    else:
        logger.debug(
            "Mayan EDMS disabled (url=%r, token set=%s, tag_id=%d)",
            mayan_url, bool(mayan_token), mayan_tag_id,
        )

    # Daily due-date reminders job (second-brain phase-1, Task 10).
    # Runs at 08:00 every day. Sends one notification per due obligation via the
    # existing send_notification path (ha_push by default). Once-per-day cadence
    # is the dedup strategy — no persistent dedup state is maintained.
    async def _notify_due_obligations() -> None:
        from datetime import date as _date
        from .brain.reminders import run_due_reminders as _run_due_reminders
        from .tools.notify_tools import send_notification as _send_notification

        store = app.get("knowledge_store")
        if store is None:
            return
        ha = app.get("ha_client")
        n_cfg = app.get("_notify_config_ref")
        if ha is None or n_cfg is None:
            return

        async def _notify_one(item: dict) -> None:
            due = item.get("due_date", "?")
            content = item.get("content", "")
            message = f"Scadenza imminente: {content} (entro {due})"
            try:
                await _send_notification(ha, message, "ha_push", n_cfg)
            except Exception as exc:
                logger.error("Due-date reminders: notification failed for %r: %s", content, exc)

        try:
            await _run_due_reminders(store, _notify_one, today=_date.today())
        except Exception as exc:
            logger.error("Due-date reminders: error querying obligations: %s", exc)

    # Stash notify_config reference so the job closure can access it after startup
    app["_notify_config_ref"] = notify_config

    engine._scheduler.add_job(
        _notify_due_obligations,
        trigger="cron",
        hour=8,
        minute=0,
        id="hiris_due_reminders",
        replace_existing=True,
        misfire_grace_time=3600,
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

    def _gather_context(wake) -> dict:
        # Synchronous, non-throwing: best-effort friendly_name from the entity
        # cache; falls back to the raw entity_id when unavailable.
        try:
            cache = app.get("entity_cache")
            state = cache.get_state(wake.entity_id) if cache is not None else None
            fn = (state or {}).get("attributes", {}).get("friendly_name") if state else None
            return {"friendly_name": fn or wake.entity_id}
        except Exception:
            return {"friendly_name": wake.entity_id}

    async def _llm_reason(system, user, *, model, max_tokens):
        # allowed_tools=[] → this reasoning call performs NO home actions; the
        # executor below is the only thing that acts, gated by the semaforo.
        runner = app.get("llm_router")
        if runner is None:
            eng = app.get("engine")
            runner = getattr(eng, "_claude_runner", None) if eng is not None else None
        if runner is None or not hasattr(runner, "run_with_actions"):
            return ""
        out = await runner.run_with_actions(
            user_message=user, system_prompt=system,
            allowed_tools=[], model=model, max_tokens=max_tokens, agent_type="agent")
        if isinstance(out, tuple):
            return out[0] or ""
        return out or ""

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
                allow_green_auto=os.environ.get("SENTINEL_ALLOW_GREEN_AUTO", "0")
                in ("1", "true", "yes", "on"))
        except Exception:
            logger.exception("sentinel on_wake failed")
            outcome = "error"
        sentinel_store.record_event({
            "ts": _time.time(), "kind": wake.signal_kind, "entity_id": wake.entity_id,
            "verdict": getattr(decision, "verdict", None), "severity": wake.severity_hint,
            "outcome": outcome, "message": getattr(decision, "message", "")})

    # Slice 5b / Task 4: EVENT-triggered user lenses, dispatched by the SAME
    # Guardian.on_state_changed alongside (not instead of) the built-in
    # DETECTORS above. `get_user_lenses` reads the in-memory lens cache
    # (Task 6, `handlers_lenses.set_lenses`/`get_event_lenses`) instead of
    # re-reading+re-validating sentinel_lenses.json on every single
    # state_changed event (Task 4 review finding). The cache is populated
    # right here from the current disk contents, and refreshed after every
    # CRUD mutation by the `/api/lenses` handlers -- so freshly-saved lenses
    # are still live without a restart, just without the per-event disk hit.
    from .watcher.lenses import load_lenses as _load_lenses
    from .api.handlers_lenses import set_lenses as _set_lenses_cache
    from .api.handlers_lenses import get_event_lenses as _get_event_lenses_cache

    _set_lenses_cache(app, _load_lenses(data_dir))

    def _get_event_lenses() -> list:
        return _get_event_lenses_cache(app)

    async def _dispatch_run_lens(lens: dict, evidence: dict) -> str:
        return await app["run_lens"](lens, evidence)

    guardian = Guardian(
        sentinel_store, lambda: load_policy(data_dir), _on_wake,
        cooldown_sec=int(os.environ.get("SENTINEL_COOLDOWN_SEC", "1800")),
        daily_cap=int(os.environ.get("SENTINEL_DAILY_CAP", "20")),
        get_user_lenses=_get_event_lenses,
        run_lens=_dispatch_run_lens)
    guardian.set_policy(load_policy(data_dir))
    app["guardian"] = guardian
    ha_client.add_state_listener(lambda evt: asyncio.create_task(guardian.on_state_changed(evt)))

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

    async def _run_decision(wake, suggested, system, force_notify_only=False):
        decision = await reason(wake, gather_context=_gather_context, llm_reason=_llm_reason, system=system)
        if suggested and getattr(decision, "verdict", "") != "falso_positivo":
            decision.action = suggested  # target deterministico dalla config, non dall'LLM
        if force_notify_only:
            # Task 3 review fix: a notify-type lens has `suggested is None`
            # (lens_action() returns None for action.type=="notify"), so the
            # guard above never fires and the LLM's OWN parsed action would
            # otherwise survive onto the Decision. Force it back to None
            # here, BEFORE execute() runs, so a notify lens can never
            # actuate -- the AI still gets to pick verdict/severity/message.
            decision.action = None
        _ep = app.get("execute_policy") or {}
        outcome = await execute(
            decision, wake,
            tiers=_ep.get("tiers") or {}, entity_tiers=_ep.get("entity_tiers") or {},
            notify=_notify, act=_act, propose=_propose,
            allow_green_auto=os.environ.get("SENTINEL_ALLOW_GREEN_AUTO", "0")
            in ("1", "true", "yes", "on"))
        await _record_situation_event(wake.signal_kind, wake.entity_id, decision, outcome)

    async def _on_situation(wake, suggested):
        await _run_decision(wake, suggested, SENTINEL_SYSTEM)

    # ── Lenti definite dall'utente (Slice 5b, Task 3): flusso condiviso ─────
    # `_run_lens` è un thin wiring del vero flusso (in `watcher/lens_runner.py`,
    # testabile in isolamento) sugli stessi adapter reali già usati sopra
    # (sentinel_store, _run_decision, execute, _notify/_act/_propose,
    # execute_policy) — nessun path di actuation nuovo: stesso semaforo,
    # stesso allowed_tools=[] della reasoning (via _run_decision → reason →
    # _llm_reason), stessa denylist domini pericolosi (via executor.execute).
    from .watcher.lens_runner import run_lens as _run_lens_flow

    async def _run_lens(lens: dict, evidence: dict, *, cooldown_sec: int | None = None) -> str:
        # Task 5 review Fix 2: `cooldown_sec` is None for every EVENT-lens
        # caller (`_dispatch_run_lens` above never passes it), so behavior
        # there is UNCHANGED -- the env-configured (default 1800s) cooldown
        # still applies. `_run_scheduled_lens` (server.py, schedule-trigger
        # callback) is the only caller that overrides it, with 0.
        return await _run_lens_flow(
            lens, evidence,
            store=sentinel_store, run_decision=_run_decision, execute=execute,
            notify=_notify, act=_act, propose=_propose,
            get_execute_policy=lambda: app.get("execute_policy") or {},
            allow_green_auto=os.environ.get("SENTINEL_ALLOW_GREEN_AUTO", "0")
            in ("1", "true", "yes", "on"),
            record_event=sentinel_store.record_event,
            sentinel_system=SENTINEL_SYSTEM,
            cooldown_sec=cooldown_sec if cooldown_sec is not None
            else int(os.environ.get("SENTINEL_COOLDOWN_SEC", "1800")),
            daily_cap=int(os.environ.get("SENTINEL_DAILY_CAP", "20")),
        )

    app["run_lens"] = _run_lens

    # ── Lenti definite dall'utente (Slice 5b, Task 5): trigger SCHEDULATO ───
    # `register_lens_schedules` (module-level, above) reads `app["run_lens"]`
    # (just bound) and `engine._scheduler` (already started, `engine.start()`
    # ran earlier in this function) to (re)register a per-lens cron/interval
    # job for every enabled schedule-type lens. Exposed on `app` so Task 6's
    # CRUD handlers can re-invoke it after every lens save/delete without a
    # server.py import (avoids a circular import back from api/handlers_*.py).
    app["register_lens_schedules"] = register_lens_schedules
    await register_lens_schedules(app)

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
            allow_green_auto=os.environ.get("SENTINEL_ALLOW_GREEN_AUTO", "0")
            in ("1", "true", "yes", "on"))
        sentinel_store.record_event({
            "ts": _time.time(), "kind": wake.signal_kind, "entity_id": wake.entity_id,
            "verdict": d.verdict, "severity": d.severity,
            "outcome": outcome, "message": d.message})
        return outcome
    app["execute_decision"] = _execute_decision

    # Chat-via-abbonamento (Slice 4b, Task 1): submit-branch for kind="chat"
    # jobs — writes the runner's reply into chat_store instead of actuating
    # the house. chat_store has no separate "conversation_id"; a conversation
    # IS an agent's active session, keyed by agent_id, so that's what the job
    # context carries and what this receives.
    from .chat_store import append_messages as _append_chat_messages
    from .chat_store import _is_toxic_assistant as _is_toxic_chat_reply

    async def _submit_chat_reply(agent_id: str, reply_text: str) -> None:
        if not agent_id or not reply_text:
            return
        # Final-review Fix 3 (Slice 4b): mirror the sync path's two
        # persistence guards (handlers_chat.py, ~line 423) so a reply that
        # arrived via the async runner gets the same treatment as one from
        # the local runner. De-tokenize BEFORE the toxicity check, same order
        # as the sync path, so both the stored history and the toxic-pattern
        # match see real values rather than vault tokens.
        _pseudonymizer = app.get("pseudonymizer")
        if _pseudonymizer is not None:
            reply_text = _pseudonymizer.detokenize(reply_text)
        if _is_toxic_chat_reply(reply_text):
            # Drop silently, same as the sync path: the next turn must not
            # inherit a poisoned/leaked history. There's no HTTP response
            # here to carry a visible error (the caller already got a 202
            # long ago) -- the poll route's chat_reply_skipped handling is
            # the user-facing side of this.
            return
        _append_chat_messages(agent_id, [{"role": "assistant", "content": reply_text}], data_dir)
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
                from .api.handlers_entities import filter_entities
                _inventory = filter_entities(_cache.all_states(), None, None)
                _current = load_policy(data_dir)
                _ctx = build_review_context(snapshot, _inventory, _current)
                _text = await _llm_reason(COVERAGE_REVIEW_SYSTEM, build_review_message(_ctx),
                                          model="auto", max_tokens=1536)
                _suggs = parse_suggestions(_text)

                def _mk_proposal(c):
                    return asyncio.create_task(create_automation_proposal(
                        proposal_store, proposal_type="ha_automation",
                        name=str(c.get("name") or "Brain coverage-review"),
                        description=str(c.get("description") or ""),
                        config=c, routing_reason="brain coverage-review"))

                apply_suggestions(
                    _suggs, data_dir=data_dir, store=_store,
                    inventory_ids={e["entity_id"] for e in _inventory},
                    current_config=_current, create_proposal=_mk_proposal,
                    cap=int(os.environ.get("BRAIN_SUGGEST_CAP", "5")))
        except Exception:
            logger.exception("coverage-review failed")

        if os.environ.get("BRIDGE_ENABLED", "0") in ("1", "true", "yes", "on"):
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

    # ── Ponte push (Piano A): spazzata di fallback per i job scaduti senza risposta dal
    # runner remoto. Se BRIDGE_FALLBACK è attivo, ragiona in locale riusando
    # lo stesso _run_decision (e quindi lo stesso cap del router LLM) delle
    # situazioni sopra — nessun path metrico/actuation nuovo.
    async def _reasoning_sweep() -> None:
        if os.environ.get("BRIDGE_ENABLED", "0") not in ("1", "true", "yes", "on"):
            return
        fallback = os.environ.get("BRIDGE_FALLBACK", "1") in ("1", "true", "yes", "on")
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
    _bridge_enabled = os.environ.get("BRIDGE_ENABLED", "0") in ("1", "true", "yes", "on")
    _chat_via_subscription_cfg = os.environ.get("CHAT_VIA_SUBSCRIPTION", "0") in ("1", "true", "yes", "on")
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
    ha_client.add_state_listener(lambda evt: asyncio.create_task(arrival_watcher.on_state_changed(evt)))

    claude_runner = None
    if api_key:
        claude_runner = ClaudeRunner(
            api_key=api_key,
            dispatcher=dispatcher,
            usage_path=usage_path,
        )

    _usage_base, _usage_ext = os.path.splitext(usage_path)
    _usage_ext = _usage_ext or ".json"

    openai_runner = None
    if openai_api_key:
        openai_runner = OpenAICompatRunner(
            base_url="https://api.openai.com/v1",
            api_key=openai_api_key,
            dispatcher=dispatcher,
            usage_path=f"{_usage_base}_openai{_usage_ext}",
        )

    ollama_runner = None
    if local_model_url and local_model_name:
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
    if openrouter_api_key:
        openrouter_runner = OpenRouterRunner(
            api_key=openrouter_api_key,
            dispatcher=dispatcher,
            usage_path=f"{_usage_base}_openrouter{_usage_ext}",
        )
        logger.info("OpenRouter abilitato (200+ modelli via openrouter.ai)")

    # Store config for /api/models endpoint
    app["openai_api_key"] = openai_api_key
    app["openrouter_api_key"] = openrouter_api_key
    app["local_model_url"] = local_model_url
    app["local_model_name"] = local_model_name

    if any([claude_runner, openai_runner, openrouter_runner, ollama_runner]):
        router = LLMRouter(
            claude=claude_runner,
            openai=openai_runner,
            openrouter=openrouter_runner,
            ollama=ollama_runner,
            strategy=llm_strategy,
            automatic_policy=automatic_policy,
            chat_policy=chat_policy,
        )
        semantic_map.set_router(router)
        app["claude_runner"] = claude_runner  # backward compat (may be None)
        app["llm_router"] = router
        engine.set_claude_runner(router)
        engine.set_task_engine(task_engine)

        # Kick off LLM classification for ambiguous entities (background, non-blocking)
        if ambiguous:
            asyncio.create_task(
                semantic_map._classify_unknown_batch(),
                name="semantic_map_initial_classify",
            )
    else:
        app["claude_runner"] = None
        app["llm_router"] = None


async def _on_cleanup(app: web.Application) -> None:
    from .chat_store import close_all_stores
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
    app.router.add_get("/api/agents", handle_list_agents)
    app.router.add_post("/api/agents", handle_create_agent)
    app.router.add_get("/api/agents/{agent_id}", handle_get_agent)
    app.router.add_put("/api/agents/{agent_id}", handle_update_agent)
    app.router.add_delete("/api/agents/{agent_id}", handle_delete_agent)
    app.router.add_post("/api/agents/{agent_id}/run", handle_run_agent)
    app.router.add_get("/api/entities", handle_list_entities)
    app.router.add_get("/api/suggestions", handle_list_suggestions)
    app.router.add_post("/api/suggestions/{id}/undo", handle_undo_suggestion)
    app.router.add_get("/api/agents/{agent_id}/usage", handle_get_agent_usage)
    app.router.add_post("/api/agents/{agent_id}/usage/reset", handle_reset_agent_usage)
    app.router.add_get("/api/agents/{agent_id}/context-preview", handle_context_preview)
    app.router.add_get("/api/agents/{agent_id}/chat-history", handle_get_chat_history)
    app.router.add_delete("/api/agents/{agent_id}/chat-history", handle_clear_chat_history)
    app.router.add_get("/api/tasks", handle_list_tasks)
    app.router.add_get("/api/tasks/{task_id}", handle_get_task)
    app.router.add_delete("/api/tasks/{task_id}", handle_cancel_task)
    app.router.add_get("/api/models", handle_list_models)
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
        handle_get_gateway_policy, handle_save_gateway_policy,
    )
    app.router.add_get("/api/gateway/policy", handle_get_gateway_policy)
    app.router.add_post("/api/gateway/policy", handle_save_gateway_policy)

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

    # Slice 5b Task 6: user-lens CRUD. Same app-level internal_auth_middleware
    # + csrf_middleware protection as every other /api/* route above -- no
    # per-route auth here, just registration under the same app.router.
    from .api.handlers_lenses import (
        handle_list_lenses, handle_create_lens, handle_update_lens, handle_delete_lens,
    )
    app.router.add_get("/api/lenses", handle_list_lenses)
    app.router.add_post("/api/lenses", handle_create_lens)
    app.router.add_put("/api/lenses/{id}", handle_update_lens)
    app.router.add_delete("/api/lenses/{id}", handle_delete_lens)

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
