"""La porta dei giudizi sui tipi (spec 2026-09-16 §3, §4, §8).

Costruisce l'istantanea dal sapere e la riscrive. **Nessun altro modulo scrive
i campi dei giudizi**: fuori da questo file e dal seme (`mind/seed.judgment_seed`)
nessun modulo di produzione costruisce un `Fact` su quei campi, e
`tests/test_judgments_single_port.py` lo cerca in tutto `hiris/app` -- per
nome del campo o per costante; un campo che arriva da una variabile quella
ricerca non lo vede, e la prova lo dichiara.

**Una riga storta non fa cadere l'avvio** (spec §8): l'istantanea torna al solo
seme del repo e lo stato dice perche', cosi' che `/api/health` lo mostri.
"""
from __future__ import annotations

import re
import sqlite3
import time as _time

from ..home_space.type_judgments import (
    GENRE_FIELD,
    JUDGMENT_FIELD_NAMES,
    NOTABLE_FIELD,
    OPERABLE_FIELD,
    PARAMETER_LIMITS_FIELD,
    RESTING_FIELD,
    WORKING_FIELD,
    JudgmentError,
    TypeJudgments,
)
from ..home_space.type_vocabulary import (
    ABSENT_STATE_FORMS,
    CHRONICLE_GENRES,
    REPO_JUDGMENTS,
    judgment_seed_rows,
)

# Nome privato importato da un altro modulo, di proposito: la guardia stretta
# sulla forma `dominio.oggetto` vive in quattro copie (docs/BACKLOG.md, voce
# «`_ENTITY_ID_RE` vive in quattro copie») e una quinta peggiorerebbe il debito.
# `proxy/ha_client.py` e' la prima e il confine con Home Assistant, e non
# importa nessun modulo di `mind`: nessun ciclo.
from ..proxy.ha_client import _ENTITY_ID_RE
from .knowledge import Fact
from .seed import REPO_PRIORITY, SEED_AUTHOR

#: Chi scrive un giudizio dalla porta: la casa, cioe' il suo proprietario.
JUDGMENT_AUTHOR = "proprietario"

#: A quale livello di soggetto ogni campo e' CONSULTATO da `TypeJudgments`
#: (le sue domande, lette nel codice il 17/09/2026): `genre_of` e `resting_of`
#: salgono entita' -> coppia -> dominio; `working_of` e `is_notable` coppia ->
#: dominio; `operable_domains` e `parameter_limits` solo il dominio. Una riga
#: a un livello che nessuna domanda legge non si scrive: il proprietario la
#: vedrebbe accettata e la casa non cambierebbe.
_LEVELS = {
    GENRE_FIELD: frozenset({"entita", "coppia", "dominio"}),
    RESTING_FIELD: frozenset({"entita", "coppia", "dominio"}),
    WORKING_FIELD: frozenset({"coppia", "dominio"}),
    NOTABLE_FIELD: frozenset({"coppia", "dominio"}),
    OPERABLE_FIELD: frozenset({"dominio"}),
    PARAMETER_LIMITS_FIELD: frozenset({"dominio"}),
}

#: `guasto` ha una forma, ma e' quella delle condizioni di sistema
#: (`mind/facts.genre_for`: i prefissi `problema:`, `integrazione:`, `log:`,
#: `automazione:`): legge `a` come `chiuso` o come la condizione vera. Dato allo
#: stato di un'entita', ogni stato diverso da `chiuso` -- `off` compreso --
#: aprirebbe un guasto, e nessuno lo chiuderebbe (spec §5: la forma resta codice,
#: la casa sceglie solo fra i generi che uno stato sa portare).
_SYSTEM_ONLY_GENRE = "guasto"


class JudgmentRefused(ValueError):
    """Un giudizio che la porta non scrive, con la ragione. L'archivio non e'
    stato toccato."""


class JudgmentStoreFailed(RuntimeError):
    """L'archivio del sapere ha sollevato **mentre** scriveva: disco pieno,
    `database is locked` oltre il `busy_timeout`, file corrotto.

    Non e' `JudgmentRefused` -- non c'e' niente di sbagliato in cio' che il
    proprietario ha chiesto, e riprovare fra un minuto puo' benissimo
    riuscire -- e non e' un errore del programma: e' l'archivio che in questo
    momento non si lascia scrivere, e chi chiama deve poterlo dire con parole
    sue invece di ricevere un 500 col corpo HTML che nessun chiamante di
    questa API sa leggere (giro di correzioni 1, punto 8).

    **L'istantanea non si tocca**: si solleva prima di ricostruirla, perche'
    una scrittura che non e' avvenuta non puo' cambiare cio' che la casa
    legge.
    """


class JudgmentNotInEffect(RuntimeError):
    """La riga E' scritta, ma l'istantanea ricostruita e' tornata al solo seme
    (un'altra riga dell'archivio non si interpreta): la correzione non vale.
    Porta la riga scritta (`row`) e lo stato (`status`)."""

    def __init__(self, row: dict | None, status: dict) -> None:
        super().__init__(
            "giudizio scritto ma NON in vigore: l'istantanea e' tornata al solo seme -- "
            f"{status['perche']}")
        self.row = row
        self.status = status


def build_judgments(knowledge, *, unavailable_reason: str | None = None) -> tuple[TypeJudgments,
                                                                                   dict]:
    """`unavailable_reason` vale solo senza sapere: e' l'errore vero con cui
    l'archivio non si e' aperto (`server._open_knowledge`), e il `perche` lo
    porta invece del solo «non e' disponibile» (Task 7b, 17/09/2026)."""
    if knowledge is None:
        why = "il sapere non e' disponibile"
        if unavailable_reason:
            why += ": " + unavailable_reason
        return REPO_JUDGMENTS, _status("solo seme", why, REPO_JUDGMENTS)
    facts, skipped = knowledge.judgment_rows_and_skipped()
    # **Le righe che l'archivio ha saltato si DICONO** (giro di correzioni 1,
    # punto 6, differito dal Task 3 al Task 7 e mai fatto). Una riga di
    # giudizio malformata a livello di `Fact` -- si corregge a mano, con un
    # `UPDATE` che nessuno rilegge -- veniva scartata da `knowledge._facts` e
    # finiva solo nel registro dell'add-on, che da fuori non si legge: la casa
    # diceva che il suo giudizio veniva dal sapere, e una riga di quel sapere
    # non c'era. L'istantanea resta buona (la riga saltata non la sporca):
    # cambia `perche`, non `provenienza_istantanea`.
    skipped_why = (None if not skipped else
                   "righe del sapere che l'archivio non riesce a leggere, e che quindi "
                   "NON sono in vigore: " + "; ".join(skipped))
    rows = [(f.subject_kind, f.subject, f.field, f.value) for f in facts]
    try:
        judgments = TypeJudgments.from_rows(rows, genres=CHRONICLE_GENRES,
                                            absent_forms=ABSENT_STATE_FORMS.value)
    except JudgmentError as error:
        why = "righe del sapere che non si interpretano: " + "; ".join(error.reasons)
        if skipped_why:
            why += " -- e inoltre " + skipped_why
        return REPO_JUDGMENTS, _status("solo seme", why, REPO_JUDGMENTS)
    return judgments, _status("sapere", skipped_why, judgments)


def _writing(operation, *args, **kwargs):
    """Esegue una scrittura dell'archivio traducendo il suo guasto in
    `JudgmentStoreFailed`.

    **Solo `sqlite3.Error`**: un `TypeError` o un `AttributeError` qui sono
    difetti di questo programma e devono restare quello che sono -- tradurli
    in «l'archivio non scrive» darebbe al proprietario una ragione falsa e
    toglierebbe a noi la traccia.
    """
    try:
        return operation(*args, **kwargs)
    except sqlite3.Error as error:
        raise JudgmentStoreFailed(
            f"il sapere non ha potuto scrivere ({type(error).__name__}: {error})") from error


def _status(source: str, why: str | None, judgments: TypeJudgments) -> dict:
    """Lo stato dell'istantanea: **da dove viene**, perche', e la sua impronta.

    **`provenienza_istantanea` e non `da`** (giro di correzioni 1, punto 3,
    fondamenta 3): `da` e' gia' l'origine di una RIGA in `judgment_listing`
    (`seme`/`proprietario`/`altro`), e qui vale una cosa diversa -- da dove e'
    stata costruita l'istantanea intera (`sapere`/`solo seme`). Due cose con
    una parola sola si separano **alla fonte**, che e' questa riga: cosi'
    nessuna delle porte a valle (`/api/health`, la risposta della POST, il
    409) deve ribattezzarla per conto suo.
    """
    return {"provenienza_istantanea": source, "perche": why,
            "impronta": judgments.chronicle_fingerprint()}


#: La forma di un soggetto `tipo`: un dominio di Home Assistant, da solo o con
#: `.device_class` (minuscole, cifre, `_`). NON e' la forma di un entity_id:
#: quella e' `_ENTITY_ID_RE`, importata qui sotto.
_TYPE_SUBJECT_RE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)?")


def _level(subject_kind: str, subject: str) -> str | None:
    """Il livello che una chiave di ricerca di `TypeJudgments` costruirebbe per
    questo soggetto, o `None` se nessuna lo costruisce.

    **La forma si controlla, non si spezza soltanto sul punto**: `Light`,
    `light x` o `Light.x` sarebbero righe accettate che nessuna chiave -- fatta
    di domini, classi ed entity_id di Home Assistant -- incontrera' mai, cioe'
    una correzione che la casa non vede (revisione del Task 7)."""
    if subject_kind == "entita":
        return "entita" if _ENTITY_ID_RE.fullmatch(subject) else None
    if not _TYPE_SUBJECT_RE.fullmatch(subject):
        return None
    return "coppia" if "." in subject else "dominio"


def _seed_values() -> dict[tuple[str, str, str], str]:
    return {(kind, subject, field): value for kind, subject, field, value in judgment_seed_rows()}


def judgment_listing(knowledge) -> list[dict]:
    """Le righe dei giudizi nell'archivio, per la pagina (spec §7): valore, chi
    e quando, e **da dove vengono**.

    `da` non si legge dal solo `who`: l'archivio si corregge anche a mano con
    un `UPDATE` che non cambia l'autore (`knowledge.py`, schema). Quindi:
    `proprietario` se l'ha scritta la porta; `seme` se l'autore e' il seme E il
    valore e' quello che il seme del repo scrive oggi; `altro` in ogni altro
    caso -- una riga che nessuno dei due rivendica. Una riga che l'archivio
    salta perche' non si regge (`knowledge._facts`) qui non compare.

    **`da` qui e' l'origine della RIGA**, e non si confonde con la provenienza
    dell'ISTANTANEA, che si chiama `provenienza_istantanea` da dove nasce
    (`_status`): giro di correzioni 1, punto 3.
    """
    seeded = _seed_values()
    listing = []
    for fact in knowledge.judgment_rows():
        if fact.who == JUDGMENT_AUTHOR:
            origin = "proprietario"
        elif (fact.who == SEED_AUTHOR
              and seeded.get((fact.subject_kind, fact.subject, fact.field)) == fact.value):
            origin = "seme"
        else:
            origin = "altro"
        listing.append({"soggetto_genere": fact.subject_kind, "soggetto": fact.subject,
                        "campo": fact.field, "valore": fact.value, "da": origin,
                        "chi": fact.who, "quando_ts": fact.when_ts})
    return listing


def _check(subject_kind: str, subject: str, field: str, value) -> None:
    if subject_kind not in ("tipo", "entita") or not subject:
        raise JudgmentRefused("serve un soggetto: un tipo o un'entita'")
    if field not in JUDGMENT_FIELD_NAMES:
        raise JudgmentRefused(f"`{field}` non e' un giudizio che la casa possa correggere")
    if value is None:
        # Tornare al seme si puo' a ogni livello: toglie anche una riga scritta
        # a mano dove nessuna domanda la legge, e la pagina la mostra.
        return
    level = _level(subject_kind, subject)
    if level is None:
        raise JudgmentRefused(
            f"il soggetto {subject_kind} `{subject}` non ha la forma di un dominio, di una "
            "coppia dominio.classe o di un'entita' dominio.oggetto, scritti come in Home "
            "Assistant: lettere minuscole, cifre e `_`, il dominio comincia con una lettera")
    if level not in _LEVELS[field]:
        raise JudgmentRefused(
            f"`{field}` su un {level} non lo consulta nessuna domanda: si legge solo su "
            + ", ".join(sorted(_LEVELS[field])))
    if not isinstance(value, str):
        raise JudgmentRefused("il valore di un giudizio e' testo (JSON per le liste e le mappe)")
    if field == GENRE_FIELD and value == _SYSTEM_ONLY_GENRE:
        raise JudgmentRefused(
            "`guasto` e' il genere delle condizioni di sistema: sullo stato di un tipo o di "
            "un'entita' aprirebbe a ogni stato e non chiuderebbe mai")
    try:
        TypeJudgments.from_rows([(subject_kind, subject, field, value)],
                                genres=CHRONICLE_GENRES, absent_forms=ABSENT_STATE_FORMS.value)
    except JudgmentError as error:
        raise JudgmentRefused("; ".join(error.reasons)) from error


def write_judgment(app, *, subject_kind: str, subject: str, field: str, value: str | None,
                   now=_time.time) -> dict:
    """**La porta unica** (spec §4): valida, scrive, ricostruisce l'istantanea e
    sostituisce INSIEME `app["type_judgments"]` e `app["type_judgments_status"]`
    -- la correzione vale subito (spec §0, decisione 2).

    `value=None` torna al seme: se il seme ha la chiave, la riga gli torna
    (`knowledge.forget_and_seed`, **una transazione sola**, cosi' che anche
    `seeded_value` sia di nuovo suo e un rilascio che corregge quel valore le
    arrivi); se non ce l'ha, si cancella.

    Solleva `JudgmentRefused` senza toccare l'archivio; `JudgmentStoreFailed`
    se l'archivio c'e' ma non si lascia scrivere, e li' l'istantanea non si
    tocca; `JudgmentNotInEffect`
    se la riga e' scritta ma l'istantanea ricostruita e' del solo seme.
    Nessuna ricarica della `EntityCache` (D1: nessun giudizio del sapere e'
    tenuto calcolato dalla cache).
    """
    knowledge = app.get("knowledge")
    if knowledge is None:
        raise JudgmentRefused("il sapere non e' disponibile")
    subject = str(subject or "").strip()
    _check(subject_kind, subject, field, value)
    if value is None:
        seeded = _seed_values().get((subject_kind, subject, field))
        fact = None if seeded is None else Fact(
            subject_kind=subject_kind, subject=subject, field=field, value=seeded,
            provenance="nostro", who=SEED_AUTHOR, when_ts=now())
        # **Togliere e rimettere il seme sono UNA transazione** (giro di
        # correzioni 1, punto 8, prima fondamenta): erano `forget()` e poi
        # `seed()`, e un guasto dell'archivio in mezzo lasciava il sapere
        # senza nessuna delle due righe.
        _writing(knowledge.forget_and_seed, subject_kind, subject, field,
                   [] if fact is None else [fact], priority=REPO_PRIORITY)
    else:
        fact = Fact(subject_kind=subject_kind, subject=subject, field=field, value=value,
                    provenance="nostro", who=JUDGMENT_AUTHOR, when_ts=now())
        _writing(knowledge.write, fact)
    judgments, status = build_judgments(knowledge)
    app["type_judgments"], app["type_judgments_status"] = judgments, status
    row = None if fact is None else {
        "soggetto_genere": fact.subject_kind, "soggetto": fact.subject, "campo": fact.field,
        "valore": fact.value, "chi": fact.who, "quando_ts": fact.when_ts}
    if status["provenienza_istantanea"] != "sapere":
        raise JudgmentNotInEffect(row, status)
    return {"riga": row, "impronta": status["impronta"],
            "provenienza_istantanea": status["provenienza_istantanea"]}
