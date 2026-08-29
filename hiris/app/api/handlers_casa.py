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

from ..casa.anagrafe import gerarchia, nomi_delle_categorie, specchio_vivo
from ..casa.nucleo import componi
from ..proxy.entity_cache import inventario_leggibile


def _mappa_categorie(casa: dict) -> dict[str, dict[str, str]]:
    """`{ambito: {category_id: nome}}` per chi disegna l'albero.

    Esce la MAPPA e non il nome ripetuto su ogni entita' categorizzata: li'
    sarebbe lo stesso fatto scritto mille volte. Stessa scelta delle
    etichette, appena sopra.

    La sorgente e' `anagrafe.nomi_delle_categorie`, la stessa che usano
    `guarda` e l'indice di `cerca`: qui si cambia solo la FORMA (le chiavi a
    coppia non attraversano JSON), mai il contenuto -- due mappe costruite
    ognuna per conto proprio sarebbero due nomi diversi per la stessa
    categoria a seconda della porta.
    """
    mappa: dict[str, dict[str, str]] = {}
    for (ambito, categoria_id), nome in nomi_delle_categorie(casa).items():
        mappa.setdefault(ambito, {})[categoria_id] = nome
    return mappa


async def handle_get_casa(request: web.Request) -> web.Response:
    archivio = request.app.get("archivio_casa")
    if archivio is None:
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
    casa = archivio.leggi()
    non_disponibili = archivio.non_disponibili()
    voci_comportamento = archivio.comportamento()
    conteggi_comportamento: dict[str, int] = {}
    for v in voci_comportamento:
        conteggi_comportamento[v["tipo"]] = conteggi_comportamento.get(v["tipo"], 0) + 1
    return web.json_response({
        "anagrafe_letta_il": archivio.aggiornata_il(),
        # I registri che non hanno risposto all'ultima lettura. Senza questo
        # campo una casa senza piani e un registro dei piani caduto sarebbero
        # la stessa schermata.
        "non_disponibili": non_disponibili,
        "conteggi": {chiave: len(valore) for chiave, valore in casa.items()},
        # Il sistema di riferimento della casa: unita', fuso, valuta, lingua,
        # versione di Home Assistant. Esposto qui e non solo nel nucleo perche'
        # e' lo stesso fatto: se il modello lo legge nel digesto e la pagina no,
        # sono due case diverse a seconda della porta da cui entri.
        "sistema_di_riferimento": archivio.sistema_di_riferimento(),
        "piani": gerarchia(casa, non_disponibili),
        # I NOMI delle etichette, id -> nome.
        #
        # `gerarchia()` mette sulle aree e sulle entita' i soli `label_id` --
        # e' cosi' che Home Assistant li manda -- e senza questa mappa chi
        # legge il payload puo' solo mostrare lo slug: «da_controllare» invece
        # di «Da controllare», una parola che l'utente non ha mai scritto e che
        # non cambierebbe nemmeno rinominando l'etichetta.
        #
        # E' lo stesso difetto gia' chiuso su `guarda` (`anagrafe.etichette_con_nome`),
        # che pero' risolve i nomi DENTRO la risposta perche' li' esce un
        # dettaglio. Qui esce l'albero intero: ripetere il nome su ogni entita'
        # etichettata sarebbe lo stesso fatto scritto mille volte. Esce la
        # mappa, una volta, e chi disegna la applica.
        "etichette": {e["id"]: e.get("nome") or e["id"]
                      for e in casa.get("etichette") or [] if e.get("id")},
        # Le CATEGORIE, con la stessa forma e per la stessa ragione -- ma
        # annidate per AMBITO, perche' il registro di Home Assistant e'
        # partizionato (`automation`, `script`, `scene`, `helpers`) e due
        # categorie omonime in ambiti diversi sono cose diverse. Appiattirle
        # su un id solo qui rimetterebbe in piedi l'ambiguita' che la chiave
        # `(ambito, id)` dell'archivio esiste per chiudere.
        #
        # Perche' anche qui, e non solo in `guarda`: la fetta delle categorie
        # ha cablato `anagrafe.categorie_con_nome` in `domande.py` e
        # nell'indice di `cerca`, e ha saltato QUESTA porta -- cosi' la stessa
        # categoria usciva col nome dallo strumento e con l'id grezzo dalla
        # pagina. E' il pattern che la review ha nominato («una fetta unifica
        # una regola e salta una porta»), ricomparso dentro una fetta scritta
        # apposta per non ripeterlo.
        "categorie": _mappa_categorie(casa),
        # L'esito dell'ultimo confronto fra l'albero qui sopra e cio' che Home
        # Assistant risponde su un campione di aree
        # (`server.giro_di_confronto_albero`, verdetto in
        # `anagrafe.confronta_con_home_assistant`).
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
        # parole: le frasi le costruisce `nucleo._avviso_confronto` per chi
        # legge un testo, qui serve il dato per chi disegna. `None` quando
        # nessun giro e' ancora passato -- mai `{}`, che direbbe «confrontato,
        # e non c'era niente da dire».
        "confronto": request.app.get("confronto_albero"),
        "comportamento": {
            "letto_il": archivio.comportamento_letto_il(),
            "conteggi": conteggi_comportamento,
            # Il campo che conta di piu': quante voci HIRIS conosce solo di
            # nome. Le automazioni scritte a mano non stanno nei file, e di
            # quelle sa il nome e non il corpo -- e' la misura onesta di
            # quanto sa davvero della casa. `corpo is None` e non falsy:
            # un corpo vuoto (`{}`, presente ma senza niente dentro) e' un
            # fatto diverso da un corpo assente, e non va confuso con esso.
            "senza_corpo": sum(1 for v in voci_comportamento if v["corpo"] is None),
            # Cio' che l'ultima lettura NON ha potuto concludere con
            # certezza (id duplicati, script vuoti, voci malformate) e i
            # file che non si sono letti, con la ragione. Costruiti con
            # cura da comportamento.componi()/rileggi() -- prima morivano in
            # una riga di log, invisibili a chi guarda solo /api/casa.
            "problemi": archivio.problemi_comportamento(),
            "file_non_letti": archivio.file_non_letti(),
            "voci": voci_comportamento,
        },
        "plance": {
            "lette_il": archivio.plance_lette_il(),
            # Le plance/percorsi che l'ultima lettura non e' riuscita a
            # risolvere -- stesso principio di "non_disponibili" sopra,
            # applicato alle plance invece che ai registri.
            "non_disponibili": archivio.non_disponibili_plance(),
            "voci": archivio.plance(),
        },
    })


def costruisci_nucleo(app) -> tuple[str, dict]:
    """Il nucleo composto dagli archivi vivi dell'app -- (testo, riepilogo).

    Condivisa da `handle_get_nucleo` (GET /api/nucleo, la verifica dal vivo)
    e da `handlers_chat.componi_contesto_chat` (il contesto che il modello
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

    Il resto del ragionamento -- perche' `non_disponibili` va propagato,
    perche' `MemoryStore.fetch(limit=count())` e non il default,
    perche' `stato_affidabile` richiede ENTRAMBI l'archivio e un inventario
    vivo pronto -- e' invariato da prima di questo refactor: vedi i
    commenti storici in git blame su questa funzione (era il corpo di
    `handle_get_nucleo`) per il dettaglio di ciascuna scelta.
    """
    archivio_casa = app.get("archivio_casa")
    archivio_memoria = app.get("archivio_memoria")
    cache = app.get("entity_cache")
    # Stessa difesa di `handle_list_entities`: una cache finta senza
    # `all_states` (o assente) non e' un inventario leggibile.
    if cache is not None and not hasattr(cache, "all_states"):
        cache = None

    if archivio_casa is None:
        # Difesa, non stato atteso: come in `handle_get_casa` qui sopra,
        # in produzione questo ramo non dovrebbe mai scattare (se
        # `_on_startup` fallisce, l'add-on non parte affatto). Senza
        # archivio non c'e' una casa da comporre -- `componi()` riceve una
        # casa vuota, non inventata -- ma soprattutto lo stato non puo'
        # essere dichiarato affidabile: vedi `stato_affidabile` sotto.
        casa: dict = {}
        non_disponibili: tuple[str, ...] = ()
        comportamento: list[dict] = []
        problemi_comportamento: tuple[str, ...] = ()
        file_non_letti_comportamento: dict[str, str] = {}
        sistema_di_riferimento: dict = {}
    else:
        casa = archivio_casa.leggi()
        non_disponibili = tuple(archivio_casa.non_disponibili())
        comportamento = archivio_casa.comportamento()
        # IMPORTANT ⑧: senza questi due, il PERCHE' di un'automazione
        # sconosciuta (id duplicato, file malformato) non arrivava mai al
        # modello -- `/api/casa` li espone gia', `componi()` non aveva un
        # parametro per riceverli.
        problemi_comportamento = tuple(archivio_casa.problemi_comportamento())
        file_non_letti_comportamento = archivio_casa.file_non_letti()
        # Unita', fuso, valuta, lingua: senza, il modello legge "72" senza
        # sapere in che scala e "alle 8" senza sapere in che fuso.
        sistema_di_riferimento = archivio_casa.sistema_di_riferimento()

    # CRITICAL ①: il default di `MemoryStore.fetch()` e' `limite=20`.
    # Con `conta()` (scritto apposta per dichiarare questa differenza) si
    # richiamano TUTTI i ricordi, e si lascia decidere al taglio di
    # `componi()` -- che dichiara sempre, nel nucleo stesso, quanti ne
    # restano fuori (`ricordi_esclusi`). Prima di questo fix, i ricordi
    # oltre il ventesimo sparivano PRIMA ancora di arrivare a `componi()`,
    # e il riepilogo giurava "ricordi_esclusi: 0" su una casa con 200
    # ricordi veri e solo 20 nel nucleo.
    if archivio_memoria is not None:
        ricordi = archivio_memoria.fetch(limit=archivio_memoria.count())
    else:
        ricordi = []

    # Lo specchio dello stato, dalla funzione condivisa e non riletto a mano:
    # `casa.anagrafe.specchio_vivo` e' la stessa che usano `guarda`, `cerca` e
    # la correzione dei ricordi. Prima questa porta -- che alimenta SIA
    # `GET /api/nucleo` SIA il contesto della chat, cioe' la piu' importante --
    # se lo rileggeva da sola: una normalizzazione imparata li' non sarebbe mai
    # arrivata qui, e il modello avrebbe letto nel digesto stati che non
    # coincidono con quelli che ottiene chiamando `guarda`.
    #
    # `classi_vive` e' la ragione per cui questo cablaggio conta davvero: il
    # registro delle entita' non manda `device_class`, quindi senza queste
    # nessun allagamento e nessun allarme monossido entra in «Notevole adesso»
    # (vedi `anagrafe.classe_effettiva`).
    stato: dict[str, str] = {}
    classi_vive: dict[str, str] = {}
    if cache is not None:
        try:
            stato, _nomi, _unita, classi_vive, _da_quando, _attributi = specchio_vivo(
                cache.all_states())
        except Exception:
            stato, classi_vive = {}, {}

    # I guasti che Home Assistant ha gia' diagnosticato (`repairs/list_issues`).
    #
    # DOVE VIVONO, e perche' non nell'archivio. In RAM, in `app["problemi_ha"]`,
    # accanto a `entity_cache` -- una fotografia riletta ogni pochi minuti da
    # `server.rileggi_problemi_ha`, mai una tabella. La ragione e' scritta per
    # esteso li'; in breve e' la stessa per cui `state` non entra nel sistema di
    # riferimento (vedi `casa/anagrafe.sistema_di_riferimento`): un problema e'
    # momentaneo, l'utente lo ripara con un clic in Home Assistant, e un
    # archivio che si rilegge di rado continuerebbe ad annunciarlo per ore dopo
    # che non c'e' piu'. Un falso allarme ripetuto in ogni prompt e'
    # esattamente il rumore che questa fetta esiste per non produrre.
    #
    # Si legge con `.get()` e si passa cosi' com'e': `None` (nessuno l'ha
    # ancora letto, o un'app di prova che non lo cabla) resta `None` fino a
    # `componi()`, che sa distinguerlo da «letto e vuoto». Tradurlo qui in `{}`
    # o in una lista vuota affermerebbe che la casa non ha guasti.
    problemi = app.get("problemi_ha")

    # L'esito dell'ultimo giro di verifica dell'albero (`server.giro_di_confronto_albero`).
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
    # `componi()`, che sa distinguerlo da «guardato e combacia».
    confronto = app.get("confronto_albero")

    # Affidabile SOLO se sappiamo sia quali entita' esistono (archivio della
    # casa) sia in che stato sono adesso (inventario vivo pronto). Una delle
    # due sole non basta: un archivio letto ma una cache non ancora caricata
    # produrrebbe uno stato vuoto che "Notevole adesso" leggerebbe come
    # "niente acceso" invece di "non ho potuto guardare".
    stato_affidabile = archivio_casa is not None and inventario_leggibile(cache)

    return componi(
        casa, comportamento, ricordi, stato,
        non_disponibili=non_disponibili,
        stato_affidabile=stato_affidabile,
        problemi_comportamento=problemi_comportamento,
        file_non_letti_comportamento=file_non_letti_comportamento,
        sistema_di_riferimento=sistema_di_riferimento,
        classi_vive=classi_vive,
        problemi=problemi,
        confronto=confronto,
        # L'orologio entra QUI, nell'unico compositore di produzione (chat
        # sincrona, ponte e GET /api/nucleo passano tutti di qua), perche'
        # `componi` e' pura e non legge nulla da sola. Senza questa riga il
        # parametro esisterebbe, i test di `componi` passerebbero, e il modello
        # continuerebbe a indovinare l'ora quando `prometti` gli chiede di
        # risolvere «fra un'ora» -- che e' il difetto misurato il 21/08/2026.
        adesso=time.time(),
    )


async def handle_get_nucleo(request: web.Request) -> web.Response:
    """GET /api/nucleo: il testo ESATTO che il modello ha sempre davanti, e
    il riepilogo di quanto ne resta fuori.

    Serve all'utente per capire, prima di accendere la chat, se HIRIS sta
    guardando la casa giusta -- e a noi per la verifica dal vivo, che qui
    e' l'unica prova che conta: `componi()` e' pura e coperta da
    `tests/test_nucleo.py`, ma nessun test dice se QUESTA casa, letta da
    QUESTO Home Assistant, produce un nucleo sensato.

    La composizione vera e' in `costruisci_nucleo()` qui sopra, condivisa
    con `handlers_chat.handle_chat` -- questo handler resta un guscio
    sottile che la chiama e la serializza, cosi' i due punti non possono
    raccontare due nuclei diversi della stessa casa.
    """
    testo, riepilogo = costruisci_nucleo(request.app)
    return web.json_response({"testo": testo, "riepilogo": riepilogo})
