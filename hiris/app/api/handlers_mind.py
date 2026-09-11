"""Le due rotte della pagina dell'osservatore (fetta «l'osservatore», Task 7:
docs/design/2026-08-26-l-osservatore.md §7).

Non serializzano niente per conto proprio. `Watcher.watching()` e
`ObservationsStore.facts()` gia' tornano la forma che la pagina mostra --
una seconda forma costruita qui la farebbe divergere il primo giorno in cui
qualcuno aggiunge un campo da una parte sola (fondamenta 3).

**L'unica eccezione, e porta il suo perche' (fetta «lo stato», 07/09/2026):
la RESA dello stato.** L'archivio continua a scrivere lo stato GREZZO --
`heat`, `not_home`, `triggered` -- perche' e' quello il fatto, ed e' quello
che `mind/facts.py` confronta coi riposi e i «non lo so» del vocabolario dei
tipi per aprire e chiudere gli episodi: scriverci «Riscaldamento»
romperebbe l'aggregazione, e tenere
entrambi in colonna sarebbe il doppione che le fondamenta vietano. La resa
avviene qui, al confine, in un campo ACCANTO al grezzo e mai sopra -- la
stessa disciplina di `nome`/`nome_dedotto` in `memory/resolver.py`. Non e'
una seconda forma dell'oggetto: e' una chiave in piu' su quella che
l'archivio ha gia' dato, e chi legge usa la resa se c'e' e il grezzo se no.

**503, non un elenco vuoto, quando manca il collaboratore.** Spec §7: la
pagina esiste perche' il proprietario possa vedere «cosa sto guardando e
perche'» in ogni momento -- un `{"watching": []}` direbbe «HIRIS non guarda
niente», mentre l'osservatore assente e' un'altra cosa (l'add-on e' partito
senza di lui). E' la stessa distinzione a tre stati che il resto del prodotto
difende ovunque (`casa.non_disponibili`, `casa.etichette`, eccetera): un
guasto non si appiattisce su un'assenza.

Entrambe le rotte sono GET, quindi nessun `csrf_middleware` da rispettare
(sono metodi "safe", stessa esenzione di `GET /api/agenda`)."""
from __future__ import annotations

from datetime import datetime, timedelta

from aiohttp import web

from ..home_space.historian import home_space_zone
from ..mind.facts import NOT_ENTITY_PREFIXES, day_boundaries
from ..proxy.state_translations import state_translation

# I soggetti che NON sono entita' di Home Assistant: una condizione di
# sistema, una voce del registro di errori, un'esecuzione di automazione. Il
# loro `corpo.stato` non e' uno stato di HA (`aperto`, `setup_retry`,
# `chiuso`: parole di HIRIS e della configurazione, non del vocabolario degli
# stati), e cercargli una traduzione vorrebbe dire spaccare `automazione:
# automation.x` sul punto e chiedere a HA il dominio «automazione:automation»,
# che non esiste su nessuna casa.
#
# **Corretto il 09/09/2026 (audit delle fondamenta): non e' piu' una tupla
# scritta qui.** Fino a oggi lo stesso confine, con le stesse quattro parole,
# viveva TRE volte -- qui, e due volte in `mind/facts.py` (`genre_for` e
# `_reading_aspect`) -- ed era una fondamenta 2 vera: un quarto prefisso
# aggiunto altrove sarebbe rimasto invisibile qui. La casa e'
# `mind/facts.NOT_ENTITY_PREFIXES`; questo modulo si collega, non copia.


#: Quanti giorni di volume la pagina mostra. **Non e' la durata del grezzo**
#: (22 giorni, `store.READING_RETENTION_S`): e' quanto serve a vedere se il
#: filtro dello scope sta funzionando -- una settimana, cioe' abbastanza da
#: distinguere un giorno storto da una tendenza.
VOLUME_DAYS = 7


async def handle_watching(request: web.Request) -> web.Response:
    """La pagina dello scope: **cosa guardo, perche', da quando, e quanto costa**.

    Spec §5.1 e §11 **non sono due pagine**: l'elenco di cio' che si guarda e'
    anche la prova che l'obiettivo e' stato capito. Per questo la rotta porta
    tutte e cinque le parti in una risposta sola -- chi legge deve poter
    confrontare le scelte con la domanda a cui rispondono senza cambiare
    schermata:

    - `watching` -- cio' che si guarda, col **motivo** e l'**autore** di ogni
      voce (`Watcher.watching()`, che le prende dallo scope);
    - `fuori` -- cio' che e' stato **lasciato fuori**, con la sua ragione. E'
      l'altra meta' della trasparenza, ed e' da li' che si rimette dentro una
      delle escluse: un elenco di sole cose guardate non direbbe se un'entita'
      manca perche' esclusa o perche' mai considerata;
    - `obiettivo` -- la domanda rispetto a cui si e' deciso;
    - `riconsiderazione` -- quando si e' ripensata tutta la casa, la **finestra
      di memoria misurata** e la **cadenza** che ne esce. Tutti e tre, o
      «ogni 84 ore» sarebbe da credere sulla parola;
    - `tentativi` -- gli ultimi giri **riusciti o no**, dal piu' recente. E'
      l'altra domanda, e non e' la stessa: `riconsiderazione` risponde a
      «quand'e' l'ultima volta che la casa e' stata ripensata», `tentativi` a
      **«sta funzionando?»**. Misurato sulla casa vera l'11/09/2026:
      l'osservatore ha provato e fallito quattro volte in quaranta minuti,
      HIRIS ha smesso di registrare qualunque cosa -- il cancello di
      `watcher.watch_reading` **e'** lo scope -- e questa pagina diceva
      soltanto «non e' mai stata fatta». Vero alla lettera, falso come
      racconto: e' la regola che questo modulo dichiara in cima al file,
      violata dalla pagina che la dichiarava;
    - `volume` -- **quante righe grezze al giorno**. E' la contropartita onesta
      dello scope, e la spec promette -83%: fino all'11/09/2026 nessuna porta
      lo esponeva, e la promessa non era verificabile da fuori.

    **Le parti che mancano si dichiarano `None`/`[]`, non si inventano.**
    L'osservatore puo' esserci e l'archivio no (avvio a meta', o un guasto): un
    obiettivo di fabbrica e un volume a zero sarebbero due affermazioni che
    nessuno ha verificato.
    """
    watcher = request.app.get("watcher")
    if watcher is None:
        return web.json_response(
            {"watching": [], "error": "osservatore non disponibile"}, status=503)
    store = request.app.get("observations")
    return web.json_response({
        "watching": watcher.watching(),
        "fuori": _left_out(store),
        "obiettivo": store.objective() if store is not None else None,
        "riconsiderazione": store.last_reconsideration() if store is not None else None,
        "tentativi": store.recent_attempts() if store is not None else None,
        "volume": _volume(request.app, store),
    })


def _left_out(store) -> list[dict]:
    """Cio' su cui qualcuno ha deciso **di no**, con la ragione e l'autore.

    Chi non e' nello scope affatto non compare: non e' stato lasciato fuori,
    non e' stato considerato -- e dirlo di 452 entita' riempirebbe la pagina di
    righe senza ragione accanto, che e' il contrario di cio' che serve.
    """
    if store is None:
        return []
    return sorted(
        ({"soggetto": subject, "motivo": v["motivo"], "autore": v["autore"],
          "deciso_ts": v["deciso_ts"]}
         for subject, v in store.scope().items() if not v["dentro"]),
        key=lambda v: v["soggetto"])


def _volume(app, store) -> list[dict]:
    """Quante righe grezze per ciascuno degli ultimi giorni, **dal piu'
    vecchio**: si legge come una tendenza, e una tendenza si legge in avanti.

    I confini sono quelli del giorno LOCALE (`facts.day_boundaries` col fuso
    della casa), gli stessi che usa l'aggregazione notturna: un conteggio su
    giorni UTC direbbe numeri che non combaciano con nessun'altra pagina.
    """
    if store is None:
        return []
    from ..server import _timezone_from_home_space_store

    timezone = _timezone_from_home_space_store(app.get("home_space_store"))
    today = datetime.now(home_space_zone(timezone)).date()
    volume = []
    for back in range(VOLUME_DAYS - 1, -1, -1):
        day = (today - timedelta(days=back)).isoformat()
        from_ts, to_ts = day_boundaries(day, timezone)
        volume.append({"giorno": day,
                       "righe": store.readings_count(from_ts=from_ts, to_ts=to_ts)})
    return volume


async def handle_facts(request: web.Request) -> web.Response:
    """Gli oggetti costruiti dall'aggregazione, filtrabili per giorno.

    `giorno` arriva dalla query cosi' com'e' -- una stringa o `None` -- e va
    all'archivio senza essere interpretato qui: e' `ObservationsStore.
    facts()` a sapere cosa significa "nessun filtro" (`giorno=None`, gli
    oggetti piu' recenti di ogni giorno). Un formato malformato non solleva:
    l'archivio confronta per uguaglianza esatta, e una data che non
    combacia con nessuna riga torna semplicemente un elenco vuoto -- non un
    errore, perche' "nessun oggetto per quel giorno" e' un esito legittimo
    (un giorno in cui la casa non ha fatto niente di osservabile), non un
    guasto.

    **Il corpo porta anche `traduzioni`**, e non e' un di piu': *«non ho
    potuto leggere le traduzioni»* e *«questo stato non ha traduzione»* sono
    DUE FATTI DIVERSI, e produrre la stessa riga per entrambi sarebbe far
    indovinare a chi legge. Chi produce il motivo lo etichetta
    (`proxy/state_translations.StateTranslations.read`), la rotta lo
    trasporta, la pagina lo dice. La tabella vera (801 chiavi, 65 KB) NON
    viaggia: resta in cache dentro l'add-on.
    """
    store = request.app.get("observations")
    if store is None:
        return web.json_response(
            {"facts": [], "error": "archivio non disponibile"}, status=503)
    day = request.query.get("day") or None
    report = await _translations_report(request.app)
    facts = _with_rendered_states(store.facts(day=day), report)
    declared = {key: value for key, value in report.items() if key != "risorse"}
    return web.json_response({"facts": facts, "traduzioni": declared})


async def _translations_report(app) -> dict:
    """L'esito etichettato della lettura delle traduzioni, per questa casa.

    La coppia `(versione_ha, lingua)` viene dal sistema di riferimento che
    l'anagrafe ha gia' distillato da `Config.as_dict()`
    (`home_space.topology.reference_frame`): non una seconda lettura verso
    Home Assistant a ogni pagina, e non una seconda idea di "lingua della
    casa". Nessuna delle due chiavi si indovina: senza, la cache lo dichiara
    e la pagina lo dice.
    """
    cache = app.get("state_translations")
    if cache is None:
        return {"lette": False,
                "motivo": "la lettura delle traduzioni non e' collegata a questa istanza"}
    home_space_store = app.get("home_space_store")
    frame = home_space_store.reference_frame() if home_space_store is not None else {}
    return await cache.read(ha_version=frame.get("versione_ha"),
                            language=frame.get("lingua"))


def _with_rendered_states(facts: list[dict], report: dict) -> list[dict]:
    """Gli stessi oggetti, con `corpo.stato_reso` accanto a `corpo.stato`
    dove una resa esiste.

    **Il grezzo non si tocca mai.** `stato` resta esattamente quello che
    l'archivio ha scritto -- e' il fatto, e la pagina deve poterlo mostrare
    quando non c'e' altro da mostrare.

    **`stato_reso` TACE quando non c'e' resa**, come ogni altra chiave del
    corpo che non ha niente da dire: uno `stato_reso: null` sarebbe un buco
    travestito da dato, e una copia del grezzo sarebbe peggio ancora --
    direbbe «tradotto» di uno stato che HA non traduce. Chi legge distingue i
    due silenzi guardando `traduzioni.lette`: a `true`, la chiave assente
    significa «questo stato non ha traduzione, e HA stesso mostrerebbe il
    grezzo»; a `false`, significa «non l'abbiamo potuto chiedere», e il motivo
    e' li' accanto.

    `body.get("stato")` non e' mai `unavailable`/`unknown`: `facts` arriva da
    `ObservationsStore.facts()`, che legge cio' che `mind/facts.py::
    aggregate_day` ha scritto -- e quella funzione scarta i due stati prima
    di aprire un episodio (revisione del tratto v3.22.2..HEAD, rilievo R5:
    le due etichette nostre che questa funzione portava per quel caso erano
    un ramo morto, mai raggiungibile da qui, rimosso insieme a loro).
    """
    resources = report.get("risorse")
    rendered = []
    for fact in facts:
        body = fact.get("corpo")
        subject = fact.get("protagonista")
        if not isinstance(body, dict) or not isinstance(subject, str):
            rendered.append(fact)
            continue
        if subject.startswith(NOT_ENTITY_PREFIXES) or "." not in subject:
            rendered.append(fact)
            continue
        translated = state_translation(
            body.get("stato"),
            domain=subject.split(".")[0],
            device_class=body.get("classe"),
            component_resources=resources if isinstance(resources, dict) else {})
        if translated is None:
            rendered.append(fact)
            continue
        rendered.append({**fact, "corpo": {**body, "stato_reso": translated}})
    return rendered
