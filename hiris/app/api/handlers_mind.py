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
from ..mind.facts import day_boundaries
from ..mind.report import as_document

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


async def handle_report(request: web.Request) -> web.Response:
    """Il resoconto di un giorno, o la serie degli ultimi (spec §9).

    Tre forme, e la differenza fra loro e' il meccanismo delle **porzioni**:

    - `?day=2026-09-13` -- il resoconto di un giorno, com'e' archiviato;
    - `?day=...&formato=documento` -- lo stesso, reso in markdown: un terzo
      dei byte a parita' di contenuto (misurato il 13/09/2026: 146 KB contro
      46, su trenta giorni);
    - senza `day` -- **le misure degli ultimi giorni**, che e' la lettura che
      serve all'analista: due dei suoi tre inneschi sono confronti nel tempo,
      e con la cronaca dentro non ci starebbero in un prompt.

    **Un giorno mai aggregato torna 404, non un resoconto vuoto**: «quel
    giorno non e' successo niente» e «quel giorno non l'abbiamo guardato» sono
    due cose diverse, e l'analista deve poterle distinguere.
    """
    store = request.app.get("observations")
    if store is None:
        return web.json_response({"errore": "archivio non disponibile"},
                                 status=503)
    day = request.query.get("day") or None
    if day is None:
        # Solo le misure: la cronaca si chiede un giorno alla volta.
        # **E l'obiettivo di ogni giorno** (spec §11). Trovato dalla live
        # review del 15/09/2026: la migrazione lo aveva riempito su tutti e
        # venti i giorni archiviati, un giorno chiesto da solo lo portava, e
        # QUI si buttava -- proprio nella lettura per cui quella riga esiste.
        # Chi legge trenta giorni di misure in serie deve sapere se in mezzo la
        # domanda e' cambiata, o legge una tendenza dove c'e' un cambio di
        # domanda. Costa una frase per giorno; la cronaca e le forme restano
        # fuori, e si chiedono un giorno alla volta.
        serie = [{"giorno": r.get("giorno"), "obiettivo": r.get("obiettivo"),
                  "misure": r.get("misure") or []}
                 for r in store.reports(limit=30)]
        return web.json_response({"resoconti": serie})
    resoconto = store.report(day)
    if resoconto is None:
        return web.json_response(
            {"errore": f"il giorno {day} non e' stato aggregato"}, status=404)
    if request.query.get("formato") == "documento":
        return web.Response(text=as_document(resoconto),
                            content_type="text/markdown", charset="utf-8")
    return web.json_response({"resoconto": resoconto})


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
        return web.json_response({"errore": "archivio non disponibile"},
                                 status=503)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"errore": "corpo non leggibile"}, status=400)
    text = body.get("testo") if isinstance(body, dict) else None
    if not isinstance(text, str):
        return web.json_response(
            {"errore": "serve un campo `testo` con la frase dell'obiettivo."},
            status=400)
    if not text.strip():
        return web.json_response(
            {"errore": "un obiettivo vuoto non si scrive: e' la sola manopola "
                       "del prodotto, e senza criterio l'osservatore non sa "
                       "piu' cosa guardare."},
            status=400)
    written = store.set_objective(text)
    return web.json_response({"obiettivo": store.objective(),
                              "scritto": bool(written)})

async def handle_analysis(request) -> web.Response:
    """L'analisi di un giorno, o le ultime (spec §10).

    - `?day=2026-09-15` -- l'analisi di quel giorno;
    - senza `day` -- le ultime, dalla piu' recente.

    **Un giorno mai analizzato torna 404, non un'analisi vuota**: «ho guardato
    e non c'era niente da dire» e «non ho guardato» sono due cose diverse, e
    la prima e' una riga con zero osservazioni. Stessa legge del resoconto.
    """
    store = request.app.get("observations")
    if store is None:
        return web.json_response({"errore": "archivio non disponibile"},
                                 status=503)
    day = (request.query.get("day") or "").strip()
    if not day:
        return web.json_response({"analisi": store.analyses(limit=30)})
    found = store.analysis(day)
    if found is None:
        return web.json_response(
            {"errore": f"il giorno {day} non e' stato analizzato"}, status=404)
    return web.json_response({"analisi": _with_device_names(request.app, found)})


def _with_device_names(app, analysis: dict) -> dict:
    """L'analisi con i nomi dei dispositivi **risolti adesso**, dove mancano.

    **L'archivio dice cio' che sapeva; chi legge risolve cio' che puo' oggi.**
    Un'analisi si scrive una volta sola -- un giorno ne ha una -- e quella del
    15/09/2026 e' nata prima che i nomi dei dispositivi arrivassero: porta
    `nome: null`, e riscriverla costerebbe 35.000 token per cambiare
    un'etichetta.

    **Un'osservazione che il nome ce l'ha tiene il suo**: e' quello di allora,
    ed e' piu' vero di quello di adesso -- un dispositivo si puo' rinominare.
    E un dispositivo che l'anagrafe non conosce **resta senza**: chi legge vede
    l'identificatore, che e' la verita', non un buco.

    E' la stessa regola di `report.series_of_measures`, un piano piu' in la'.
    """
    casa = app.get("home_space_store")
    if casa is None:
        return analysis
    names = {str(d.get("id")): d.get("nome")
             for d in (casa.read() or {}).get("dispositivi") or []
             if d.get("id") and d.get("nome")}
    if not names:
        return analysis
    seen = []
    for line in analysis.get("osservazioni") or []:
        if isinstance(line, dict) and not line.get("nome"):
            found_name = names.get(line.get("soggetto"))
            line = {**line, "nome": found_name} if found_name else line
        seen.append(line)
    return {**analysis, "osservazioni": seen}
