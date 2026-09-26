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
    _SUBJECT_KINDS,
    DA_SAPERE_SUBITO_FIELD,
    GENRE_FIELD,
    JUDGMENT_FIELD_NAMES,
    NOTABLE_FIELD,
    OPERABLE_FIELD,
    PARAMETER_LIMITS_FIELD,
    RESTING_FIELD,
    SCAFFOLDING_FIELD,
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

#: L'autore dei giudizi scritti dalla porta PRIMA del 26/09/2026, quando la
#: porta non sapeva chi scriveva e firmava tutto cosi'. Per quelle righe e'
#: vero (spec 2026-09-26 §3: «i giudizi gia' scritti restano "proprietario"»),
#: e resta scritto qui solo per riconoscerle: nessuna riga nuova lo porta.
_LEGACY_AUTHOR = "proprietario"

#: L'origine di una riga scritta dalla porta, in `judgment_listing`: una
#: CORREZIONE, di chiunque sia -- chi l'ha scritta e' `chi`, un altro campo.
#: Fino al 26/09/2026 si chiamava «proprietario», cioe' l'autore dentro
#: l'origine: due fatti in una parola, separati qui alla fonte.
CORRECTION_ORIGIN = "correzione"

#: A quale livello di soggetto ogni campo e' CONSULTATO da `TypeJudgments`
#: (le sue domande, lette nel codice il 17/09/2026): `genre_of` e `resting_of`
#: salgono entita' -> coppia -> dominio; `working_of`, `is_notable` e
#: `da_sapere_subito` coppia -> dominio (spec `2026-09-18-da-sapere-subito.md`
#: §2: stessa forma di `is_notable`, per la stessa ragione -- `binary_sensor`
#: dice «no» in generale e «si'» sulle classi che lo meritano, mai su
#: un'entita' singola); `operable_domains` e `parameter_limits` solo il
#: dominio. Una riga a un livello che nessuna domanda legge non si scrive: il
#: proprietario la vedrebbe accettata e la casa non cambierebbe.
_LEVELS = {
    GENRE_FIELD: frozenset({"entita", "coppia", "dominio"}),
    RESTING_FIELD: frozenset({"entita", "coppia", "dominio"}),
    WORKING_FIELD: frozenset({"coppia", "dominio"}),
    NOTABLE_FIELD: frozenset({"coppia", "dominio"}),
    DA_SAPERE_SUBITO_FIELD: frozenset({"coppia", "dominio"}),
    SCAFFOLDING_FIELD: frozenset({"integrazione"}),
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
    (`seme`/`correzione`/`altro`), e qui vale una cosa diversa -- da dove e'
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
#: Lo slug di un'integrazione: un segmento solo, come lo scrive Home
#: Assistant nel manifest (`hacs`, `websocket_api`, `homeassistant`).
_INTEGRATION_RE = re.compile(r"[a-z][a-z0-9_]*")


def _level(subject_kind: str, subject: str) -> str | None:
    """Il livello che una chiave di ricerca di `TypeJudgments` costruirebbe per
    questo soggetto, o `None` se nessuna lo costruisce.

    **La forma si controlla, non si spezza soltanto sul punto**: `Light`,
    `light x` o `Light.x` sarebbero righe accettate che nessuna chiave -- fatta
    di domini, classi ed entity_id di Home Assistant -- incontrera' mai, cioe'
    una correzione che la casa non vede (revisione del Task 7)."""
    if subject_kind == "entita":
        return "entita" if _ENTITY_ID_RE.fullmatch(subject) else None
    if subject_kind == "integrazione":
        # Lo SLUG, non il percorso del logger: `hacs`, `websocket_api`.
        # `custom_components.hacs` sarebbe una riga accettata che nessuna
        # chiave incontrera' mai -- `report._integration_slug` consegna sempre
        # un segmento solo.
        return "integrazione" if _INTEGRATION_RE.fullmatch(subject) else None
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
    `correzione` se l'ha scritta la porta -- dal 26/09/2026 la riga porta la
    chiave di chi l'ha scritta (`said_by`), prima portava l'autore
    `_LEGACY_AUTHOR`; `seme` se l'autore e' il seme E il valore e' quello che
    il seme del repo scrive oggi; `altro` in ogni altro caso -- una riga che
    nessuno rivendica. Chi ha scritto una correzione lo dice `chi`. Una riga
    che l'archivio salta perche' non si regge (`knowledge._facts`) qui non
    compare. La chiave non esce: alla pagina serve il nome.

    **`da` qui e' l'origine della RIGA**, e non si confonde con la provenienza
    dell'ISTANTANEA, che si chiama `provenienza_istantanea` da dove nasce
    (`_status`): giro di correzioni 1, punto 3.
    """
    seeded = _seed_values()
    listing = []
    for fact in knowledge.judgment_rows():
        if fact.said_by is not None or fact.who == _LEGACY_AUTHOR:
            origin = CORRECTION_ORIGIN
        elif (fact.who == SEED_AUTHOR
              and seeded.get((fact.subject_kind, fact.subject, fact.field)) == fact.value):
            origin = "seme"
        else:
            origin = "altro"
        listing.append({"soggetto_genere": fact.subject_kind, "soggetto": fact.subject,
                        "campo": fact.field, "valore": fact.value, "da": origin,
                        "chi": fact.who, "quando_ts": fact.when_ts})
    return listing


def _check(subject_kind: str, subject: str, field: str, value, current: TypeJudgments) -> None:
    if subject_kind not in _SUBJECT_KINDS or not subject:
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
    if field == DA_SAPERE_SUBITO_FIELD and value == "si":
        # **`== "si"` e non «il campo e' scritto»**, e la differenza e'
        # sostanziale (decisione del proprietario, 18/09/2026): il valore ha
        # TRE forme, e per un ELENCO di stati questa domanda non ha senso --
        # l'elenco dice gia' quali stati contano, e non c'e' niente da
        # decidere. Il rifiuto riguarda il solo `si`, che senza riposo ne'
        # lavoro non sa a cosa appoggiarsi.
        #
        # Ruling del controller (giro di correzioni 1, IMPORTANT 2): un tipo
        # `da_sapere_subito: si` senza `riposo` ne' `lavoro` e' un caso
        # indecidibile per `stato_da_sapere_subito` -- il suo ripiego «non e'
        # un riposo» su un riposo vuoto renderebbe notizia ogni stato non
        # assente, `off` compreso. Per sapere quando una cosa esce dal suo
        # riposo bisogna sapere qual e' il riposo: un rifiuto e' piu' onesto
        # di un «si» che trasforma in notizia anche lo spegnimento.
        #
        # **Questo rifiuto e' una cortesia, NON la garanzia** (revisione
        # finale, I-1): non protegge l'invariante, perche' si puo' scrivere il
        # riposo, poi il `si`, poi togliere il riposo -- tornando al seme,
        # oppure con `riposo: '[]'`, che `_parse` accetta -- e restare con un
        # `si` orfano. La garanzia sta alla fonte, in
        # `TypeJudgments.stato_da_sapere_subito`: senza lavoro ne' riposo la
        # regola risponde `False` («indecidibile vale no»). Qui si spiega il
        # problema a chi scrive, quando lo si puo' ancora spiegare.
        domain, _, device_class = subject.partition(".")
        device_class = device_class or None
        if not current.resting_of(domain, device_class) and not current.working_of(
                domain, device_class):
            raise JudgmentRefused(
                f"`{DA_SAPERE_SUBITO_FIELD}` su `{subject}` senza un riposo ne' un lavoro: per "
                "sapere quando una cosa esce dal suo riposo bisogna prima sapere qual e' il "
                "riposo -- scrivi prima `riposo` o `lavoro`")


def write_judgment(app, *, subject_kind: str, subject: str, field: str, value: str | None,
                   author_name: str, said_by: str, now=_time.time) -> dict:
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

    `author_name` e `said_by` sono chi scrive (spec 2026-09-26 §3, decisione
    6): il nome in `who`, la chiave del soggetto in `said_by`, come i ricordi.
    Li decide chi chiama dal soggetto del confine -- il nome da
    `soffitto.subject_name`, la casa dei nomi -- e mai dal corpo di una
    richiesta.
    """
    knowledge = app.get("knowledge")
    if knowledge is None:
        raise JudgmentRefused("il sapere non e' disponibile")
    subject = str(subject or "").strip()
    _check(subject_kind, subject, field, value, app.get("type_judgments", REPO_JUDGMENTS))
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
                    provenance="nostro", who=author_name, said_by=said_by,
                    when_ts=now())
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
