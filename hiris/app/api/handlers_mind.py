"""Le rotte del cervello, che la pagina dell'osservatore legge.

Sette: `watching`, `report`, `analysis`, `knowledge` e le POST `objective`,
`judgment` (la rotta dei giudizi sui tipi, spec 2026-09-16 §4) e `scope` (il
togli e il rimetti del proprietario, D9 degli attori).
Nate come due (fetta «l'osservatore», `docs/design/2026-08-26-l-osservatore.md`
§7), cresciute con la spec dei tre attori (§8, §9, §10, §11).

`Watcher.watching()` e gli archivi gia' tornano la forma che la pagina
mostra -- una seconda forma costruita qui la farebbe divergere il primo giorno
in cui qualcuno aggiunge un campo da una parte sola (fondamenta 3). Cio' che
le letture AGGIUNGONO all'archivio -- l'integrazione delle voci tecniche, le
escluse, il volume, i nomi, gli esiti dell'attuatore -- vive in
`mind/view.MindView`, non qui (Tappa 5, Task 8, 06/10/2026): fino a quel
giorno stava dentro le rotte, e il modello non poteva chiederlo. Ora la rotta
e lo strumento `mind` chiamano gli stessi metodi (`mind_view`).

**503, non un elenco vuoto, quando manca il collaboratore.** Spec §7: la
pagina esiste perche' il proprietario possa vedere «cosa sto guardando e
perche'» in ogni momento -- un `{"watching": []}` direbbe «HIRIS non guarda
niente», mentre l'osservatore assente e' un'altra cosa (l'add-on e' partito
senza di lui). E' la stessa distinzione a tre stati che il resto del prodotto
difende ovunque (`casa.non_disponibili`, `casa.etichette`, eccetera): un
guasto non si appiattisce su un'assenza.

Le rotte GET non hanno `csrf_middleware` da rispettare (sono metodi "safe",
stessa esenzione di `GET /api/agenda`); le POST ci passano, come ogni
scrittura su `/api/`."""
from __future__ import annotations

from aiohttp import web

from ..chat_thread import subject_key_for
from ..home_space.ha_vocabulary import is_entity_id
from ..home_space.open_questions import OPEN_QUESTIONS
from ..home_space.type_judgments import ATTRIBUTE_FIELD, DECLINED_FIELD, MEANING_FIELD
from ..mind import analyst, recipe_turn
from ..mind.judgments import (
    JudgmentNotInEffect,
    JudgmentRefused,
    JudgmentStoreFailed,
    judgment_listing,
    write_judgment,
)
from ..mind.report import BACKFILL_EVERY_MINUTES
from ..mind.scope import OWNER
from ..mind.store import READING_RETENTION_S
from ..mind.view import MindView
from .boundary import error_response, json_object
from .soffitto import subject_name


def mind_view(app) -> MindView:
    """Le letture del cervello di questa app: l'UNICO punto che le costruisce,
    per le rotte qui sotto, per lo strumento `mind`
    (`handlers_chat.create_tool_dispatcher`) e per i giri del server che
    chiedono i nomi dei dispositivi.

    Si costruisce a ogni richiesta, ed e' gratis: tiene solo riferimenti agli
    oggetti dell'app, che possono nascere dopo questa rotta (l'osservatore
    parte all'avvio, a meta')."""
    return MindView(store=app.get("observations"), watcher=app.get("watcher"),
                    home_space=app.get("home_space_store"), cache=app.get("entity_cache"),
                    judgments=app.get("type_judgments"))


async def handle_watching(request: web.Request) -> web.Response:
    """La pagina dello scope: **cosa guardo, perche', da quando, e quanto costa**
    (`MindView.scope`, dove le parti sono spiegate una per una).

    **503, non uno scope vuoto, senza osservatore**: vedi il docstring del
    modulo.
    """
    scope = mind_view(request.app).scope()
    if scope is None:
        return error_response(503, "osservatore non disponibile")
    return web.json_response(scope)


async def handle_report(request: web.Request) -> web.Response:
    """Il resoconto di un giorno, o la serie degli ultimi (spec §9).

    Due forme:

    - `?day=2026-09-13` -- il resoconto di un giorno, reso per la pagina;
    - senza `day` -- **le misure degli ultimi giorni**: due dei tre inneschi
      dell'analista sono confronti nel tempo, e con la cronaca dentro non ci
      starebbero in un prompt. Oggi la leggono gli attrezzi di misura
      (`scripts/batteria_attori.py`).

    Una terza forma, `?day=...&formato=documento`, rendeva lo stesso giorno in
    markdown a sezioni per l'analista. Nessuno la chiedeva, ed e' uscita il
    02/10/2026: cosa faceva e' scritto nel BACKLOG, alla voce sugli attori.

    **Un giorno mai aggregato torna 404, non un resoconto vuoto**: «quel
    giorno non e' successo niente» e «quel giorno non l'abbiamo guardato» sono
    due cose diverse, e chi legge deve poterle distinguere.
    """
    view = mind_view(request.app)
    if view.store is None:
        return error_response(503, "archivio non disponibile")
    day = request.query.get("day") or None
    if day is None:
        # Solo le misure, e l'obiettivo di ogni giorno: `MindView.reports`.
        return web.json_response({"resoconti": view.reports()})
    resoconto = view.report(day)
    if resoconto is None:
        # `ora_notturna`: quando il resoconto di quel giorno si scrivera'. La
        # pagina lo dice («non e' un errore»), e lo riceve invece di saperlo
        # (C-11, Tappa 4, Task 5).
        return error_response(
            404, f"il giorno {day} non e' stato aggregato",
            ora_notturna=view.nightly_time())
    return web.json_response({"resoconto": resoconto})


async def handle_set_objective(request) -> web.Response:
    """Scrive l'obiettivo della casa. **La sola manopola del prodotto.**

    Torna `{"obiettivo": {...}, "scritto": bool}`.

    **Perche' questa rotta e' nata il 14/09/2026, col suo numero.**
    `store.set_objective` esisteva dal giorno 11, provata da dieci prove, e
    nessun codice di produzione la chiamava: nessuna rotta, nessun campo nella
    pagina, nessuno strumento in chat. Misurato sulla casa vera quel giorno,
    l'obiettivo era ancora quello **di fabbrica** -- `scritto_ts: null` -- e
    l'osservatore decideva cosa guardare contro una frase generica, mentre la
    spec lo chiama «obiettivo = prompt». Il docstring di `set_objective` parla
    perfino del bottone «salva»: una motivazione scritta accanto al codice che
    il codice smentiva.

    **`scritto: false` non e' un errore.** Riscrivere lo stesso testo non e' un
    cambio d'obiettivo e non deve sporcare la storia -- la pagina dice «da
    quando guardo questa cosa», e direbbe che tutto e' cambiato ogni volta che
    qualcuno preme «salva» senza aver toccato niente. La regola vive
    nell'archivio, in un posto solo; qui si riporta soltanto cosa ha deciso.

    **Un testo vuoto e' un 400, non un 200 silenzioso.** E' l'unica manopola:
    un campo svuotato per sbaglio non deve poter lasciare l'osservatore senza
    criterio, e chi ha premuto salva deve sapere che non e' stato scritto
    niente.
    """
    store = request.app.get("observations")
    if store is None:
        return error_response(503, "archivio non disponibile")
    body = await json_object(request)
    text = body.get("testo")
    if not isinstance(text, str):
        return error_response(400, "serve un campo `testo` con la frase dell'obiettivo.")
    if not text.strip():
        return error_response(400, "un obiettivo vuoto non si scrive: e' la sola manopola "
                                   "del prodotto, e senza criterio l'osservatore non sa "
                                   "piu' cosa guardare.")
    written = store.set_objective(text)
    return web.json_response({"obiettivo": store.objective(),
                              "scritto": bool(written)})


_JUDGMENT_TEXT_KEYS = ("soggetto_genere", "soggetto", "campo")

#: L'autore di un giudizio quando nessuno sa dirne il nome (un ingress senza
#: intestazione del nome E Home Assistant che non risponde). Vero per
#: costruzione: il cancello di questa rotta ha appena verificato che chi
#: scrive puo' costruire, cioe' e' un amministratore. Mai la chiave: sulla
#: pagina sarebbe un identificatore interno (fix round 1 del Task 4).
UNNAMED_BUILDER = "un amministratore"


async def handle_set_judgment(request) -> web.Response:
    """Scrive un giudizio su un tipo o un'entita' (spec 2026-09-16 §4).

    Corpo: `{"soggetto_genere", "soggetto", "campo", "valore"}`; `valore: null`
    torna al seme. Torna l'esito di `mind/judgments.write_judgment`:
    `{"riga": {...} | null, "impronta": ..., "provenienza_istantanea": "sapere"}`
    -- **non** `da`, che in `giudizi` e' l'origine della riga e qui sarebbe la
    provenienza dell'istantanea: due cose, due parole (giro di correzioni 1,
    punto 3).

    **Un `valore` MANCANTE e' un 400, non un ritorno al seme**: un campo
    dimenticato da chi chiama cancellerebbe in silenzio una correzione.

    **409 se la riga e' scritta ma non vale**: l'istantanea ricostruita e'
    tornata al solo seme per un'altra riga dell'archivio che non si interpreta.
    Non e' un rifiuto (l'archivio e' cambiato) e non e' un successo.

    **503 anche quando il sapere c'e' ma non si lascia scrivere** (giro di
    correzioni 1, punto 8): disco pieno, base occupata oltre il `busy_timeout`.
    Stessa risposta del sapere assente -- per chi guarda e' la stessa cosa, e
    il rimedio e' lo stesso -- con la ragione vera nel corpo.

    E' una scrittura: passa dal `csrf_middleware` come l'obiettivo.

    **Ed e' di chi amministra** (spec 2026-09-26 §3, decisione 6): il gesto
    `amministrare` della sua riga in `admission.ADMISSION` si chiede al
    confine, prima di tutto. L'autore della
    riga e' il soggetto che il confine ha attaccato alla richiesta, mai un
    campo del corpo.
    """
    if request.app.get("knowledge") is None:
        return error_response(503, "il sapere non e' disponibile")
    body = await json_object(request)
    if ("valore" not in body
            or not all(isinstance(body.get(key), str) for key in _JUDGMENT_TEXT_KEYS)):
        return error_response(400, "servono `soggetto_genere`, `soggetto` e `campo` come testo, e "
                                   "`valore` (testo, oppure null per tornare al seme).")
    soggetto = request.get("soggetto")
    try:
        outcome = write_judgment(
            request.app, subject_kind=body["soggetto_genere"], subject=body["soggetto"],
            field=body["campo"], value=body["valore"],
            author_name=(await subject_name(request.app, soggetto)
                         or UNNAMED_BUILDER),
            said_by=subject_key_for(soggetto))
    except JudgmentRefused as refused:
        return error_response(400, str(refused))
    except JudgmentStoreFailed as failed:
        # **503 come il sapere assente** (giro di correzioni 1, punto 8):
        # l'archivio c'e' ma non si lascia scrivere -- disco pieno, `database
        # is locked` oltre il `busy_timeout`. Per chi guarda e' la stessa cosa
        # («il sapere adesso non si puo' usare») e ha lo stesso rimedio
        # (riprovare), mentre un 500 col corpo HTML di aiohttp la pagina non
        # sa nemmeno leggerlo. Non e' un 400: non c'e' niente di sbagliato in
        # cio' che il proprietario ha chiesto.
        return error_response(503, str(failed))
    except JudgmentNotInEffect as unused:
        return error_response(
            409, str(unused), riga=unused.row,
            impronta=unused.status["impronta"],
            provenienza_istantanea=unused.status["provenienza_istantanea"])
    return web.json_response(outcome)


async def handle_set_scope(request) -> web.Response:
    """Il **togli** e il **rimetti** del proprietario (D9 degli attori, Task
    3.7): una decisione sullo scope con autore `OWNER`.

    Corpo: `{"soggetto": entity_id, "dentro": bool, "motivo": testo?}`. Torna
    `{"soggetto", "decisione": {...}}`, la riga di `store.decision()` dopo la
    scrittura.

    **Il motivo e' facoltativo per chi preme, non per l'archivio**:
    `decide_scope` non scrive una decisione senza ragione, e un campo vuoto
    diventa il ripiego di `analyst` (`OWNER_REMOVED`, `OWNER_BROUGHT_BACK`).

    **Solo cio' su cui qualcuno ha gia' deciso** (404 altrimenti): la pagina
    toglie e rimette righe che mostra. Un soggetto mai giudicato scritto qui
    sarebbe una riga che la pagina direbbe guardata e che forse nessun evento
    accendera' mai -- la stessa ragione per cui l'osservatore scarta gli id
    che non ha chiesto. I soggetti tecnici (`log:`, `problema:`...) non sono
    entita' e non passano dallo scope: 400.

    `OWNER` non lo scavalca nessuno (`scope.may_overwrite`): per questo la
    scrive solo chi amministra (il gesto della sua riga in
    `admission.ADMISSION`), come i giudizi sui tipi. E' una scrittura: passa dal `csrf_middleware`.
    """
    store = request.app.get("observations")
    if store is None:
        return error_response(503, "archivio non disponibile")
    body = await json_object(request)
    subject, inside, why = body.get("soggetto"), body.get("dentro"), body.get("motivo")
    if (not is_entity_id(subject) or not isinstance(inside, bool)
            or not (why is None or isinstance(why, str))):
        return error_response(400, "servono `soggetto` (un entity_id), `dentro` (vero o "
                                   "falso) e, se vuoi, `motivo` come testo.")
    if store.decision(subject) is None:
        return error_response(404, f"su {subject} nessuno ha ancora deciso: non c'e' "
                                   "niente da togliere o rimettere.")
    reason = (why or "").strip() or (
        analyst.OWNER_BROUGHT_BACK if inside else analyst.OWNER_REMOVED)
    store.decide_scope(subject, inside=inside, reason=reason, author=OWNER)
    return web.json_response({"soggetto": subject,
                              "decisione": store.decision(subject)})


async def handle_analysis(request) -> web.Response:
    """L'analisi di un giorno, o le ultime (spec §10).

    - `?day=2026-09-15` -- l'analisi di quel giorno;
    - senza `day` -- le ultime, dalla piu' recente.

    **Un giorno mai analizzato torna 404, non un'analisi vuota**: «ho guardato
    e non c'era niente da dire» e «non ho guardato» sono due cose diverse, e
    la prima e' una riga con zero osservazioni. Stessa legge del resoconto.
    """
    view = mind_view(request.app)
    if view.store is None:
        return error_response(503, "archivio non disponibile")
    day = (request.query.get("day") or "").strip()
    if not day:
        return web.json_response({"analisi": view.analyses()})
    found = view.analysis(day)
    if found is None:
        return error_response(404, f"il giorno {day} non e' stato analizzato")
    return web.json_response({"analisi": found})



def _fact_row(fact) -> dict:
    """Una riga del sapere per la pagina, **in una forma sola** per ogni
    elenco di `handle_knowledge` (fondamenta 3). La chiave di chi l'ha
    scritta (`said_by`) non esce: alla pagina serve il nome."""
    return {"specie": fact.subject_kind, "soggetto": fact.subject,
            "campo": fact.field, "valore": fact.value,
            "provenienza": fact.provenance, "verifica": fact.verification,
            "prove": fact.evidence, "fonte": fact.source,
            "chi": fact.who, "quando_ts": fact.when_ts}


async def handle_knowledge(request) -> web.Response:
    """Il **sapere**: cosa HIRIS ha capito della casa, e cosa non ha capito.

    Torna `{"conteggi": {...}, "non_capito": [...], "significati": [...],
    "attributi": [...], "rifiuti": [...], "giudizi": [...],
    "domande_aperte": [...], "ricette": [...], "cronaca": {...}}`. `giudizi`
    sono le righe dei giudizi sui tipi che l'archivio sa leggere, con da dove
    vengono (`mind/judgments.judgment_listing`:
    una riga che l'archivio salta non c'e'); `domande_aperte` le
    domande del censore (`open_questions.OPEN_QUESTIONS`) a cui la pagina chiede
    di rispondere (spec 2026-09-16 §7).

    **La quarta fondamenta**: se un dato c'e' e nessuno puo' chiederlo, non
    esiste. Il sapere contiene i significati delle classi che Home Assistant
    pubblica, gli attributi che valgono la pena e le ricette dei dispositivi
    (e, sulle case avviate prima del 01/10/2026, le direzioni dell'energia che
    il seme scriveva e nessuno legge piu') -- e fino al 15/09/2026 si leggeva
    da tre punti del codice e da **nessuna pagina**.

    **Il riassunto e' per specie e provenienza, non un numero solo**: «177
    significati importati da Home Assistant» e «tre ricette dedotte dal
    modello» sono due fatti diversi.

    **E le righe che il modello non ha capito viaggiano intere**, con chi e
    quando: sono cio' che il proprietario risolverebbe in dieci secondi --
    «quello e' il contatore dell'acqua» -- e una riga di tre settimane fa puo'
    riguardare un dispositivo che nel frattempo e' cambiato.

    **Senza archivio e' un 503, non un sapere vuoto**: «non e' collegato» e
    «non ha capito niente della casa» sono due cose diverse.

    **Significati, attributi e rifiuti si elencano riga per riga** (G-05,
    Tappa 8, fondamenta 4): fino al 08/10/2026 la porta li contava soltanto, e
    un significato importato da Home Assistant o un «niente da misurare» del
    modello si potevano sapere solo sommati. Ogni riga ha la stessa forma di
    quelle di `non_capito` (`_fact_row`), con la sua fonte: per un significato
    e' la citazione, col tag (B-47).
    """
    sapere = request.app.get("knowledge")
    if sapere is None:
        return error_response(503, "il sapere non e' disponibile")
    names = mind_view(request.app).device_names()
    listed = sapere.field_rows((MEANING_FIELD, ATTRIBUTE_FIELD, DECLINED_FIELD))
    return web.json_response({
        "conteggi": sapere.summary(),
        "non_capito": [_fact_row(f) for f in sapere.not_understood()],
        "significati": [_fact_row(f) for f in listed if f.field == MEANING_FIELD],
        "attributi": [_fact_row(f) for f in listed if f.field == ATTRIBUTE_FIELD],
        "rifiuti": [_fact_row(f) for f in listed if f.field == DECLINED_FIELD],
        "giudizi": judgment_listing(sapere),
        "domande_aperte": [{"chiavi": sorted(question.keys), "domanda": question.question}
                           for question in OPEN_QUESTIONS],
        # Le ricette INTERE, non solo il loro conto (attori, 06/10/2026):
        # passi, entita', contro cosa sono state scritte (`recipe_listing`),
        # col nome del dispositivo di adesso.
        "ricette": [{**row, "nome": names.get(row["dispositivo"])}
                    for row in recipe_turn.recipe_listing(sapere)],
        # Quanto costa rifare la cronaca, che la pagina dice accanto a ogni
        # giudizio che la rifa': quanti giorni ne conserva il grezzo e ogni
        # quanto il recupero ne scrive uno (C-11, Tappa 4, Task 5).
        "cronaca": {"ritenzione_s": READING_RETENTION_S,
                    "un_giorno_ogni_s": BACKFILL_EVERY_MINUTES * 60},
    })
