"""Le due rotte della pagina dell'osservatore (fetta «l'osservatore», Task 7:
docs/design/2026-08-26-l-osservatore.md §7).

Non serializzano niente per conto proprio. `Watcher.watching()` e
`ObservationsStore.facts()` gia' tornano la forma che la pagina mostra --
una seconda forma costruita qui la farebbe divergere il primo giorno in cui
qualcuno aggiunge un campo da una parte sola (fondamenta 3).

**L'unica eccezione, e porta il suo perche' (fetta «lo stato», 07/09/2026):
la RESA dello stato.** L'archivio continua a scrivere lo stato GREZZO --
`heat`, `not_home`, `triggered` -- perche' e' quello il fatto, ed e' quello
che `mind/facts.py` confronta con `_RESTING`/`_UNKNOWN` per aprire e chiudere
gli episodi: scriverci «Riscaldamento» romperebbe l'aggregazione, e tenere
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

from aiohttp import web

from ..proxy.state_translations import state_translation

# I soggetti che NON sono entita' di Home Assistant: una condizione di
# sistema, una voce del registro di errori, un'esecuzione di automazione. Il
# loro `corpo.stato` non e' uno stato di HA (`aperto`, `setup_retry`,
# `chiuso`: parole di HIRIS e della configurazione, non del vocabolario degli
# stati), e cercargli una traduzione vorrebbe dire spaccare `automazione:
# automation.x` sul punto e chiedere a HA il dominio «automazione:automation»,
# che non esiste su nessuna casa. Lo stesso confine, con le stesse quattro
# parole, e' gia' scritto in `mind/facts.py::genre_for`.
_NOT_ENTITY_PREFIXES = ("problema:", "integrazione:", "log:", "automazione:")


async def handle_watching(request: web.Request) -> web.Response:
    """Cosa sta guardando l'osservatore, e da dove viene ogni voce.

    `Watcher.watching()` porta gia' `provenienza` per ciascuna voce --
    oggi sempre `"pavimento"` -- che e' cio' che dice alla pagina se una
    voce si puo' togliere (spec §7). Non si ricalcola qui.
    """
    watcher = request.app.get("watcher")
    if watcher is None:
        return web.json_response(
            {"watching": [], "error": "osservatore non disponibile"}, status=503)
    return web.json_response({"watching": watcher.watching()})


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
        if subject.startswith(_NOT_ENTITY_PREFIXES) or "." not in subject:
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
