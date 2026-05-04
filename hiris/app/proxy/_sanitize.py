"""Sanitize Home Assistant-derived strings before they reach the LLM.

Friendly names, sensor states, knowledge_db annotations and any other field
controllable through HA (or by users tinkering with HA) can carry prompt
injection markers. We strip them before composing the system prompt or the
context block so they cannot rewire the agent's instructions.
"""
import re

_INJECTION_RE = re.compile(
    r'(ignore|forget|disregard|system:|assistant:|<\|im_|SYSTEM\s*PROMPT)',
    re.IGNORECASE,
)


def sanitize_ha_value(v) -> str:
    """Strip injection markers and clamp length. Non-strings pass through stringified."""
    if v is None:
        return ""
    if not isinstance(v, str):
        v = str(v)
    v = v.strip()
    v = _INJECTION_RE.sub("[FILTERED]", v)
    return v[:120]
