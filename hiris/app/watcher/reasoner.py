from __future__ import annotations
import inspect
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

SITUATION_HOLISTIC_SYSTEM = (
    "Sei il cervello di HIRIS in revisione olistica: ricevi una fotografia della casa "
    "(presenza, meteo, sicurezza, salute impianto). Segnala SOLO ciò che merita attenzione; "
    "non elencare lo stato normale. Puoi proporre UNA azione a basso rischio pertinente; "
    "NON proporre mai azioni su serrature, allarmi, tapparelle, sirene. Rispondi in italiano "
    "e concludi SEMPRE col blocco ```json``` con verdict/severity/message/action."
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
    # ATTENZIONE: il ritratto va estratto PRIMA di _san. sanitize_ha_value
    # tronca ogni valore a 120 caratteri: un ritratto da ~1800 arriverebbe al
    # prompt mozzato alla prima riga, in silenzio e con i test verdi. E' gia'
    # sanificato alla fonte, stringa per stringa (brain/portrait.py: sia
    # notable_state sia _meta passano da sanitize_ha_value, cosi' come i nomi
    # area).
    _raw_ctx = dict(context or {})
    portrait = _raw_ctx.pop("portrait", None)
    ctx = _san(_raw_ctx)
    memory = ctx.pop("memory", None)
    # fetta 2b Task 2: rides alongside "memory", popped the same way and for
    # the same reason (it must not leak into the JSON "Contesto:" block). A
    # bool survives `_san` untouched (not a str/list/dict), so -- unlike the
    # portrait -- there is no 120-char-truncation trap to dodge here; it only
    # needs to travel with `memory`, not be extracted before sanitizing.
    # Missing/None (a context built without the flag) is treated as NOT
    # by-meaning: absent provenance must not earn the "relevant" heading.
    by_meaning = ctx.pop("memory_by_meaning", None)
    portrait_block = ""
    if isinstance(portrait, str) and portrait.strip():
        # "" significa "nessun blocco": e' il contratto che tiene il messaggio
        # identico a prima quando il ritratto non c'e'.
        portrait_block = f"{portrait.strip()}\n\n"
    memory_block = ""
    if isinstance(memory, list) and memory:
        # Snippets are rendered raw (not JSON-encoded like ev/ctx), so flatten
        # each to a single line: collapsing all whitespace/newlines removes the
        # only way a crafted insight could break the prompt's line structure or
        # open a fake ``` fence (sanitize_ha_value clamps length but keeps
        # newlines/backticks). Empty-after-flatten snippets are dropped.
        flat = [" ".join(str(s).split()) for s in memory]
        lines = "\n".join(f"- {s}" for s in flat if s)
        if lines:
            # The heading must tell the truth about how these snippets were
            # picked: "Cosa so di rilevante" only when KnowledgeStore.search
            # actually compared meanings (a working embedder). When it
            # degraded to the most recent rows instead (no embedder -- the
            # factory default -- or a failed one), labelling that block
            # "relevant" would make the model repeat a false claim to the
            # user; "Ultimi ricordi" says what it actually is.
            heading = "Cosa so di rilevante:" if by_meaning else "Ultimi ricordi:"
            memory_block = f"{heading}\n{lines}\n\n"
    return (
        f"Segnale: {wake.signal_kind} su {wake.entity_id}\n"
        f"Evidenza: {json.dumps(ev, ensure_ascii=False)}\n"
        f"Contesto: {json.dumps(ctx, ensure_ascii=False)}\n\n"
        f"{portrait_block}"
        f"{memory_block}"
        "Valuta e rispondi con il blocco json richiesto."
    )

VERDICT_ANOMALY = "anomalia"
VERDICT_FALSE_POSITIVE = "falso_positivo"
VERDICTS = (VERDICT_ANOMALY, VERDICT_FALSE_POSITIVE)

# Consolidamento 1.4: soglia UNICA per il testo grezzo riportato come
# messaggio quando non c'e' nulla da interpretare. Prima erano due (400 nel
# runner, 500 qui) senza alcuna ragione dichiarata. Si tiene la piu' ampia:
# quel testo e' l'unica traccia che l'utente vede di una risposta che il
# modello ha sbagliato a formattare, quindi troncare di meno aiuta a capire
# cosa e' successo. Non e' un parametro perche' nessun chiamante ha bisogno
# di una soglia propria; il costo di un messaggio piu' lungo e' solo estetico
# (chi lo consegna a Home Assistant sanifica e ritronca per conto suo).
FALLBACK_MESSAGE_MAX = 500


def parse_decision(text: str, default_severity: str = "warn",
                   default_verdict: str = VERDICT_ANOMALY) -> Decision:
    """Legge l'ultimo blocco ```json``` della risposta del modello e ne ricava
    una Decision. Non solleva mai.

    UNICA implementazione (consolidamento 1.4). Prima ne esisteva una copia in
    `agent/runner.py` con lo stesso ingresso e la stessa espressione regolare
    ma la decisione OPPOSTA di fronte al dubbio: una divergenza silenziosa fra
    due file, non una scelta dichiarata. Ora la scelta e' `default_verdict`, e
    chi chiama la dichiara.

    `default_verdict` e' il verdetto usato quando la risposta non e'
    interpretabile: nessun blocco json, json non valido, json che non e' un
    oggetto, oppure oggetto senza il campo `verdict`. Sono tutti lo stesso
    caso -- il modello non ha detto cosa pensa -- e vanno trattati uguale.
    I due percorsi che chiamano questa funzione vogliono l'opposto, ed
    entrambi hanno ragione:

    - Sentinella in-process (`reason` qui sotto, e gli Agentbot che ci passano
      sopra): default "anomalia". Sorveglia la casa; un modello che risponde
      male non deve tradursi in silenzio. Il testo grezzo diventa il messaggio
      e l'utente viene avvisato. Il costo del dubbio resta una notifica e non
      un comando, perche' senza `action` l'esecutore (`executor.execute`) puo'
      solo notificare.
    - Runner remoto (`agent/runner.py`): default "falso_positivo". Li' la
      Decisione arriva a HIRIS attraverso la rete e viene applicata da
      `_execute_decision` (server.py), che e' gia' fail-closed sul verdetto
      (un verdetto assente o sconosciuto degrada a "falso_positivo" = no-op).
      Il runner si allinea a monte: se non capisce, non chiede di agire.

    Un `default_verdict` fuori da VERDICTS ricade sul piu' prudente
    ("falso_positivo"): un valore inatteso non deve poter aprire la strada
    all'attuazione."""
    if default_verdict not in VERDICTS:
        default_verdict = VERDICT_FALSE_POSITIVE
    m = list(_JSON_RE.finditer(text or ""))
    if m:
        try:
            obj = json.loads(m[-1].group(1))
        except (ValueError, TypeError):
            obj = None
        # Il blocco puo' contenere una lista o uno scalare: senza questa
        # guardia `obj.get` sollevava AttributeError, che non e' fra le
        # eccezioni catturate -- il ragionatore crashava invece di ricadere
        # sul fallback.
        if isinstance(obj, dict):
            action = obj.get("action")
            return Decision(
                verdict=str(obj.get("verdict") or default_verdict),
                severity=str(obj.get("severity") or default_severity),
                message=str(obj.get("message", "")).strip() or "(nessun messaggio)",
                action=action if isinstance(action, dict) else None,
            )
    return Decision(verdict=default_verdict, severity=default_severity,
                    message=(text or "").strip()[:FALLBACK_MESSAGE_MAX] or "(vuoto)",
                    action=None)

async def reason(wake: WakeEvent, *,
                 gather_context: Callable[[WakeEvent], dict],
                 llm_reason: Callable[..., Awaitable[str]],
                 model: str = "auto", max_tokens: int = 1024,
                 system: str = SENTINEL_SYSTEM) -> Decision:
    context = gather_context(wake)
    if inspect.isawaitable(context):
        context = await context
    context = context or {}
    user = build_user_message(wake, context)
    text = await llm_reason(system, user, model=model, max_tokens=max_tokens)
    return parse_decision(text, default_severity=wake.severity_hint)
