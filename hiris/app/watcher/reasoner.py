from __future__ import annotations
import json, re
from typing import Awaitable, Callable
from .signals import WakeEvent, Decision
try:
    from ..proxy._sanitize import sanitize_ha_value as sanitize  # SEC-024 sanitizer
except Exception:  # pragma: no cover - fallback difensivo
    def sanitize(s):  # type: ignore
        return re.sub(r"[<>]", "", str(s))

SENTINEL_SYSTEM = (
    "Sei la Sentinella di HIRIS: valuti un singolo segnale di anomalia domestica. "
    "Decidi se è una vera anomalia e cosa fare. Puoi proporre UNA azione pertinente "
    "e a basso rischio; NON proporre mai azioni su serrature, allarmi, tapparelle, sirene. "
    "Rispondi in italiano e concludi SEMPRE con un blocco ```json``` con i campi "
    "verdict('anomalia'|'falso_positivo'), severity('info'|'warn'|'critico'), message, "
    "action(null oppure {domain,service,entity_id,data})."
)

_JSON_RE = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL)

def _san(v):
    """Recursive deep sanitization."""
    if isinstance(v, str):
        return sanitize(v)
    if isinstance(v, list):
        return [_san(x) for x in v]
    if isinstance(v, dict):
        return {k: _san(x) for k, x in v.items()}
    return v

def build_user_message(wake: WakeEvent, context: dict) -> str:
    ev = _san(dict(wake.evidence))
    ctx = _san(dict(context or {}))
    return (
        f"Segnale: {wake.signal_kind} su {wake.entity_id}\n"
        f"Evidenza: {json.dumps(ev, ensure_ascii=False)}\n"
        f"Contesto: {json.dumps(ctx, ensure_ascii=False)}\n\n"
        "Valuta e rispondi con il blocco json richiesto."
    )

def parse_decision(text: str, default_severity: str = "warn") -> Decision:
    m = list(_JSON_RE.finditer(text or ""))
    if m:
        try:
            obj = json.loads(m[-1].group(1))
            return Decision(
                verdict=str(obj.get("verdict", "anomalia")),
                severity=str(obj.get("severity", default_severity)),
                message=str(obj.get("message", "")).strip() or "(nessun messaggio)",
                action=obj.get("action") if isinstance(obj.get("action"), dict) else None,
            )
        except (ValueError, TypeError):
            pass
    return Decision(verdict="anomalia", severity=default_severity,
                    message=(text or "").strip()[:500] or "(vuoto)", action=None)

async def reason(wake: WakeEvent, *,
                 gather_context: Callable[[WakeEvent], dict],
                 llm_reason: Callable[..., Awaitable[str]],
                 model: str = "auto", max_tokens: int = 1024) -> Decision:
    context = gather_context(wake) or {}
    user = build_user_message(wake, context)
    text = await llm_reason(SENTINEL_SYSTEM, user, model=model, max_tokens=max_tokens)
    return parse_decision(text, default_severity=wake.severity_hint)
