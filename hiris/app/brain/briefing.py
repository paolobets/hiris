"""Slice 7 (Maggiordomo) -- deterministic daily briefing bundle, plus the
butler composer that turns the bundle into natural-language text.

Bundle building (Task 1) is pure/read-only: pulls upcoming obligations from
the KnowledgeStore, open doors/windows from the EntityCache and low batteries
from the AdvisoryStore, and folds them into a single dict. No LLM, no network,
no writes. Never raises -- any failure on either input source degrades to an
empty section rather than propagating.

Le batterie scariche NON si calcolano qui. Il fatto "questa batteria e'
scarica" ha una sola fonte di verita': il controllo di salute del Brain
(brain/health_checks.check_low_battery), i cui esiti finiscono in
`AdvisoryStore`. Il briefing li rilegge. Prima erano due calcoli distinti, con
due soglie diverse, e l'utente poteva sentirsi dire due cose diverse a seconda
di dove guardava. Conseguenze accettate: le batterie riflettono l'ultima
scansione del Brain (cadenza di mezz'ora) invece dell'istante della richiesta,
e la soglia in vigore e' solo quella del controllo -- `detectors.battery.min_pct`
non governa piu' il briefing.

Composing (Task 2) turns that bundle into the actual butler briefing text via
an injected LLM callable, GROUNDED (the prompt instructs the model to use
ONLY the bundle data, never invent/infer, never propose actions), with a
deterministic template fallback so a briefing always goes out even if the
LLM is unavailable, returns nothing useful, or raises.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from .advisory_store import STATI_ATTIVI
from .health_checks import BATTERIA_TITOLO_PREFISSO, CHECK_BATTERIA
from ..proxy.entity_cache import inventario_leggibile

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


def _collect_deadlines(
    knowledge_store, *, today: date, horizon_days: int, allow_sensitive: bool,
    owner: str = "home",
) -> tuple[list[dict], int]:
    """Returns (visible_deadlines, hidden_sensitive_count)."""
    if knowledge_store is None:
        return [], 0
    try:
        before = (today + timedelta(days=horizon_days)).strftime("%Y-%m-%d")
        # Review C/#2: the SCHEDULED briefing/nudges are a HOME-WIDE broadcast
        # (single push target, no per-user delivery -- see server.py's
        # _briefing_notify/ha_push), so they pass the default owner="home" and
        # only genuinely shared obligations are included (without it,
        # upcoming_obligations returns EVERY owner's rows and a user's private
        # obligation would leak into the shared briefing). The on-demand chat
        # tool, which HAS the caller's identity, passes owner=user_id so the
        # user sees their OWN private obligations plus home ones.
        rows = knowledge_store.upcoming_obligations(before=before, owner=owner)
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


def _collect_open_now(entity_cache) -> tuple[list[dict], bool]:
    """Porte e finestre aperte adesso, dalla cache delle entita', al piu' 20.

    Ritorna `(aperture, lette)`. `lette` e' False quando non si e' potuto
    guardare -- cache assente, mai caricata (vedi `EntityCache.loaded`) o che
    solleva: un elenco vuoto in quei casi diventerebbe "nessuna apertura", cioe'
    un'affermazione sulla casa che nessuno ha verificato. Il maggiordomo deve
    poter dire "non ho potuto controllare", come gli strumenti di chat che
    leggono lo stesso inventario.

    Questa parte resta un calcolo istantaneo: l'apertura di una porta e' una
    condizione che cambia da un minuto all'altro e nessun controllo del Brain
    la sorveglia.
    """
    if not inventario_leggibile(entity_cache):
        return [], False
    try:
        states = entity_cache.all_states()
    except Exception:
        return [], False

    open_now: list[dict] = []
    for entity in states or []:
        try:
            eid = entity.get("id") or entity.get("entity_id") or ""
            if not eid or not eid.startswith("binary_sensor."):
                continue
            if entity.get("device_class") not in _OPENING_DEVICE_CLASSES:
                continue
            if entity.get("state") != "on":
                continue
            open_now.append({"name": entity.get("name") or eid})
            if len(open_now) >= _CAP:
                break
        except Exception:
            continue

    return open_now, True


def _nome_batteria(riga: dict, evidenza: dict) -> str:
    """Nome del dispositivo da citare, preso dall'evidenza della segnalazione.

    `check_low_battery` scrive il nome amichevole in `evidence["name"]`: e' un
    dato, non testo destinato all'utente, quindi non cambia il giorno in cui
    qualcuno riscrive o traduce il titolo della segnalazione.

    Ripiego per le righe salvate prima che quel campo esistesse -- lo store e'
    persistente e quelle righe esistono davvero: si toglie dal titolo il
    prefisso condiviso con il controllo, poi si prova l'identificativo, e in
    ultima istanza resta il titolo cosi' com'e'.
    """
    nome_evidenza = evidenza.get("name")
    if isinstance(nome_evidenza, str) and nome_evidenza.strip():
        return nome_evidenza.strip()

    titolo = str(riga.get("title") or "").strip()
    if titolo.startswith(BATTERIA_TITOLO_PREFISSO):
        nome = titolo[len(BATTERIA_TITOLO_PREFISSO):].strip()
        if nome:
            return nome
    eid = evidenza.get("entity_id")
    return str(eid).strip() if eid else titolo


def _percentuale_batteria(evidenza: dict):
    """Carica residua dall'evidenza, solo se e' davvero un numero."""
    pct = evidenza.get("pct")
    if isinstance(pct, bool) or not isinstance(pct, (int, float)):
        return None
    return float(pct)


def _collect_low_batteries(advisory_store) -> list[dict]:
    """Batterie scariche prese dalle segnalazioni del Brain, al piu' 20.

    Si leggono solo le segnalazioni ancora attive: una rientrata non ha piu'
    nulla da dire e una messa a tacere dall'utente non deve riemergere qui.

    Store assente o in errore significa nessuna batteria da segnalare, mai un
    ricalcolo dalla cache delle entita': un ripiego che ricalcola ricrea le due
    fonti di verita' che questo passaggio elimina. Non solleva mai.
    """
    if advisory_store is None:
        return []
    try:
        righe: list[dict] = []
        for stato in STATI_ATTIVI:
            righe.extend(advisory_store.list(status=stato) or [])
    except Exception:
        return []

    low_batteries: list[dict] = []
    for riga in righe:
        try:
            if not isinstance(riga, dict) or riga.get("check_id") != CHECK_BATTERIA:
                continue
            evidenza = riga.get("evidence")
            if not isinstance(evidenza, dict):
                evidenza = {}
            nome = _nome_batteria(riga, evidenza)
            if not nome:
                continue
            low_batteries.append({"name": nome, "pct": _percentuale_batteria(evidenza)})
            if len(low_batteries) >= _CAP:
                break
        except Exception:
            continue

    return low_batteries


def build_briefing_bundle(
    knowledge_store,
    entity_cache,
    *,
    today: date,
    allow_sensitive: bool,
    horizon_days: int = 7,
    owner: str = "home",
    advisory_store=None,
) -> dict:
    """Deterministic butler briefing bundle: deadlines from ingested
    documents (obligations) plus notable home status (open doors/windows from
    the cache, low batteries from the Brain's advisories). Egress-gated:
    sensitive deadlines are excluded from the list when `allow_sensitive` is
    False, but still counted. Never raises.

    `owner` scopes the deadlines: default "home" (scheduled home-wide broadcast,
    shared obligations only); the on-demand chat tool passes the caller's
    user_id so the user also sees their own private obligations (review C/#2).

    `advisory_store` e' l'unica fonte delle batterie scariche: senza store la
    sezione resta vuota, non si ricalcola. La vecchia `policy` non serve piu'
    perche' la soglia vive nel controllo che emette le segnalazioni.
    """
    try:
        deadlines, hidden_sensitive = _collect_deadlines(
            knowledge_store, today=today, horizon_days=horizon_days,
            allow_sensitive=allow_sensitive, owner=owner,
        )
    except Exception:
        deadlines, hidden_sensitive = [], 0

    try:
        open_now, aperture_lette = _collect_open_now(entity_cache)
    except Exception:
        open_now, aperture_lette = [], False

    try:
        low_batteries = _collect_low_batteries(advisory_store)
    except Exception:
        low_batteries = []

    home: dict = {"open_now": open_now, "low_batteries": low_batteries}
    # La chiave compare SOLO quando c'e' una lacuna da dichiarare: il caso
    # normale mantiene la forma di prima, e il cambio di forma e' esso stesso la
    # spiegazione (stessa convenzione della potatura in api/read_denylist.py).
    if not aperture_lette:
        home["open_now_unavailable"] = True

    return {
        "deadlines": deadlines,
        "home": home,
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
    "non c'e' nulla di rilevante da segnalare, dillo brevemente e basta. Se il "
    "riepilogo contiene `open_now_unavailable`, porte e finestre NON sono state "
    "controllate: dillo apertamente e non affermare che sia tutto chiuso. Sei "
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
    malformed entries: never raises.

    Free-text (`content`/`name`) is passed through `_san` because this template
    is not only user-facing notification text (Task 4) but also the return value
    of the read-only `daily_briefing` chat tool (Task 5) -- i.e. it can land in a
    chat model's context that DOES hold actuation tools, so a poisoned obligation
    must be injection-neutralized here just as `build_briefing_message` does."""
    bundle = bundle or {}
    deadlines = bundle.get("deadlines") or []
    home = bundle.get("home") or {}
    open_now = home.get("open_now") or []
    low_batteries = home.get("low_batteries") or []
    aperture_non_lette = bool(home.get("open_now_unavailable"))

    lines: list[str] = ["Ecco il resoconto di oggi."]

    if deadlines:
        lines.append("Scadenze in arrivo:")
        for d in deadlines:
            try:
                if not isinstance(d, dict):
                    continue
                content = str(_san(d.get("content") or "")).strip()
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

    if aperture_non_lette:
        # Dirlo e' l'unica frase vera: "nessuna apertura" qui sarebbe
        # un'affermazione sulla casa che nessuno ha verificato.
        lines.append(
            "Non ho potuto controllare porte e finestre: l'inventario delle "
            "entità non è disponibile in questo momento."
        )
    elif open_now:
        try:
            names = [str(_san(e.get("name") or "")).strip() for e in open_now if isinstance(e, dict)]
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
                name = str(_san(e.get("name") or "")).strip()
                if not name:
                    continue
                pct = e.get("pct")
                parts.append(f"{name} ({pct}%)" if pct is not None else name)
            except Exception:
                continue
        if parts:
            lines.append("Batterie scariche: " + ", ".join(parts) + ".")

    if not deadlines and not open_now and not low_batteries:
        if aperture_non_lette:
            # Senza le aperture il "nulla da segnalare" vale solo per cio' che
            # si e' davvero potuto guardare.
            lines.append(
                "Per il resto non c'è nulla di urgente: nessuna scadenza "
                "imminente e nessuna batteria scarica da segnalare."
            )
        else:
            lines.append(
                "Non c'e' nulla di urgente al momento: nessuna scadenza imminente, "
                "nessuna apertura e nessuna batteria scarica da segnalare."
            )

    try:
        hidden = (bundle.get("counts") or {}).get("hidden_sensitive")
        if isinstance(hidden, int) and not isinstance(hidden, bool) and hidden > 0:
            noun = "scadenza riservata" if hidden == 1 else "scadenze riservate"
            lines.append(f"Ci sono anche {hidden} {noun} non mostrate qui.")
    except Exception:
        pass

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

    san_home: dict = {"open_now": san_open_now, "low_batteries": san_low_batteries}
    # Booleano nostro, non testo di terzi: se la lacuna non entrasse nel
    # riepilogo, il modello comporrebbe comunque "e' tutto chiuso" leggendo un
    # `open_now` vuoto. Il sistema (BRIEFING_SYSTEM) gli dice come leggerla.
    if home.get("open_now_unavailable"):
        san_home["open_now_unavailable"] = True

    payload = {
        "generated_for": generated_for,
        "deadlines": san_deadlines,
        "home": san_home,
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
