"""La vista HTTP dell'anagrafe, in sola lettura.

Esiste perche' in questo progetto una cosa si dichiara funzionante solo dopo
averla vista girare: la suite verde non e' una prova. Senza una vista, nessuno
puo' guardare l'anagrafe su un Home Assistant vero.

Nota per chi legge il censimento: il percorso non compare qui per esteso di
proposito. Lo strumento (`scripts/censimento.py`) spoglia solo i commenti `#`,
non le docstring -- e la sua stessa registrazione (`app.router.add_get(...)`)
viene rimossa dal corpus perche' e' autocitazione. Se la docstring ripetesse
il percorso, la rotta risulterebbe "citata fuori dai test" per colpa delle
proprie parole e sparirebbe dal censimento invece di comparire come solo-test.
"""
from __future__ import annotations

import time

from aiohttp import web

from ..casa.anagrafe import category_names, hierarchy, live_mirror
from ..casa.nucleo import compose
from ..proxy.entity_cache import inventory_is_readable


def _categories_by_scope(home_space: dict) -> dict[str, dict[str, str]]:
    """`{scope: {category_id: name}}` per chi disegna l'albero.

    Esce la MAPPA e non il nome ripetuto su ogni entita' categorizzata: li'
    sarebbe lo stesso fatto scritto mille volte. Stessa scelta delle
    etichette, appena sopra.

    La sorgente e' `anagrafe.category_names`, la stessa che usano
    `guarda` e l'indice di `cerca`: qui si cambia solo la FORMA (le chiavi a
    coppia non attraversano JSON), mai il contenuto -- due mappe costruite
    ognuna per conto proprio sarebbero due nomi diversi per la stessa
    categoria a seconda della porta.
    """
    categories: dict[str, dict[str, str]] = {}
    for (scope, category_id), name in category_names(home_space).items():
        categories.setdefault(scope, {})[category_id] = name
    return categories


async def handle_get_home_space(request: web.Request) -> web.Response:
    store = request.app.get("archivio_casa")
    if store is None:
        # Difesa, non stato atteso: in produzione questo ramo non dovrebbe mai
        # scattare. Se `_on_startup` fallisce, l'add-on non parte affatto; un
        # Home Assistant non ancora pronto all'avvio produce un archivio
        # VUOTO (create_app() lo istanzia comunque), non assente. Resta qui
        # come rete di sicurezza per un futuro in cui l'ordine di avvio
        # cambiasse -- una difesa che non scatta e' giusta, non va tolta.
        #
        # `non_disponibili: None`, non `[]`: `[]` afferma "tutti i registri
        # ok", e qui non lo sappiamo -- non abbiamo nemmeno letto niente.
        return web.json_response({
            # Nome proprio, non "aggiornata_il" generico: tre sezioni di
            # questa risposta hanno ciascuna la propria data (anagrafe,
            # comportamento, plance) e un unico campo di primo livello senza
            # nome che dica di cosa parla prometterebbe una freschezza che
            # vale solo per una delle tre.
            "anagrafe_letta_il": None, "non_disponibili": None, "conteggi": {}, "piani": [],
            # `None` e non `{}`: qui non e' "la casa non dichiara un sistema
            # di riferimento", e' "non abbiamo letto niente". La stessa
            # distinzione di `non_disponibili` qui sopra.
            "sistema_di_riferimento": None,
            # `None` e non `{}`: qui non e' "la casa non ha etichette", e'
            # "non abbiamo letto niente".
            "etichette": None, "categorie": None,
            # Stesso principio di "non_disponibili" qui sopra, applicato al
            # comportamento: `senza_corpo: 0` affermerebbe "conosco tutto",
            # e senza archivio non lo sappiamo -- resta `None`. `conteggi` e
            # `voci`, come `conteggi`/`piani` sopra, sono contenitori naturali
            # e restano vuoti. `problemi`/`file_non_letti` restano `None` per
            # lo stesso motivo di `senza_corpo`: un elenco vuoto affermerebbe
            # "nessun problema", e senza archivio non lo sappiamo.
            # `None` per lo stesso motivo di tutti gli altri qui sopra: un
            # esito vuoto affermerebbe «l'albero e' stato confrontato e
            # combacia», e qui non si e' confrontato niente.
            "confronto": None,
            "comportamento": {"letto_il": None, "conteggi": {}, "senza_corpo": None,
                              "problemi": None, "file_non_letti": None, "voci": []},
            "plance": {"lette_il": None, "non_disponibili": None, "voci": []},
        })
    home_space = store.read()
    unavailable = store.unavailable()
    behavior_entries = store.behavior()
    behavior_counts: dict[str, int] = {}
    for v in behavior_entries:
        behavior_counts[v["tipo"]] = behavior_counts.get(v["tipo"], 0) + 1
    return web.json_response({
        "anagrafe_letta_il": store.updated_at(),
        # I registri che non hanno risposto all'ultima lettura. Senza questo
        # campo una casa senza piani e un registro dei piani caduto sarebbero
        # la stessa schermata.
        "non_disponibili": unavailable,
        "conteggi": {key: len(value) for key, value in home_space.items()},
        # Il sistema di riferimento della casa: unita', fuso, valuta, lingua,
        # versione di Home Assistant. Esposto qui e non solo nel nucleo perche'
        # e' lo stesso fatto: se il modello lo legge nel digesto e la pagina no,
        # sono due case diverse a seconda della porta da cui entri.
        "sistema_di_riferimento": store.reference_frame(),
        "piani": hierarchy(home_space, unavailable),
        # I NOMI delle etichette, id -> nome.
        #
        # `hierarchy()` mette sulle aree e sulle entita' i soli `label_id` --
        # e' cosi' che Home Assistant li manda -- e senza questa mappa chi
        # legge il payload puo' solo mostrare lo slug: «da_controllare» invece
        # di «Da controllare», una parola che l'utente non ha mai scritto e che
        # non cambierebbe nemmeno rinominando l'etichetta.
        #
        # E' lo stesso difetto gia' chiuso su `guarda` (`anagrafe.labels_with_name`),
        # che pero' risolve i nomi DENTRO la risposta perche' li' esce un
        # dettaglio. Qui esce l'albero intero: ripetere il nome su ogni entita'
        # etichettata sarebbe lo stesso fatto scritto mille volte. Esce la
        # mappa, una volta, e chi disegna la applica.
        "etichette": {e["id"]: e.get("nome") or e["id"]
                      for e in home_space.get("etichette") or [] if e.get("id")},
        # Le CATEGORIE, con la stessa forma e per la stessa ragione -- ma
        # annidate per AMBITO, perche' il registro di Home Assistant e'
        # partizionato (`automation`, `script`, `scene`, `helpers`) e due
        # categorie omonime in ambiti diversi sono cose diverse. Appiattirle
        # su un id solo qui rimetterebbe in piedi l'ambiguita' che la chiave
        # `(ambito, id)` dell'archivio esiste per chiudere.
        #
        # Perche' anche qui, e non solo in `guarda`: la fetta delle categorie
        # ha cablato `anagrafe.categories_with_name` in `domande.py` e
        # nell'indice di `cerca`, e ha saltato QUESTA porta -- cosi' la stessa
        # categoria usciva col nome dallo strumento e con l'id grezzo dalla
        # pagina. E' il pattern che la review ha nominato («una fetta unifica
        # una regola e salta una porta»), ricomparso dentro una fetta scritta
        # apposta per non ripeterlo.
        "categorie": _categories_by_scope(home_space),
        # L'esito dell'ultimo confronto fra l'albero qui sopra e cio' che Home
        # Assistant risponde su un campione di aree
        # (`server.tree_comparison_round`, verdetto in
        # `anagrafe.compare_with_home_assistant`).
        #
        # Esce ANCHE da qui, e non solo nel nucleo, per la stessa ragione del
        # sistema di riferimento poco sopra: e' lo stesso fatto, e se il
        # modello leggesse una divergenza che la pagina non mostra sarebbero
        # due case diverse a seconda della porta. Ed e' proprio qui che serve
        # di piu': questa risposta disegna l'albero, e una divergenza e'
        # esattamente cio' che chi guarda l'albero deve poter vedere sul ramo
        # che la porta.
        #
        # Esce grezzo (`aree_totali`, `guardate`, `letto_il`) e non gia' in
        # parole: le frasi le costruisce `nucleo._comparison_notice` per chi
        # legge un testo, qui serve il dato per chi disegna. `None` quando
        # nessun giro e' ancora passato -- mai `{}`, che direbbe «confrontato,
        # e non c'era niente da dire».
        "confronto": request.app.get("confronto_albero"),
        "comportamento": {
            "letto_il": store.behavior_loaded_at(),
            "conteggi": behavior_counts,
            # Il campo che conta di piu': quante voci HIRIS conosce solo di
            # nome. Le automazioni scritte a mano non stanno nei file, e di
            # quelle sa il nome e non il corpo -- e' la misura onesta di
            # quanto sa davvero della casa. `corpo is None` e non falsy:
            # un corpo vuoto (`{}`, presente ma senza niente dentro) e' un
            # fatto diverso da un corpo assente, e non va confuso con esso.
            "senza_corpo": sum(1 for v in behavior_entries if v["corpo"] is None),
            # Cio' che l'ultima lettura NON ha potuto concludere con
            # certezza (id duplicati, script vuoti, voci malformate) e i
            # file che non si sono letti, con la ragione. Costruiti con
            # cura da comportamento.compose()/reread() -- prima morivano in
            # una riga di log, invisibili a chi guarda solo /api/home-space.
            "problemi": store.behavior_problems(),
            "file_non_letti": store.unloaded_files(),
            "voci": behavior_entries,
        },
        "plance": {
            "lette_il": store.dashboards_loaded_at(),
            # Le plance/percorsi che l'ultima lettura non e' riuscita a
            # risolvere -- stesso principio di "non_disponibili" sopra,
            # applicato alle plance invece che ai registri.
            "non_disponibili": store.unavailable_dashboards(),
            "voci": store.dashboards(),
        },
    })


def compose_briefing(app) -> tuple[str, dict]:
    """Il nucleo composto dagli archivi vivi dell'app -- (testo, riepilogo).

    Condivisa da `handle_get_briefing` (GET /api/briefing, la verifica dal vivo)
    e da `handlers_chat.compose_chat_context` (il contesto che il modello
    riceve davvero -- dalla fetta "il ponte riceve il nucleo", parita' A, su
    ENTRAMBI i percorsi di chat: il sincrono e quello in abbonamento): la
    STESSA composizione, non due che potrebbero divergere -- e' esattamente la
    sovrapposizione n.1 della mappa del prodotto (vedi
    docs/design/2026-08-05-la-conoscenza-di-hiris.md, §7) che questa
    condivisione esiste per chiudere: prima la chat vedeva una mappa senza
    ritratto, il resto del sistema il ritratto senza la mappa.

    Prende `app` (un `web.Application`, o l'equivalente `.get()`-abile nei
    test) invece di un `web.Request`, cosi' un chiamante che non ha una
    request in corso (nessuno oggi, ma non c'e' motivo di legarla) puo'
    comunque chiamarla.

    Il resto del ragionamento -- perche' `unavailable` va propagato,
    perche' `MemoryStore.fetch(limit=count())` e non il default,
    perche' `reliable_state` richiede ENTRAMBI l'archivio e un inventario
    vivo pronto -- e' invariato da prima di questo refactor: vedi i
    commenti storici in git blame su questa funzione (era il corpo di
    `handle_get_briefing`) per il dettaglio di ciascuna scelta.
    """
    home_space_store = app.get("archivio_casa")
    memory_store = app.get("archivio_memoria")
    cache = app.get("entity_cache")
    # Stessa difesa di `handle_list_entities`: una cache finta senza
    # `all_states` (o assente) non e' un inventario leggibile.
    if cache is not None and not hasattr(cache, "all_states"):
        cache = None

    if home_space_store is None:
        # Difesa, non stato atteso: come in `handle_get_home_space` qui sopra,
        # in produzione questo ramo non dovrebbe mai scattare (se
        # `_on_startup` fallisce, l'add-on non parte affatto). Senza
        # archivio non c'e' una casa da comporre -- `compose()` riceve una
        # casa vuota, non inventata -- ma soprattutto lo stato non puo'
        # essere dichiarato affidabile: vedi `reliable_state` sotto.
        home_space: dict = {}
        unavailable: tuple[str, ...] = ()
        behavior: list[dict] = []
        behavior_problems: tuple[str, ...] = ()
        unloaded_behavior_files: dict[str, str] = {}
        reference_frame: dict = {}
    else:
        home_space = home_space_store.read()
        unavailable = tuple(home_space_store.unavailable())
        behavior = home_space_store.behavior()
        # IMPORTANT ⑧: senza questi due, il PERCHE' di un'automazione
        # sconosciuta (id duplicato, file malformato) non arrivava mai al
        # modello -- `/api/home-space` li espone gia', `compose()` non aveva un
        # parametro per riceverli.
        behavior_problems = tuple(home_space_store.behavior_problems())
        unloaded_behavior_files = home_space_store.unloaded_files()
        # Unita', fuso, valuta, lingua: senza, il modello legge "72" senza
        # sapere in che scala e "alle 8" senza sapere in che fuso.
        reference_frame = home_space_store.reference_frame()

    # CRITICAL ①: il default di `MemoryStore.fetch()` e' `limit=20`.
    # Con `count()` (scritto apposta per dichiarare questa differenza) si
    # richiamano TUTTI i ricordi, e si lascia decidere al taglio di
    # `compose()` -- che dichiara sempre, nel nucleo stesso, quanti ne
    # restano fuori (`excluded_memories`). Prima di questo fix, i ricordi
    # oltre il ventesimo sparivano PRIMA ancora di arrivare a `compose()`,
    # e il riepilogo giurava "excluded_memories: 0" su una casa con 200
    # ricordi veri e solo 20 nel nucleo.
    if memory_store is not None:
        memories = memory_store.fetch(limit=memory_store.count())
    else:
        memories = []

    # Lo specchio dello stato, dalla funzione condivisa e non riletto a mano:
    # `casa.anagrafe.live_mirror` e' la stessa che usano `guarda`, `cerca` e
    # la correzione dei ricordi. Prima questa porta -- che alimenta SIA
    # `GET /api/briefing` SIA il contesto della chat, cioe' la piu' importante --
    # se lo rileggeva da sola: una normalizzazione imparata li' non sarebbe mai
    # arrivata qui, e il modello avrebbe letto nel digesto stati che non
    # coincidono con quelli che ottiene chiamando `guarda`.
    #
    # `reported_classes` e' la ragione per cui questo cablaggio conta davvero: il
    # registro delle entita' non manda `device_class`, quindi senza queste
    # nessun allagamento e nessun allarme monossido entra in «Notevole adesso»
    # (vedi `anagrafe.actual_class`).
    state: dict[str, str] = {}
    reported_classes: dict[str, str] = {}
    if cache is not None:
        try:
            state, _names, _units, reported_classes, _since_when, _attributes = live_mirror(
                cache.all_states())
        except Exception:
            state, reported_classes = {}, {}

    # I guasti che Home Assistant ha gia' diagnosticato (`repairs/list_issues`).
    #
    # DOVE VIVONO, e perche' non nell'archivio. In RAM, in `app["problemi_ha"]`,
    # accanto a `entity_cache` -- una fotografia riletta ogni pochi minuti da
    # `server.reread_ha_problems`, mai una tabella. La ragione e' scritta per
    # esteso li'; in breve e' la stessa per cui `state` non entra nel sistema di
    # riferimento (vedi `casa/anagrafe.sistema_di_riferimento`): un problema e'
    # momentaneo, l'utente lo ripara con un clic in Home Assistant, e un
    # archivio che si rilegge di rado continuerebbe ad annunciarlo per ore dopo
    # che non c'e' piu'. Un falso allarme ripetuto in ogni prompt e'
    # esattamente il rumore che questa fetta esiste per non produrre.
    #
    # Si legge con `.get()` e si passa cosi' com'e': `None` (nessuno l'ha
    # ancora letto, o un'app di prova che non lo cabla) resta `None` fino a
    # `compose()`, che sa distinguerlo da «letto e vuoto». Tradurlo qui in `{}`
    # o in una lista vuota affermerebbe che la casa non ha guasti.
    problems = app.get("problemi_ha")

    # L'esito dell'ultimo giro di verifica dell'albero (`server.tree_comparison_round`).
    #
    # Vive dove vivono i problemi, in RAM e non in archivio, e per la stessa
    # ragione: un confronto e' momentaneo due volte -- la casa cambia, e la
    # replica si ricostruisce da sola al primo evento di registro. Una tabella
    # riletta di rado continuerebbe ad annunciare per ore una divergenza gia'
    # rientrata, che e' il falso allarme che questa fetta esiste per non
    # produrre (stesso ragionamento di `casa/anagrafe.sistema_di_riferimento`
    # su `state`).
    #
    # Si legge con `.get()` e si passa cosi' com'e': `None` (nessun giro
    # ancora fatto, o un'app di prova che non lo cabla) resta `None` fino a
    # `compose()`, che sa distinguerlo da «guardato e combacia».
    comparison = app.get("confronto_albero")

    # Affidabile SOLO se sappiamo sia quali entita' esistono (archivio della
    # casa) sia in che stato sono adesso (inventario vivo pronto). Una delle
    # due sole non basta: un archivio letto ma una cache non ancora caricata
    # produrrebbe uno stato vuoto che "Notevole adesso" leggerebbe come
    # "niente acceso" invece di "non ho potuto guardare".
    reliable_state = home_space_store is not None and inventory_is_readable(cache)

    return compose(
        home_space, behavior, memories, state,
        unavailable=unavailable,
        reliable_state=reliable_state,
        behavior_problems=behavior_problems,
        unloaded_behavior_files=unloaded_behavior_files,
        reference_frame=reference_frame,
        reported_classes=reported_classes,
        problems=problems,
        comparison=comparison,
        # L'orologio entra QUI, nell'unico compositore di produzione (chat
        # sincrona, ponte e GET /api/briefing passano tutti di qua), perche'
        # `compose` e' pura e non legge nulla da sola. Senza questa riga il
        # parametro esisterebbe, i test di `compose` passerebbero, e il modello
        # continuerebbe a indovinare l'ora quando `prometti` gli chiede di
        # risolvere «fra un'ora» -- che e' il difetto misurato il 21/08/2026.
        now=time.time(),
    )


async def handle_get_briefing(request: web.Request) -> web.Response:
    """GET /api/briefing: il testo ESATTO che il modello ha sempre davanti, e
    il riepilogo di quanto ne resta fuori.

    Serve all'utente per capire, prima di accendere la chat, se HIRIS sta
    guardando la casa giusta -- e a noi per la verifica dal vivo, che qui
    e' l'unica prova che conta: `compose()` e' pura e coperta da
    `tests/test_nucleo.py`, ma nessun test dice se QUESTA casa, letta da
    QUESTO Home Assistant, produce un nucleo sensato.

    La composizione vera e' in `compose_briefing()` qui sopra, condivisa
    con `handlers_chat.handle_chat` -- questo handler resta un guscio
    sottile che la chiama e la serializza, cosi' i due punti non possono
    raccontare due nuclei diversi della stessa casa.
    """
    text, summary = compose_briefing(request.app)
    return web.json_response({"text": text, "summary": summary})
