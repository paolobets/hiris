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

from ..home_space.behavior import without_body
from ..home_space.briefing import _MEASUREMENT_NAMES, compose
from ..home_space.historian import home_space_zone, house_timezone
from ..home_space.house import House
from ..home_space.reader import TABLES
from ..home_space.render import render_entity
from ..proxy.state_translations import read_for_house

#: Cio' che l'albero toglie dalla resa media di un'entita' (Tappa 9, F5, D1),
#: ognuno col suo perche': `area` e' il ramo in cui l'entita' sta, lo stesso
#: fatto scritto due volte; `attributi` sono le ceste dello stato, che la
#: pagina non disegna e che ripetute su ogni entita' della casa sarebbero la
#: parte piu' pesante della risposta. Il resto e' la riga di `search`, con la
#: stessa forma (fondamenta 3).
#:
#: Le ceste vanno fuori anche per un'altra ragione: questa porta non passa da
#: `privacy.redact_row` (lo applica solo `query_house`) e la leggono anche i
#: servizi firmati «lettore» e «utente». Con gli attributi uscirebbe la
#: posizione delle persone (N135-1, prova in `test_handlers_home_space.py`).
#: Lo `stato` invece esce senza filtro, e una `person` in «Lavoro» si legge
#: «Lavoro»: il filtro esiste per i modelli cloud (spec del 29/09/2026, §3),
#: e chi amministra lo vede uguale in Home Assistant. Non e' una svista da
#: allineare a `search`.
_TREE_DROPS = ("area", "attributi")
#: Cio' che l'albero toglie dal nodo di un'area (D3): alias ed etichette
#: dell'area non li disegna nessuna pagina, e la chat li ha da `render_area`.
_AREA_DROPS = ("alias", "etichette")
#: Le liste di entita' di un nodo d'area (`topology._area_node`).
_ENTITY_LISTS = ("entita", "entita_nascoste", "entita_disabilitate")


def _tree(house: House, translations: dict, zone) -> list[dict]:
    """L'albero della casa, con ogni entita' resa da `render.render_entity`
    alla media (Tappa 9, F5, D1).

    Fino al 12/10/2026 l'entita' era la voce dell'anagrafe, con la classe e
    l'unita' rilette dal vivo (`_with_live_kind`, B-17): una forma sua, con
    `piattaforma`, `nascosta` e le etichette per id, mentre la chat leggeva
    `integrazione`, `fuori` e le etichette col nome. Ora e' la stessa resa,
    meno `_TREE_DROPS`. Le voci dell'albero non si toccano: escono copie."""
    out = []
    for floor in house.hierarchy():
        areas = []
        for area in floor.get("aree") or []:
            area = {key: value for key, value in area.items() if key not in _AREA_DROPS}
            for key in _ENTITY_LISTS:
                if key in area:
                    area[key] = [_tree_entity(house, entry, translations, zone)
                                 for entry in area[key]]
            areas.append(area)
        out.append({**floor, "aree": areas})
    return out


def _tree_entity(house: House, entry, translations: dict, zone):
    if not isinstance(entry, dict) or not entry.get("id"):
        return entry
    # Alla media la resa non compone i `comandi`, gli unici che leggono i
    # giudizi: `None` lo dice (`tests/test_judgments_passed_in_production.py`).
    row = render_entity(house, entry["id"], "media", zone=zone, translations=translations,
                        judgments=None)
    return {key: value for key, value in row.items() if key not in _TREE_DROPS}



async def handle_get_home_space(request: web.Request) -> web.Response:
    store = request.app.get("home_space_store")
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
            "anagrafe_letta_il": None, "non_disponibili": None,
            "non_disponibili_letti_il": None, "conteggi": {}, "piani": [],
            # `None` e non `{}`: qui non e' "la casa non dichiara un sistema
            # di riferimento", e' "non abbiamo letto niente". La stessa
            # distinzione di `non_disponibili` qui sopra.
            "sistema_di_riferimento": None,
            # Un vocabolario, non un fatto della casa: esce anche qui, e la
            # risposta ha la stessa forma nei due rami.
            "nomi_misure": _MEASUREMENT_NAMES,
            # Stesso principio di "non_disponibili" qui sopra, applicato al
            # comportamento: `senza_corpo: 0` affermerebbe "conosco tutto",
            # e senza archivio non lo sappiamo -- resta `None`. `conteggi`,
            # come `conteggi`/`piani` sopra, e' un contenitore naturale e
            # resta vuoto. `problemi`/`corpi_non_letti` restano `None` per
            # lo stesso motivo di `senza_corpo`: un elenco vuoto affermerebbe
            # "nessun problema", e senza archivio non lo sappiamo.
            # `None` per lo stesso motivo di tutti gli altri qui sopra: un
            # esito vuoto affermerebbe «l'albero e' stato confrontato e
            # combacia», e qui non si e' confrontato niente.
            "confronto": None,
            "comportamento": {"letto_il": None, "conteggi": {}, "senza_corpo": None,
                              "problemi": None, "corpi_non_letti": None,
                              "conservato": None},
            "plance": {"lette_il": None, "non_disponibili": None, "conservato": None,
                       "voci": []},
        })
    home_space = store.read()
    unavailable = store.unavailable()
    behavior_entries = store.behavior()
    behavior_counts: dict[str, int] = {}
    for v in behavior_entries:
        behavior_counts[v["tipo"]] = behavior_counts.get(v["tipo"], 0) + 1
    # Quante voci HIRIS conosce solo di nome.
    unknown_bodies = len(without_body(behavior_entries, store.unread_bodies()))
    # La casa di questa richiesta, letta come la leggono tutti
    # (`House.read`): anagrafe, specchio e registri caduti in un posto. Le
    # parole degli stati e il fuso, come nella ricerca della chat.
    house = House.read(store, request.app.get("entity_cache"))
    translations = await read_for_house(request.app.get("state_translations"),
                                        store.reference_frame())
    zone = home_space_zone(house_timezone(store))
    return web.json_response({
        "anagrafe_letta_il": store.updated_at(),
        # I registri che non hanno risposto all'ultima lettura. Senza questo
        # campo una casa senza piani e un registro dei piani caduto sarebbero
        # la stessa schermata.
        "non_disponibili": unavailable,
        # E per ognuno, quando e' stata letta la copia che l'anagrafe tiene al
        # suo posto (`HomeSpace.unavailable_since`, S-36): `None` se quel
        # registro non ha mai risposto e la tabella e' vuota.
        "non_disponibili_letti_il": store.unavailable_since(),
        # Le tabelle esposte, non quelle interne (`reader.INTERNAL_TABLES`, B-50).
        "conteggi": {key: len(home_space[key]) for key in TABLES if key in home_space},
        # Il sistema di riferimento della casa: unita', fuso, valuta, lingua,
        # versione di Home Assistant. Esposto qui e non solo nel nucleo perche'
        # e' lo stesso fatto: se il modello lo legge nel digesto e la pagina no,
        # sono due case diverse a seconda della porta da cui entri.
        "sistema_di_riferimento": store.reference_frame(),
        # Le parole con cui si legge `unita` qui sopra, nell'ordine in cui la
        # casa si legge: la tabella del nucleo, mandata a chi disegna l'albero
        # invece di ricopiata nel JavaScript (C-09, Tappa 4, Task 5).
        "nomi_misure": _MEASUREMENT_NAMES,
        # Ogni entita' e' la resa media, meno `_TREE_DROPS` (Tappa 9, F5).
        "piani": _tree(house, translations, zone),
        # L'esito dell'ultimo confronto fra l'albero qui sopra e cio' che Home
        # Assistant risponde su un campione di aree
        # (`server.tree_comparison_round`, verdetto in
        # `topology.compare_with_home_assistant`).
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
        # parole: le frasi le costruisce `briefing._comparison_notice` per chi
        # legge un testo, qui serve il dato per chi disegna. `None` quando
        # nessun giro e' ancora passato -- mai `{}`, che direbbe «confrontato,
        # e non c'era niente da dire».
        "confronto": request.app.get("tree_comparison"),
        "comportamento": {
            "letto_il": store.behavior_loaded_at(),
            "conteggi": behavior_counts,
            # Il campo che conta di piu': quante voci HIRIS conosce solo di
            # nome. Le automazioni scritte a mano non stanno nei file, e di
            # quelle sa il nome e non il corpo -- e' la misura onesta di
            # quanto sa davvero della casa. `corpo is None` e non falsy:
            # un corpo vuoto (`{}`, presente ma senza niente dentro) e' un
            # fatto diverso da un corpo assente, e non va confuso con esso.
            "senza_corpo": unknown_bodies,
            # Cio' che l'ultima lettura NON ha potuto concludere con
            # certezza (id duplicati, script vuoti, voci malformate) e i
            # file che non si sono letti, con la ragione. Li costruisce
            # `behavior.reread()`.
            "problemi": store.behavior_problems(),
            "corpi_non_letti": store.unread_bodies(),
            # La replica conservata (G-16): `None` quando e' quella
            # dell'ultima rilettura, altrimenti perche' non e' stata
            # sostituita e di quando e'. Lo stesso oggetto che il nucleo
            # dice a parole.
            "conservato": store.behavior_kept(),
        },
        "plance": {
            "lette_il": store.dashboards_loaded_at(),
            # Le plance/percorsi che l'ultima lettura non e' riuscita a
            # risolvere -- stesso principio di "non_disponibili" sopra,
            # applicato alle plance invece che ai registri.
            "non_disponibili": store.unavailable_dashboards(),
            "conservato": store.dashboards_kept(),
            # Titolo e percorso soltanto (D3): li sceglie il lettore,
            # `behavior.reread_dashboards`, la casa di questo fatto.
            "voci": store.dashboards(),
        },
    })


def house_of(app) -> House:
    """La casa di adesso (`home_space.house.House`) dagli archivi vivi di
    `app`: anagrafe e specchio in una lettura. Vale un turno, e chi la riceve
    non la mette mai in `app[...]` (R12): il turno dopo ne legge una nuova."""
    return House.read(app.get("home_space_store"), app.get("entity_cache"))


def compose_briefing(app, house: House | None = None) -> tuple[str, dict]:
    """Il nucleo composto dagli archivi vivi dell'app -- (testo, riepilogo).

    Condivisa da `handle_get_briefing` (GET /api/briefing, la verifica dal vivo),
    da `handlers_chat.compose_chat_context` (il contesto che il modello
    riceve davvero, su ENTRAMBI i percorsi di chat: il sincrono e quello in
    abbonamento) e dal turno di una promessa (`keeper/exchange.py`): la
    STESSA composizione, non due che potrebbero divergere.

    Prende `app` (un `web.Application`, o l'equivalente `.get()`-abile nei
    test) invece di un `web.Request`: il turno di una promessa non ha una
    request in corso.

    `house` e' la casa del turno (`house_of`), quando il chiamante la
    condivide con gli strumenti (R18): nucleo e `search` guardano la STESSA
    anagrafe e lo STESSO specchio, e la gerarchia si costruisce una volta.
    Senza, se ne legge una qui.
    """
    if house is None:
        house = house_of(app)
    home_space_store = app.get("home_space_store")
    memory_store = app.get("memory_store")

    if home_space_store is None:
        # Difesa, non stato atteso: come in `handle_get_home_space` qui sopra,
        # in produzione questo ramo non dovrebbe mai scattare (se
        # `_on_startup` fallisce, l'add-on non parte affatto). Senza
        # archivio non c'e' una casa da comporre -- `compose()` riceve una
        # casa vuota, non inventata -- ma soprattutto lo stato non puo'
        # essere dichiarato affidabile: vedi `reliable_state` sotto.
        behavior: list[dict] = []
        behavior_problems: tuple[str, ...] = ()
        unread_bodies: dict[str, str] = {}
        behavior_kept: dict | None = None
        reference_frame: dict = {}
    else:
        behavior = home_space_store.behavior()
        # IMPORTANT ⑧: senza questi due, il PERCHE' di un'automazione
        # sconosciuta (id duplicato, file malformato) non arrivava mai al
        # modello -- `/api/home-space` li espone gia', `compose()` non aveva un
        # parametro per riceverli.
        behavior_problems = tuple(home_space_store.behavior_problems())
        unread_bodies = home_space_store.unread_bodies()
        # G-16: la replica conservata dalla guardia si dichiara, con la data.
        behavior_kept = home_space_store.behavior_kept()
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

    # Lo specchio dello stato, quello della casa del turno e non riletto a mano:
    # `house.House.read` lo prende da `home_space.topology.read_mirror`, la
    # stessa che usano `search` e la correzione dei ricordi, che compone lei se
    # lo specchio e' leggibile (una cache assente, finta senza `all_states`, mai
    # caricata o guasta non lo e'). Fino al 04/10/2026 una lettura che sollevava
    # lasciava lo stato «affidabile» e le capacita' «non guardate»: ora e' non
    # leggibile e basta, come gli altri tre casi.
    #
    # Dal 29/09/2026 il nucleo non porta piu' lo stato del momento («Notevole
    # adesso» e' uscita): dello specchio servono due cose sole. `state`, perche'
    # `compose()` distingue ancora «ho guardato» da «non ho potuto guardare»
    # (CRITICAL ②); `attributes`, per la sezione «cosa si puo' chiedere alle
    # cose di casa», che aggrega le CAPACITA'. Le classi e i nomi dello
    # specchio -- che servivano solo alle righe di quella sezione -- non si
    # leggono piu' qui. Con lo specchio non leggibile `compose()` dice «non ho
    # guardato» e non legge gli attributi (`reliable_state`, sotto).
    mirror = house.mirror

    # I guasti che Home Assistant ha gia' diagnosticato (`repairs/list_issues`).
    #
    # DOVE VIVONO, e perche' non nell'archivio. In RAM, in `app["ha_problems"]`,
    # accanto a `entity_cache` -- una fotografia riletta ogni pochi minuti da
    # `server.reread_ha_problems`, mai una tabella. La ragione e' scritta per
    # esteso li'; in breve e' la stessa per cui `state` non entra nel sistema di
    # riferimento (vedi `home_space/topology.reference_frame`): un problema e'
    # momentaneo, l'utente lo ripara con un clic in Home Assistant, e un
    # archivio che si rilegge di rado continuerebbe ad annunciarlo per ore dopo
    # che non c'e' piu'. Un falso allarme ripetuto in ogni prompt e'
    # esattamente il rumore che questa fetta esiste per non produrre.
    #
    # Si legge con `.get()` e si passa cosi' com'e': `None` (nessuno l'ha
    # ancora letto, o un'app di prova che non lo cabla) resta `None` fino a
    # `compose()`, che sa distinguerlo da «letto e vuoto». Tradurlo qui in `{}`
    # o in una lista vuota affermerebbe che la casa non ha guasti.
    problems = app.get("ha_problems")

    # L'esito dell'ultimo giro di verifica dell'albero (`server.tree_comparison_round`).
    #
    # Vive dove vivono i problemi, in RAM e non in archivio, e per la stessa
    # ragione: un confronto e' momentaneo due volte -- la casa cambia, e la
    # replica si ricostruisce da sola al primo evento di registro. Una tabella
    # riletta di rado continuerebbe ad annunciare per ore una divergenza gia'
    # rientrata, che e' il falso allarme che questa fetta esiste per non
    # produrre (stesso ragionamento di `home_space/topology.reference_frame`
    # su `state`).
    #
    # Si legge con `.get()` e si passa cosi' com'e': `None` (nessun giro
    # ancora fatto, o un'app di prova che non lo cabla) resta `None` fino a
    # `compose()`, che sa distinguerlo da «guardato e combacia».
    comparison = app.get("tree_comparison")

    # Affidabile SOLO se sappiamo sia quali entita' esistono (archivio della
    # casa) sia in che stato sono adesso (inventario vivo pronto). Una delle
    # due sole non basta: un archivio letto ma una cache non ancora caricata
    # produrrebbe uno stato vuoto che il nucleo leggerebbe come "niente da
    # dire" invece di "non ho potuto guardare".
    reliable_state = home_space_store is not None and mirror.readable

    return compose(
        house.home_space, behavior, memories, mirror.state,
        unavailable=house.unavailable,
        floors=house.hierarchy(),
        reliable_state=reliable_state,
        behavior_problems=behavior_problems,
        unread_bodies=unread_bodies,
        behavior_kept=behavior_kept,
        reference_frame=reference_frame,
        problems=problems,
        comparison=comparison,
        attributes=mirror.attributes,
        # L'orologio entra QUI, nell'unico compositore di produzione (chat
        # sincrona, ponte, promesse e GET /api/briefing passano tutti di qua), perche'
        # `compose` e' pura e non legge nulla da sola. Senza questa riga il
        # parametro esisterebbe, i test di `compose` passerebbero, e il modello
        # continuerebbe a indovinare l'ora quando `promise` gli chiede di
        # risolvere «fra un'ora» -- che e' il difetto misurato il 21/08/2026.
        now=time.time(),
    )


async def handle_get_briefing(request: web.Request) -> web.Response:
    """GET /api/briefing: il testo ESATTO che il modello ha sempre davanti, e
    il riepilogo di quanto ne resta fuori.

    Serve all'utente per capire, prima di accendere la chat, se HIRIS sta
    guardando la casa giusta -- e a noi per la verifica dal vivo, che qui
    e' l'unica prova che conta: `compose()` e' pura e coperta da
    `tests/test_briefing.py`, ma nessun test dice se QUESTA casa, letta da
    QUESTO Home Assistant, produce un nucleo sensato.

    La composizione vera e' in `compose_briefing()` qui sopra, condivisa
    con la chat (`handlers_chat.compose_chat_context`) -- questo handler resta un guscio
    sottile che la chiama e la serializza, cosi' i due punti non possono
    raccontare due nuclei diversi della stessa casa.
    """
    text, summary = compose_briefing(request.app)
    return web.json_response({"text": text, "summary": summary})
