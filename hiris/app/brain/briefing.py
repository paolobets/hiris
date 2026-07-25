"""Slice 7 (Maggiordomo) -- deterministic daily briefing bundle, plus the
butler composer that turns the bundle into natural-language text.

Bundle building (Task 1) is pure/read-only: pulls upcoming obligations from
the KnowledgeStore and notable home status (open doors/windows, low
batteries) from the EntityCache, and folds them into a single dict. No LLM,
no network, no writes. Never raises -- any failure on either input source
degrades to an empty section rather than propagating.

Composing (Task 2) turns that bundle into the actual butler briefing text via
an injected LLM callable, GROUNDED (the prompt instructs the model to use
ONLY the bundle data, never invent/infer, never propose actions), with a
deterministic template fallback so a briefing always goes out even if the
LLM is unavailable, returns nothing useful, or raises.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

try:
    from ..proxy._sanitize import sanitize_ha_value as _san  # SEC-024 sanitizer
except Exception:  # pragma: no cover - fallback difensivo
    _san = lambda v: v  # noqa: E731

_OPENING_DEVICE_CLASSES = {"door", "window", "garage_door", "opening"}
_CAP = 20


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _battery_threshold(policy: dict | None, default_pct: int) -> int:
    try:
        return int(policy["detectors"]["battery"]["min_pct"])  # type: ignore[index]
    except Exception:
        return default_pct


def _collect_deadlines(
    knowledge_store, *, today: date, horizon_days: int, allow_sensitive: bool,
) -> tuple[list[dict], int]:
    """Returns (visible_deadlines, hidden_sensitive_count)."""
    if knowledge_store is None:
        return [], 0
    try:
        before = (today + timedelta(days=horizon_days)).strftime("%Y-%m-%d")
        rows = knowledge_store.upcoming_obligations(before=before)
    except Exception:
        return [], 0

    deadlines: list[dict] = []
    hidden_sensitive = 0
    for row in rows or []:
        try:
            sensitivity = row.get("sensitivity") or "normal"
            is_sensitive = sensitivity != "normal"
            if is_sensitive and not allow_sensitive:
                hidden_sensitive += 1
                continue
            due_date = row.get("due_date")
            due = _parse_iso_date(due_date)
            days_left = (due - today).days if due is not None else None
            deadlines.append({
                "content": row.get("content"),
                "due_date": due_date,
                "days_left": days_left,
                "sensitive": is_sensitive,
            })
        except Exception:
            continue

    deadlines.sort(key=lambda d: d.get("due_date") or "")
    return deadlines, hidden_sensitive


def _collect_home_status(
    entity_cache, *, policy: dict | None, battery_default_pct: int,
) -> tuple[list[dict], list[dict]]:
    """Returns (open_now, low_batteries), each capped at 20 entries."""
    if entity_cache is None:
        return [], []
    try:
        states = entity_cache.all_states()
    except Exception:
        return [], []

    threshold = _battery_threshold(policy, battery_default_pct)
    open_now: list[dict] = []
    low_batteries: list[dict] = []

    for entity in states or []:
        try:
            eid = entity.get("id") or entity.get("entity_id") or ""
            if not eid:
                continue

            if eid.startswith("binary_sensor.") and len(open_now) < _CAP:
                device_class = entity.get("device_class")
                if device_class in _OPENING_DEVICE_CLASSES and entity.get("state") == "on":
                    name = entity.get("name") or eid
                    open_now.append({"name": name})
                continue

            if eid.startswith("sensor.") and len(low_batteries) < _CAP:
                device_class = entity.get("device_class")
                unit = entity.get("unit") or ""
                name = entity.get("name") or ""
                is_battery = device_class == "battery" or (
                    unit == "%" and "batter" in name.lower()
                )
                if not is_battery:
                    continue
                try:
                    pct = float(entity.get("state"))
                except (TypeError, ValueError):
                    continue
                if pct < threshold:
                    low_batteries.append({"name": name or eid, "pct": pct})
        except Exception:
            continue

    return open_now[:_CAP], low_batteries[:_CAP]


def build_briefing_bundle(
    knowledge_store,
    entity_cache,
    policy,
    *,
    today: date,
    allow_sensitive: bool,
    horizon_days: int = 7,
    battery_default_pct: int = 20,
) -> dict:
    """Deterministic butler briefing bundle: deadlines from ingested
    documents (obligations) plus notable home status (open doors/windows,
    low batteries). Egress-gated: sensitive deadlines are excluded from the
    list when `allow_sensitive` is False, but still counted. Never raises.
    """
    try:
        deadlines, hidden_sensitive = _collect_deadlines(
            knowledge_store, today=today, horizon_days=horizon_days,
            allow_sensitive=allow_sensitive,
        )
    except Exception:
        deadlines, hidden_sensitive = [], 0

    try:
        open_now, low_batteries = _collect_home_status(
            entity_cache, policy=policy, battery_default_pct=battery_default_pct,
        )
    except Exception:
        open_now, low_batteries = [], []

    return {
        "deadlines": deadlines,
        "home": {"open_now": open_now, "low_batteries": low_batteries},
        "counts": {
            "deadlines": len(deadlines),
            "hidden_sensitive": hidden_sensitive,
            "open_now": len(open_now),
            "low_batteries": len(low_batteries),
        },
        "generated_for": today.isoformat(),
    }


# ---------------------------------------------------------------------------
# Task 2: LLM-composed butler briefing (grounded) + deterministic fallback.
# ---------------------------------------------------------------------------

BRIEFING_SYSTEM = (
    "Sei il maggiordomo digitale di HIRIS: prepari il resoconto quotidiano per il "
    "padrone di casa. Ricevi un riepilogo con scadenze imminenti, porte/finestre "
    "aperte e batterie scariche, e lo racconti con tono cortese, professionale e "
    "sintetico, in italiano. Usa SOLO i dati forniti nel riepilogo: non inventare, "
    "non dedurre e non aggiungere nulla che non sia presente nei dati ricevuti. Se "
    "non c'e' nulla di rilevante da segnalare, dillo brevemente e basta. Sei "
    "puramente informativo: non proporre e non intraprendere alcuna azione, "
    "limitati a riferire quanto ricevuto."
)


def _fmt_days_left(days_left) -> str:
    if not isinstance(days_left, int):
        return ""
    if days_left < 0:
        return f"scaduta da {-days_left} giorni"
    if days_left == 0:
        return "scade oggi"
    if days_left == 1:
        return "scade domani"
    return f"tra {days_left} giorni"


def render_briefing_template(bundle: dict) -> str:
    """Deterministic butler briefing built only from the bundle's real keys
    (deadlines/home.open_now/home.low_batteries -- see build_briefing_bundle
    above). Always returns a non-empty string, even for an empty bundle, so
    a briefing can always go out without the LLM. Defensive against
    malformed entries: never raises."""
    bundle = bundle or {}
    deadlines = bundle.get("deadlines") or []
    home = bundle.get("home") or {}
    open_now = home.get("open_now") or []
    low_batteries = home.get("low_batteries") or []

    lines: list[str] = ["Ecco il resoconto di oggi."]

    if deadlines:
        lines.append("Scadenze in arrivo:")
        for d in deadlines:
            try:
                if not isinstance(d, dict):
                    continue
                content = str(d.get("content") or "").strip()
                if not content:
                    continue
                when = _fmt_days_left(d.get("days_left"))
                if when:
                    lines.append(f"- {content} ({when})")
                else:
                    # Only show a due date we can validate as ISO -- never echo
                    # unparseable free-text from the stored due_date column.
                    _iso = _parse_iso_date(d.get("due_date"))
                    due = _iso.isoformat() if _iso else None
                    lines.append(f"- {content}" + (f" (entro il {due})" if due else ""))
            except Exception:
                continue

    if open_now:
        try:
            names = [str(e.get("name") or "").strip() for e in open_now if isinstance(e, dict)]
            names = [n for n in names if n]
        except Exception:
            names = []
        if names:
            lines.append("Aperture rilevate: " + ", ".join(names) + ".")

    if low_batteries:
        parts: list[str] = []
        for e in low_batteries:
            try:
                if not isinstance(e, dict):
                    continue
                name = str(e.get("name") or "").strip()
                if not name:
                    continue
                pct = e.get("pct")
                parts.append(f"{name} ({pct}%)" if pct is not None else name)
            except Exception:
                continue
        if parts:
            lines.append("Batterie scariche: " + ", ".join(parts) + ".")

    if not deadlines and not open_now and not low_batteries:
        lines.append(
            "Non c'e' nulla di urgente al momento: nessuna scadenza imminente, "
            "nessuna apertura e nessuna batteria scarica da segnalare."
        )

    return "\n".join(lines)


def build_briefing_message(bundle: dict) -> str:
    """Serialize the bundle into an LLM user message. Free-text fields
    (obligation `content`, entity `name`) are sanitized through the shared
    `_san` filter (proxy._sanitize.sanitize_ha_value), exactly like the
    reasoner does for wake-event evidence/context, so a poisoned obligation
    content or entity name cannot inject instructions into the prompt.
    Includes ONLY data present in the bundle -- no external context."""
    bundle = bundle or {}
    deadlines = bundle.get("deadlines") or []
    home = bundle.get("home") or {}
    open_now = home.get("open_now") or []
    low_batteries = home.get("low_batteries") or []
    counts = bundle.get("counts") or {}
    generated_for = bundle.get("generated_for")

    san_deadlines = []
    for d in deadlines:
        if not isinstance(d, dict):
            continue
        # due_date is stored as free-text (TEXT column, no write-time format
        # validation) so a poisoned value that passes the store's lexicographic
        # filter could smuggle raw text into the LLM message. Emit only a
        # re-serialized valid ISO date; anything unparseable becomes None.
        _iso = _parse_iso_date(d.get("due_date"))
        san_deadlines.append({
            "content": _san(d.get("content")),
            "due_date": _iso.isoformat() if _iso else None,
            "days_left": d.get("days_left"),
            "sensitive": bool(d.get("sensitive")),
        })

    san_open_now = [
        {"name": _san(e.get("name"))} for e in open_now if isinstance(e, dict)
    ]
    san_low_batteries = [
        {"name": _san(e.get("name")), "pct": e.get("pct")}
        for e in low_batteries if isinstance(e, dict)
    ]

    payload = {
        "generated_for": generated_for,
        "deadlines": san_deadlines,
        "home": {"open_now": san_open_now, "low_batteries": san_low_batteries},
        "counts": counts,
    }
    return (
        "Riepilogo di oggi (usa SOLO questi dati per comporre il resoconto):\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n\nComponi il resoconto del maggiordomo."
    )


async def compose_briefing(
    bundle: dict, llm_reason, *, model: str = "auto", max_tokens: int = 700,
) -> str:
    """Compose the natural-language butler briefing via the injected
    llm_reason callable -- SAME shape as server.py's _llm_reason, which runs
    with allowed_tools=[] (no actuation from this call). Falls back to the
    deterministic template if the LLM returns empty/whitespace text or
    raises for any reason. Never raises, never returns an empty string."""
    try:
        text = await llm_reason(
            BRIEFING_SYSTEM, build_briefing_message(bundle),
            model=model, max_tokens=max_tokens,
        )
    except Exception:
        return render_briefing_template(bundle)

    if not isinstance(text, str) or not text.strip():
        return render_briefing_template(bundle)
    return text
