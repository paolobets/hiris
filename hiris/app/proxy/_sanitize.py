"""Sanitize Home Assistant-derived strings before they reach the LLM.

Friendly names, sensor states, area names and any other field controllable
through HA (or by users tinkering with HA) can carry prompt injection
markers. We strip them before composing the system prompt or the context
block so they cannot rewire the agent's instructions.
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
    # Structured chat-template / instruction-format tokens used to smuggle a
    # fake role turn into the context: LLaMA/Mistral [INST]..[/INST], any
    # ChatML-or-similar <|role|> special token (<|system|>, <|user|>,
    # <|assistant|>, <|endoftext|>, <|eot_id|>, ...; <|im_...| above already
    # covered a subset), and Alpaca-style "### Instruction"/"### System"
    # headers. These never occur in legitimate HA friendly names, states or
    # annotations, so -- unlike the bare-verb English case above -- no
    # word-boundary discipline is needed: matching broadly here carries no
    # realistic false-positive cost. NOTE: the "###" alternative deliberately
    # only fires for the classic English Alpaca/injection shape
    # ("### Instruction"/"### System"), NOT bare "###" or Italian headers
    # ("### Istruzioni installazione", "### Sistema di allarme") -- those are
    # ordinary markdown in user notes and must survive.
    r'|\[/?INST\]|<\|[a-zA-Z_]+\|>|###\s*(?:system|instructions?)\b'
    # "override"/"bypass" -- phrase-scoped, NOT bare-word. Unlike the
    # injection-only verbs above, both are also ordinary Italian/English
    # vocabulary on their own ("override del termostato", "bypass
    # chirurgico", "ho fatto un bypass ieri") -- bare-word matching would
    # garble smart-home and everyday phrasing. Only the imperative +
    # system-prompt/instructions/rules-target shape (the actual injection
    # pattern) is matched, mirroring the ignora/dimentica phrase discipline
    # above. This is a deliberate under-match: "override the light schedule"
    # or "bypass the alarm sensor" will NOT be filtered.
    # "overrid(e|es|ed|ing|den)" spells all inflections: "override" drops the
    # trailing -e before -ing/-en, so a naive "override(?:...ing)?" would miss
    # "overriding"/"overridden". "bypass" keeps its stem, so bypass(es|ed|ing).
    r'|\b(?:overrid(?:e|es|ed|ing|den)|bypass(?:es|ed|ing)?)\s+(?:the\s+|all\s+|your\s+)?'
    r'(?:system\s+prompt|instructions?|restrictions?|rules?|safeguards?|security)\b'
    r'|bypassa(?:re)?\s+(?:le\s+|tutte\s+le\s+)?(?:istruzioni|regole|restrizioni)'
    r'|sovrascrivi\s+(?:le\s+)?istruzioni|scavalca\s+(?:le\s+)?istruzioni'
    r')',
    re.IGNORECASE,
)


def sanitize_text(v, max_len: int = 2000) -> str:
    """Strip prompt-injection markers and clamp length. Non-strings stringified.

    Like sanitize_ha_value but with a configurable, larger clamp — for
    persisting cleartext reasoning that must stay readable (display-only).
    """
    if v is None:
        return ""
    if not isinstance(v, str):
        v = str(v)
    v = v.strip()
    v = _INJECTION_RE.sub("[FILTERED]", v)
    return v[:max_len]


def sanitize_ha_value(v) -> str:
    """Strip injection markers and clamp to 120 chars (HA attribute values)."""
    return sanitize_text(v, 120)
