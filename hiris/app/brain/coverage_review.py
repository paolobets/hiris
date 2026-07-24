from __future__ import annotations
import json, re
try:
    from ..proxy._sanitize import sanitize_ha_value as _san
except Exception:
    _san = lambda v: v  # noqa: E731

COVERAGE_REVIEW_SYSTEM = (
    "Sei il cervello di HIRIS che rivede la copertura della casa. Ricevi l'inventario "
    "delle entita' (per tipo) e la configurazione di sorveglianza attuale. Trova BUCHI "
    "di copertura (cose che dovrebbero essere sorvegliate e non lo sono) e OPPORTUNITA' "
    "di gestione. Proponi SOLO entita' presenti nell'inventario e SOLO cio' che NON e' "
    "gia' configurato. Concludi SEMPRE con un blocco ```json``` con "
    "{suggestions:[{kind:'coverage'|'management', title, rationale, config}]}. "
    "Per coverage, config e' una voce pronta, es. {detector:'fridge_temp', entity:'sensor.x', max_temp_c:8}."
)
_JSON_RE = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL)

def build_review_context(snapshot, inventory, current_config, memory=None) -> dict:
    inv = [{"entity_id": e.get("entity_id"), "friendly_name": _san(e.get("friendly_name") or ""),
            "domain": e.get("domain"), "device_class": e.get("device_class")} for e in (inventory or [])]
    ctx = {"snapshot": snapshot or {}, "inventory": inv, "current": current_config or {}}
    if memory:
        # Slice 6b Task 5: bounded, home-scoped memory snippets (see
        # reasoner_memory.py / server.py's _holistic_reason). Only added when
        # non-empty so absent/empty memory keeps the context (and therefore
        # build_review_message's output) identical to before this change.
        ctx["memory"] = list(memory)
    return ctx

def build_review_message(context) -> str:
    ctx = dict(context or {})
    # Rendered as a readable bullet block below (not JSON-encoded like the
    # rest of the context), so pop it before json.dumps -- mirrors
    # reasoner.py's build_user_message (Slice 6b Task 3).
    memory = ctx.pop("memory", None)
    memory_block = ""
    if isinstance(memory, list) and memory:
        # Flatten each snippet to a single line: collapsing all
        # whitespace/newlines removes the only way a crafted insight could
        # break the prompt's line structure or open a fake ``` fence.
        flat = [" ".join(str(s).split()) for s in memory]
        lines = "\n".join(f"- {s}" for s in flat if s)
        if lines:
            memory_block = f"Cosa so di rilevante:\n{lines}\n\n"
    return ("Inventario + config attuale:\n" + json.dumps(ctx, ensure_ascii=False)
            + "\n\n" + memory_block + "Proponi coperture/gestioni col blocco json richiesto.")

def parse_suggestions(text) -> list[dict]:
    m = list(_JSON_RE.finditer(text or ""))
    if not m:
        return []
    try:
        obj = json.loads(m[-1].group(1))
    except (ValueError, TypeError):
        return []
    sugg = obj.get("suggestions") if isinstance(obj, dict) else None
    if not isinstance(sugg, list):
        return []
    out = []
    for s in sugg:
        if isinstance(s, dict) and s.get("kind") in ("coverage", "management") and isinstance(s.get("config"), dict):
            out.append({"kind": s["kind"], "title": str(s.get("title", ""))[:120],
                        "rationale": str(s.get("rationale", ""))[:500], "config": s["config"]})
    return out
