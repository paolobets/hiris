"""Sanitize Home Assistant-derived strings before they reach the LLM.

Friendly names, sensor states, knowledge_db annotations and any other field
controllable through HA (or by users tinkering with HA) can carry prompt
injection markers. We strip them before composing the system prompt or the
context block so they cannot rewire the agent's instructions.
"""
import re

# Markers are phrase-based for the risky verbs (Italian too), NOT bare verbs:
# HIRIS is an Italian smart-home whose insights routinely say things like
# "il sistema ha ignorato l'evento" or "ho dimenticato di..." -- matching a
# lone "ignora"/"dimentica" would garble legitimate memory. We only match the
# imperative injection lead-ins ("ignora le istruzioni", "dimentica tutto"),
# role prefixes, and the classic override phrases, in both EN and IT.
_INJECTION_RE = re.compile(
    r'('
    # English verbs -- word-bounded so they don't fire inside Italian words
    # (bare "ignore" matched "s-ignore", "Il S-ignore degli Anelli").
    r'\bignor(?:e[ds]?|ing)\b|\bforget(?:s|ting)?\b|\bdisregard(?:s|ed|ing)?\b'
    r'|system:|assistant:|<\|im_|SYSTEM\s*PROMPT'
    # Italian role prefixes / system-prompt references
    r'|sistema:|assistente:|prompt\s+di\s+sistema'
    # Italian injection phrases (imperative + object, low false-positive).
    # Up to one adjective may sit between the verb and the noun
    # ("ignora le PRECEDENTI istruzioni"); istruzion[ei] covers ogni-singular.
    r'|ignora\s+(?:le\s+|tutte\s+le\s+|ogni\s+)?(?:\w+\s+)?istruzion[ei]|ignora\s+tutto'
    r'|dimentica\s+(?:tutto|le\s+istruzioni|quanto\s+detto|le\s+regole)'
    r'|scorda\s+(?:tutto|le\s+istruzioni)'
    r'|istruzioni\s+precedenti|nuove\s+istruzioni'
    # Italian role-override lead-ins
    r'|agisci\s+come|comportati\s+come|fingi\s+di\s+essere|fai\s+finta\s+di\s+essere'
    r')',
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
