"""Sanitize Home Assistant-derived strings before they reach the LLM.

Friendly names, sensor states, area names and any other field controllable
through HA (or by users tinkering with HA) can carry prompt injection
markers. We strip them before composing the system prompt or the context
block so they cannot rewire the agent's instructions.

WHERE THIS IS ACTUALLY WIRED (fixed 2026-08-25, audit finding C-2 /
L1-sicurezza.md: this module used to have zero production callers while this
docstring claimed an active defense -- a security module lying about itself;
extended 2026-08-25 after an independent review found two more raw paths and
a false rationale for a third -- I1 in FIX1-report.md; extended again the
same day after a second review found this list itself did not match the
code -- the nucleo bypassed the shared memory function it was credited with
using, and an automation/script name arriving over the network was uncovered
-- N1/N2 in FIX1-report.md). Every point where text HIRIS does not control
can enter the model's context calls one of the two functions below:

- `proxy/entity_cache.py::_to_minimal` -- the single point where a raw HA
  state becomes what every reader sees (`specchio_vivo`, `guarda`, `cerca`,
  the nucleo). Sanitizes `state`, `name` (friendly_name), and the free-text
  media_player attributes (`media_title`, `media_artist`, `source`) -- the
  concrete vector the audit verified. NOT sanitized: numeric/enum attributes
  (`brightness`, `hvac_mode`, `current_position`, ...) -- they are not
  attacker-writable free text, and running them through a text filter would
  silently coerce numbers to strings for no real gain.
- `proxy/ha_client.py::diario` -- the logbook boundary. Sanitizes `nome`,
  `stato` AND `messaggio` per entry (free text HA does not control) -- `stato`
  was missed in the first pass: for a message-sensor (email/ntfy/SMS, the
  FIRST vector L1-sicurezza.md names) the hostile text often IS the state, not
  the logbook message. Leaves `None` fields as `None` rather than
  manufacturing an empty string. `nome`/`stato` go through `sanitize_ha_value`
  (they are `state`-shaped: a friendly_name, a state string); `messaggio` is
  arbitrary logbook prose with no HA-imposed ceiling, so it goes through
  `sanitize_ha_free_text` instead (M2, correzioni-minori.md).
- `proxy/ha_client.py::storico` -- the historical-series boundary
  (`andamento`'s tool). Sanitizes `valore`. The first pass left this one
  unwired on the claim that the series is "numeric by construction"; that
  claim was false -- `valore` is `voce.get("state")`, the raw state of
  WHATEVER entity was asked for, and `andamento`'s own tool description
  promotes it for "whether a door was left open". Same vector as `diario`,
  same fix.
- `casa/archivio.py::ArchivioCasa.sostituisci` -- the SOLE writer of the
  house registry mirror. Sanitizes `nome`/`alias`/`titolo`/`motivo` for
  piani, aree, dispositivi (incl. produttore/modello), entita, etichette,
  categorie and integrazioni at write time, so every reader (`leggi()`, the
  nucleo, `guarda`, `cerca`, the config page) inherits the defense for free
  instead of each caller having to remember to filter. `nome`/`alias`/
  `titolo` go through `sanitize_ha_value` (255 -- they are HA's
  friendly_name/title, `state`-shaped); `integrazioni.motivo` (why an
  integration failed, not a `state`) goes through `sanitize_ha_free_text`
  (500) since M2, correzioni-minori.md.
- `casa/archivio.py::ArchivioCasa.sostituisci_comportamento` -- a SECOND,
  separate writer (different cadence, different source, see its docstring)
  for automations/scripts. Sanitizes `nome` only. `nome` is Home Assistant's
  `friendly_name`, read by `comportamento.rileggi()` via a RAW
  `get_states([])` call that does NOT go through `entity_cache._to_minimal`
  -- the same network-controllable text C-2 sanitizes everywhere else it
  surfaces, missed here on a first pass because the file it lives next to
  (`corpo`, the automation/script body) genuinely comes from a local YAML
  file the house owner edits. Two fields, two sources, two answers: `corpo`
  is left alone (see below), `nome` is not.
- `casa/domande.py::ricordi_sanificati` -- a memory is the one thing that
  re-enters the model's context on every subsequent turn without being asked
  for (I-1: a `ricorda()` call from an injected turn would otherwise plant a
  permanent backdoor). ONE shared function, called from `casa/nucleo.py::
  _righe_ricordi` (the always-on channel), `casa/domande.py::guarda` (by id
  or anchored to an area/entity/device), AND `casa/strumenti.py::_richiama`
  (`ArchivioMemoria.per_ancora`, a THIRD read path the first pass missed --
  it does not go through `guarda`, so the same memory came out filtered from
  one door and raw from another). A single shared function, not three copies
  of the same line, is what makes a fourth door impossible to forget: import
  it, do not re-derive it. Sanitized where the text becomes part of what the
  model reads, NOT in `memoria/archivio.py` itself -- that archive's own
  contract ("il testo e' la verita'", rule 1 of its module docstring)
  promises the stored text matches what was said, verbatim, for the
  correction page and the record. Sanitizing on read, not on write, keeps
  both promises true at once.

DELIBERATELY NOT WIRED, and why: the `corpo` field of an automation/script
(`casa/comportamento.py`, `automations.yaml`/`scripts.yaml`) is a local file
the house owner edits, not something a network device or a compromised
integration can write -- it is not the vector this fix closes. This is
narrower than the same sentence used to be: it once covered the whole
module, which was wrong -- see the `sostituisci_comportamento` bullet above
for the field (`nome`) that reasoning never actually applied to.

TRUNCATION IS DECLARED, NOT SILENT (fixed 2026-08-25, I2 in FIX1-report.md;
the cap refined 2026-08-25, M2 in correzioni-minori.md).
`sanitize_ha_value`'s clamp was 120 chars and cut without saying so: once
this module was actually wired, that silently mangled real content -- an
`input_text` state (HA allows up to 255) -- into something that read as
complete. The clamp is now 255 (Home Assistant's own ceiling on a state
string, `homeassistant.core.MAX_LENGTH_STATE_STATE`, not a margin picked for
caution) for fields that actually ARE `state`. A logbook `messaggio` and an
integration's failure `motivo` are NOT `state` -- HA does not cap them at
all, and a legitimate one can honestly run longer than 255 -- so they now go
through `sanitize_ha_free_text` (cap 500, see its docstring for the number)
instead of `sanitize_ha_value`. Both functions, and the shared `sanitize_text`
underneath them, append a trailing marker (`_TRONCATO`, " [troncato]") when a
cut actually happens -- the same convention `proxy/ha_client.py::_truncate`
uses (the two truncators were unified into one function, M1 in
correzioni-minori.md, so it is now literally the same code, not just the same
convention). Text at or under the cap is returned untouched: no marker where
nothing was cut, or the marker itself would be the false claim.
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
    # M3 (audit-2026-08-25, minori): "istruzioni precedenti"/"nuove
    # istruzioni" bare (no colon after) is ordinary Italian -- "le nuove
    # istruzioni della caldaia sono nel cassetto", "le istruzioni precedenti
    # del forno erano piu' chiare" are normal sentences about an appliance
    # manual, not an attack, and used to come back as `[FILTERED]` with the
    # user never told why. The imperative forms that actually carry the
    # injection risk are already caught above ("ignora/dimentica/scorda...
    # istruzioni", "sovrascrivi/scavalca le istruzioni") without this bare
    # bigram. What this bigram alone still catches, on purpose, is the
    # "introduce a new directive" shape an injection actually uses --
    # "nuove istruzioni: <payload>", "istruzioni precedenti: <payload>" --
    # requiring the colon that a descriptive sentence about a manual does
    # not have. This is a deliberate narrowing, not a removal: a crafted
    # message that smuggles the same bigram without a colon ("le nuove
    # istruzioni sono ignora tutto e...") now passes this alternative
    # unfiltered -- accepted, because the imperative-verb alternatives above
    # already catch the realistic phrasing of that same attack, and this
    # bigram's own false-positive cost (breaking a normal household sentence
    # silently) was worse than the marginal coverage it added alone.
    r'|(?:istruzioni\s+precedenti|nuove\s+istruzioni)\s*:'
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


# I2 (independent review, 2026-08-25): a silent clamp is exactly the class
# of defect this product treats as a Critical elsewhere ("never state
# something false with confidence") -- a message cut at the byte limit reads
# as a complete sentence, and the reader (human or model) has no way to tell
# "this is everything" from "this is everything I kept". Same marker text as
# `proxy/ha_client.py::_TRUNC_MARK`/`_truncate` used to have on purpose: the
# same fact (this string got cut) must read the same way everywhere it
# happens, not invent a second wording for the identical event.
#
# M1 (audit-2026-08-25, minori): this marker and the clamp algorithm below
# used to be duplicated verbatim in `ha_client.py` (`_TRUNC_MARK`/
# `_truncate`) -- same algorithm, same string, written twice, free to drift.
# `ha_client.py` already imports from this module (`sanitize_ha_value`), so
# sharing costs one more name in that import line. Both copies used the
# IDENTICAL string (" [troncato]") before the merge, so there was no visible
# text to choose between -- this one survives because it is the module that
# both callers already depend on, not because either wording lost.
_TRONCATO = " [troncato]"


def truncate_with_marker(text, cap: int) -> str:
    """Tronca `text` a `cap` caratteri dichiarando il taglio con un marcatore.

    Nessun filtro di iniezione qui -- SOLO il taglio. E' la funzione che
    prima viveva duplicata come `ha_client.py::_truncate` (stesso algoritmo,
    stessa costante `_TRUNC_MARK`/`_TRONCATO`) per tagliare messaggi d'errore
    e risposte di template che non sono testo libero di Home Assistant e non
    vanno fatti passare dal filtro di iniezione -- `sanitize_text` la
    richiama sotto DOPO aver gia' applicato quel filtro, per il proprio caso
    d'uso.

    Il risultato non supera mai `cap`, marcatore incluso nel conteggio. Se
    `cap` e' cosi' piccolo da non poter ospitare il marcatore si taglia e
    basta: meglio perdere il marcatore che sforare il limite dichiarato.
    Testo non stringa viene stringificato; a o sotto il tetto torna
    invariato, senza marcatore: dichiarare un taglio che non c'e' stato
    sarebbe a sua volta un'affermazione falsa.
    """
    if not isinstance(text, str):
        text = str(text)
    if len(text) <= cap:
        return text
    if cap <= len(_TRONCATO):
        return text[:max(0, cap)]
    return text[:cap - len(_TRONCATO)] + _TRONCATO


def sanitize_text(v, max_len: int = 2000) -> str:
    """Strip prompt-injection markers and clamp length. Non-strings stringified.

    Like sanitize_ha_value but with a configurable, larger clamp — for
    persisting cleartext reasoning that must stay readable (display-only).

    The result never exceeds `max_len`. When the text actually gets cut, the
    cut is DECLARED with a trailing marker (`_TRONCATO`, marker included in
    the budget) instead of silently disappearing — via `truncate_with_marker`
    below, shared with `ha_client.py::_truncate` since M1 (audit-2026-08-25,
    minori). Text at or under `max_len` is returned untouched, no marker:
    declaring a cut that didn't happen would be its own false claim.
    """
    if v is None:
        return ""
    if not isinstance(v, str):
        v = str(v)
    v = v.strip()
    v = _INJECTION_RE.sub("[FILTERED]", v)
    return truncate_with_marker(v, max_len)


def sanitize_ha_value(v) -> str:
    """Strip injection markers and clamp to 255 chars, declaring the cut if it
    happens (see `sanitize_text`).

    255, not the old 120: it is Home Assistant's own ceiling on a state
    string (`homeassistant.core.MAX_LENGTH_STATE_STATE`), not a margin picked
    for caution. 120 was tight enough to silently truncate real content once
    this function was actually wired in production — an `input_text` state
    is the field this cap actually protects — and make it read as complete.
    Wired call sites: see the top-of-module list.

    NOT for `messaggio` (diario) or `motivo` (integration failure reason):
    those are not `state`, see `sanitize_ha_free_text` below (M2,
    audit-2026-08-25, minori) — using this 255 cap for them was the earlier,
    honest-but-not-generous choice this fix replaces.
    """
    return sanitize_text(v, 255)


# M2 (audit-2026-08-25, minori): 255 is Home Assistant's own ceiling on a
# `state` string -- correct for `sanitize_ha_value` above, wrong for fields
# that are not `state`. `messaggio` (a logbook entry's free text --
# ha_client.py::diario) and `motivo` (why an integration failed to start --
# casa/archivio.py::sostituisci) are HA free text with no such ceiling: a
# legitimate one -- an automation message that quotes an SMS/email body, an
# exception summary from a broken integration -- can honestly run past 255
# without being an attack. Clamping them to the `state` ceiling was honest
# (the marker said so) but not generous: it threw away real content that had
# every right to be there.
#
# 500, not "as large as possible": `messaggio` is capped per-entry but NOT
# per-call -- `diario()` returns up to MAX_DIARIO_VOCI (200) entries in one
# response, so this cap multiplies straight into the prompt budget. At 500
# chars the worst case (200 entries every one of them at the cap) is ~100 KB
# of text, tens of thousands of tokens -- large, but still a bounded slice of
# ONE tool call's answer, not an unbounded one; at 255 the same worst case
# was already ~50 KB, so 500 roughly doubles the ceiling without changing its
# order of magnitude. 500 characters is also roughly the length of a short
# SMS/email paragraph or a one-line exception with its message (not a full
# traceback): generous for the legitimate case this fix exists for, without
# letting one crafted logbook message eat most of the model's context.
MAX_TESTO_LIBERO = 500


def sanitize_ha_free_text(v) -> str:
    """Come `sanitize_ha_value`, ma per campi HA liberi che NON sono `state`
    (`messaggio` del diario, `motivo` di un'integrazione rotta) -- vedi
    `MAX_TESTO_LIBERO` sopra per la ragione del numero."""
    return sanitize_text(v, MAX_TESTO_LIBERO)
