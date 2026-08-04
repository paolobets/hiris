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
    "Per coverage, config e' una voce pronta, es. {detector:'fridge_temp', entity:'sensor.x', max_temp_c:8}. "
    "Per management, config DEVE essere una configurazione di automazione Home Assistant "
    "completa e applicabile (alias, trigger/triggers, action/actions): e' cio' che verra' "
    "scritto in Home Assistant se l'utente approva. Se non hai un'automazione completa da "
    "proporre, usa kind 'coverage' oppure ometti il suggerimento."
)
_JSON_RE = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL)

def build_review_context(snapshot, inventory, current_config, memory=None,
                         memory_by_meaning=False, portrait=None) -> dict:
    inv = [{"entity_id": e.get("entity_id"), "friendly_name": _san(e.get("friendly_name") or ""),
            "domain": e.get("domain"), "device_class": e.get("device_class")} for e in (inventory or [])]
    # Review C/#4: sanitize the HA-health/error-log snapshot through the SAME
    # filter the sibling bridge path applies to this exact snapshot dict
    # (server.py's _holistic_reason, BRIDGE_ENABLED branch: `{k: (_san(v) if
    # isinstance(v, str) else v) ...}`) -- otherwise raw health/error text
    # (e.g. HA error_log top_errors) reaches this LLM prompt unfiltered while
    # the bridge path filters it, an injection-amplifier gap for finding #6.
    san_snapshot = {k: (_san(v) if isinstance(v, str) else v) for k, v in (snapshot or {}).items()}
    ctx = {"snapshot": san_snapshot, "inventory": inv, "current": current_config or {}}
    if memory:
        # Slice 6b Task 5: bounded, home-scoped memory snippets (see
        # reasoner_memory.py / server.py's _holistic_reason). Only added when
        # non-empty so absent/empty memory keeps the context (and therefore
        # build_review_message's output) identical to before this change.
        ctx["memory"] = list(memory)
        # fetta 2b Task 3: `memory_by_meaning` rides alongside `memory`, same
        # discipline (added only when there is a memory block to label) --
        # mirrors reasoner.py's build_user_message / server.py's
        # _gather_context for the per-event path. `relevant_memory()` returns
        # a `MemoryRecall` dataclass, not a bare list; the caller is expected
        # to pass `.snippets` as `memory` and `.by_meaning` here, so this
        # context is built the same way regardless of whether the store
        # compared meanings or degraded to the most recent rows.
        ctx["memory_by_meaning"] = bool(memory_by_meaning)
    if isinstance(portrait, str) and portrait.strip():
        # Solo-se-non-vuoto, come per `memory`: mantiene byte-identico il
        # messaggio quando il ritratto non e' disponibile (test di
        # byte-identita' in tests/test_coverage_review_memory.py).
        ctx["portrait"] = portrait.strip()
    return ctx

def build_review_message(context) -> str:
    ctx = dict(context or {})
    # Rendered as a readable bullet block below (not JSON-encoded like the
    # rest of the context), so pop it before json.dumps -- mirrors
    # reasoner.py's build_user_message (Slice 6b Task 3).
    memory = ctx.pop("memory", None)
    # fetta 2b Task 3: pops alongside `memory`, same reason (must not leak
    # into the JSON blob below). Missing (a context built without the flag)
    # is treated as NOT by-meaning: absent provenance must not earn the
    # "relevant" heading -- same default as reasoner.py's build_user_message.
    by_meaning = ctx.pop("memory_by_meaning", None)
    memory_block = ""
    if isinstance(memory, list) and memory:
        # Sanitize each snippet through the SAME injection filter/clamp the
        # per-wake path applies (reasoner.build_user_message runs _san over the
        # whole context before rendering) so a poisoned insight can't smuggle
        # an instruction-override phrase here, THEN flatten to a single line so
        # collapsed whitespace/newlines can't break structure / open a ``` fence.
        flat = [" ".join(str(_san(s)).split()) for s in memory]
        lines = "\n".join(f"- {s}" for s in flat if s)
        if lines:
            # The heading must tell the truth about how these snippets were
            # picked: "Cosa so di rilevante" only when KnowledgeStore.search
            # actually compared meanings (a working embedder). When it
            # degraded to the most recent rows instead (no embedder -- the
            # factory default -- or a failed one), labelling that block
            # "relevant" would make the model repeat a false claim to the
            # user; "Ultimi ricordi" says what it actually is. Same string,
            # same rule, as reasoner.py's build_user_message -- so the two
            # paths cannot drift apart in what they tell the model.
            heading = "Cosa so di rilevante:" if by_meaning else "Ultimi ricordi:"
            memory_block = f"{heading}\n{lines}\n\n"
    portrait = ctx.pop("portrait", None)
    portrait_block = ""
    if isinstance(portrait, str) and portrait.strip():
        portrait_block = f"{portrait.strip()}\n\n"
    return ("Inventario + config attuale:\n" + json.dumps(ctx, ensure_ascii=False)
            + "\n\n" + portrait_block + memory_block
            + "Proponi coperture/gestioni col blocco json richiesto.")

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
