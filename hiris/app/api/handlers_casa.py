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

from aiohttp import web

from ..casa.anagrafe import gerarchia
from ..casa.nucleo import componi
from ..proxy.entity_cache import inventario_leggibile


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
            # Stesso principio di "non_disponibili" qui sopra, applicato al
            # comportamento: `senza_corpo: 0` affermerebbe "conosco tutto",
            # e senza archivio non lo sappiamo -- resta `None`. `conteggi` e
            # `voci`, come `conteggi`/`piani` sopra, sono contenitori naturali
            # e restano vuoti. `problemi`/`file_non_letti` restano `None` per
            # lo stesso motivo di `senza_corpo`: un elenco vuoto affermerebbe
            # "nessun problema", e senza archivio non lo sappiamo.
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
        "piani": gerarchia(casa, non_disponibili),
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


async def handle_get_nucleo(request: web.Request) -> web.Response:
    """GET /api/nucleo: il testo ESATTO che il modello ha sempre davanti, e
    il riepilogo di quanto ne resta fuori.

    Serve all'utente per capire, prima di accendere la chat, se HIRIS sta
    guardando la casa giusta -- e a noi per la verifica dal vivo, che qui
    e' l'unica prova che conta: `componi()` e' pura e coperta da
    `tests/test_nucleo.py`, ma nessun test dice se QUESTA casa, letta da
    QUESTO Home Assistant, produce un nucleo sensato.

    Questo ramo ha sbagliato tre volte a propagare `non_disponibili` (i
    registri che non hanno risposto all'ultima lettura): un modulo lo
    riceveva e non lo passava oltre, o non lo riceveva affatto, e il
    risultato era sempre lo stesso -- una casa letta a meta' raccontata
    come una casa piu' piccola. Qui si prende da `archivio.non_disponibili()`,
    esattamente come fa `handle_get_casa` qui sopra per `/api/casa`, e si
    passa a `componi()` cosi' com'e'.

    Lo stato vivo (chi e' acceso adesso) NON viene ricalcolato con una
    strada propria: si legge dalla stessa `entity_cache` che il resto del
    server usa (vedi `handlers_entities.handle_list_entities`,
    `server._osserva_la_casa`), nella stessa forma (`{"id": ..., "state":
    ...}`, non `entity_id`). `inventario_leggibile()` -- la bandiera che
    dispatcher/ha_tools/briefing/handlers_entities gia' usano per non
    spacciare "non ho guardato" per "va tutto bene" -- decide se quello
    stato e' abbastanza fresco da essere dichiarato affidabile a
    `componi()`. Senza archivio della casa (quali entita' esistono) O senza
    un inventario vivo pronto (in che stato sono adesso), il nucleo non
    afferma la quiete: dichiara esplicitamente `stato_affidabile=False`, e
    "Notevole adesso" dira' "non ho potuto guardare" invece di "niente di
    notevole" -- la stessa distinzione che `componi()` esiste per fare
    (vedi `_stato_inaffidabile` in `casa/nucleo.py`).
    """
    archivio_casa = request.app.get("archivio_casa")
    archivio_memoria = request.app.get("archivio_memoria")
    cache = request.app.get("entity_cache")
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
    else:
        casa = archivio_casa.leggi()
        non_disponibili = tuple(archivio_casa.non_disponibili())
        comportamento = archivio_casa.comportamento()

    ricordi = archivio_memoria.richiama() if archivio_memoria is not None else []

    # `stato` nella forma che `componi()` vuole: entity_id -> valore grezzo.
    # `entity_cache.all_states()` usa la chiave "id", non "entity_id" (vedi
    # `brain.portrait.notable_state`, che documenta la stessa forma).
    stato: dict[str, str] = {}
    if cache is not None:
        for e in cache.all_states():
            entity_id = e.get("id") if isinstance(e, dict) else None
            if entity_id:
                stato[entity_id] = e.get("state")

    # Affidabile SOLO se sappiamo sia quali entita' esistono (archivio della
    # casa) sia in che stato sono adesso (inventario vivo pronto). Una delle
    # due sole non basta: un archivio letto ma una cache non ancora caricata
    # produrrebbe uno stato vuoto che "Notevole adesso" leggerebbe come
    # "niente acceso" invece di "non ho potuto guardare".
    stato_affidabile = archivio_casa is not None and inventario_leggibile(cache)

    testo, riepilogo = componi(
        casa, comportamento, ricordi, stato,
        non_disponibili=non_disponibili,
        stato_affidabile=stato_affidabile,
    )
    return web.json_response({"testo": testo, "riepilogo": riepilogo})
