"""La vista HTTP della memoria -- cio' che HIRIS sa, in chiaro e correggibile.

E' la decisione (5) del progetto della memoria (docs/design/2026-08-05-la-
conoscenza-di-hiris.md, §6), scritta a luglio e mai eseguita. Fino alla fetta
E5 Task 9 la pagina "Memoria" interrogava la coda di approvazione di
knowledge_store, vuota per costruzione da mesi perche' nessuno la riempiva
piu'; dalla fetta "esce il documentale" quella coda non esiste piu' affatto,
uscita con l'archivio che la conteneva. Questa vista interroga l'archivio vero
(memoria/archivio.py) ed e' l'unica: rende reale la regola (2) del contratto,
si puo' ricordare subito solo se poi si puo' guardare e correggere.

Tre cose, non di piu':

1. GET mostra la frase E cosa HIRIS ha capito -- le ancore col nome che
   l'anagrafe conosce OGGI (`Lookup.verify`), non l'identificatore nudo: e'
   il motivo per cui si ancora a un identificatore invece che a una parola.
   Se l'identificatore non esiste piu' nell'anagrafe, questa vista lo dice
   (`esiste: false`), non lo tace ne' fa finta che l'ancora non ci sia. Se
   invece l'anagrafe (o il registro che servirebbe) non e' mai stata letta,
   `esiste` resta `None`: "non ho potuto controllare" e "ho controllato e
   non c'e'" sono due fatti diversi, e confonderli fa sparire ancore vive
   ogni volta che Home Assistant non era pronto all'avvio.
2. PATCH corregge l'interpretazione, mai il testo (memoria/archivio.py,
   regola 2): usa `validate()` -- lo stesso CANCELLO che gia' protegge
   l'ingresso dal modello (interpretazione.py) -- cosi' un'ancora senza
   riscontro nell'anagrafe viene RIFIUTATA con la ragione, non accettata a
   meta' come farebbe l'ingestione normale (che scarta e prosegue). Un
   `PATCH` su un id sparito (cancellato da un'altra scheda, per esempio)
   risponde 404, non 200 `ok: true`: un ricordo che non esiste piu' non si
   "corregge" con successo.
3. Senza archivio, la risposta non afferma "zero ricordi" come se fosse un
   fatto accertato: lo dichiara (`disponibile: false`) -- stessa convenzione
   di `handlers_casa.handle_get_home_space`, non una seconda inventata qui.
"""
from __future__ import annotations

from aiohttp import web

from ..casa.anagrafe import live_mirror
from ..memoria.interpretazione import deduci_unit, validate
from ..memoria.resolver import STORE_KEY_PER_TYPE, costruisci_indice

# Gli stessi campi scalari che MemoryStore.correggi() accetta
# (memoria/archivio.py, `_CAMPI_MODIFICABILI`) piu' le due liste che quel
# metodo sostituisce per intero (`ancore`, `condizioni`). Duplicato qui
# apposta invece di importare il nome con l'underscore da un altro modulo:
# quel prefisso e' gia' il segnale "non e' superficie pubblica".
_CORRECTABLE_FIELDS = {
    "detto_da", "forza", "grandezza", "minimo", "massimo", "unita",
    "ancore", "condizioni",
}

# Quanti ricordi mostra al massimo il GET. Non e' un tetto silenzioso: la
# risposta porta sempre `totale` (vedi handle_get_memoria), cosi' chi guarda
# sa se sta vedendo tutto o solo la coda piu' recente.
_MEMORIES_SHOWN_LIMIT = 200


def _topology_loaded(home_space_store) -> bool:
    """Vero solo se l'anagrafe e' stata DAVVERO letta almeno una volta.

    `create_app()` istanzia sempre `archivio_casa`: in produzione non e'
    mai `None`. Ma un archivio appena creato (Home Assistant non ancora
    pronto all'avvio, handlers_casa.py:27-29 lo dichiara possibile) ha
    `aggiornata_il() is None` -- una casa vuota, non una casa cambiata.
    Trattarla come "letta e senza ancore" farebbe sparire ogni ancora
    valida al primo avvio, che e' esattamente il bug che questa funzione
    esiste per evitare.
    """
    return home_space_store is not None and home_space_store.updated_at() is not None


def _page_mirror(request) -> tuple[dict, dict, dict, dict, dict, dict]:
    """Lo specchio dello stato per questa pagina:
    `(stato, nomi, unita, classi, da_quando, attributi)`.

    La lettura vera sta in `casa.anagrafe.specchio_vivo`, la stessa che usa il
    dispatcher: qui c'e' solo la difesa su una cache assente o guasta, perche'
    ne' la vista ne' la correzione di un ricordo devono fallire per colpa dello
    specchio.

    Restituisce la SESTINA (era la cinquina, `attributi` e' l'ultimo arrivato)
    e non il solo pezzo che serviva prima: i nomi, le unita' e l'istante
    arrivano dalla stessa lettura, e chiamarla due volte per prenderne un
    pezzo per volta avrebbe voluto dire leggere lo specchio in due istanti
    diversi -- la stessa classe di divergenza che `specchio_vivo` esiste per
    chiudere. Questa pagina non legge `attributi` (non ne ha bisogno: mostra
    ricordi, non il dettaglio di un'entita'), ma la forma resta la stessa di
    chi lo chiama -- fondamenta 3.
    """
    cache = request.app.get("entity_cache")
    if cache is None or not hasattr(cache, "all_states"):
        return {}, {}, {}, {}, {}, {}
    try:
        return live_mirror(cache.all_states())
    except Exception:
        return {}, {}, {}, {}, {}, {}


def _unverifiable_types(home_space_store, topology_loaded: bool) -> frozenset[str]:
    """I tipi di ancora (`area`/`entita`/`dispositivo`) per cui l'anagrafe
    non puo' dare una risposta affidabile in questo momento.

    Se l'anagrafe intera non e' mai stata letta, sono TUTTI i tipi. Se e'
    stata letta ma un registro specifico non ha risposto
    (`ArchivioCasa.non_disponibili()` -- per esempio il registro delle
    aree e' caduto ma quello delle entita' no), e' solo il tipo di quel
    registro: gli altri restano verificabili normalmente.
    """
    if not topology_loaded:
        return frozenset(STORE_KEY_PER_TYPE)
    unavailable_keys = set(home_space_store.unavailable())
    return frozenset(kind for kind, key in STORE_KEY_PER_TYPE.items()
                      if key in unavailable_keys)


def _risolvi_ancora(tether: dict, lookup, unverifiable: frozenset[str]) -> dict:
    """Un'ancora arricchita col nome che l'anagrafe conosce OGGI.

    "non ho potuto controllare" (`indice is None`, l'anagrafe non e' mai
    stata letta; oppure il tipo di questa ancora e' fra i registri che non
    hanno risposto all'ultima lettura) e "ho controllato e non c'e' piu'"
    sono due fatti diversi: `esiste` resta `None` nel primo caso, mai
    `False` -- dichiarare un'assenza che non si e' potuta controllare
    sarebbe lo stesso silenzio non dichiarato che questo ramo ha gia'
    pagato quattordici volte.
    """
    if lookup is None or tether["tipo"] in unverifiable:
        return {**tether, "nome_attuale": None, "esiste": None}
    entry = lookup.verify(tether["tipo"], tether["riferimento"])
    return {**tether, "nome_attuale": entry.get("nome") if entry else None,
            "esiste": entry is not None}


async def handle_get_memories(request: web.Request) -> web.Response:
    store = request.app.get("archivio_memoria")
    if store is None:
        # Stessa convenzione di handle_get_home_space (handlers_casa.py): senza
        # archivio non sappiamo se i ricordi sono zero o se e' l'archivio a
        # mancare -- `disponibile` lo dice, `ricordi: []` resta un
        # contenitore naturale, non l'affermazione di un fatto.
        return web.json_response({"disponibile": False, "ricordi": []})

    home_space_store = request.app.get("archivio_casa")
    topology_loaded = _topology_loaded(home_space_store)
    # Coi NOMI DI RIPIEGO, come in chat. Senza, un ricordo ancorato a
    # un'entita' che nel registro non ha nome usciva su questa pagina col suo
    # entity_id crudo, mentre in chat HIRIS la chiama «Abat-jour sinistra»:
    # due nomi per la stessa cosa, e l'utente senza modo di capire se il
    # ricordo sia ancorato bene. Lo specchio si legge gia' quattro righe piu'
    # in la' per le unita': mancava solo passarne i nomi.
    live_state = _page_mirror(request)
    lookup = (costruisci_indice(home_space_store.read(), live_state[1])
              if topology_loaded else None)
    unverifiable = _unverifiable_types(home_space_store, topology_loaded)

    memories = store.fetch(limit=_MEMORIES_SHOWN_LIMIT)
    for r in memories:
        r["corretto_da_utente"] = bool(r["corretto_da_utente"])
        r["ancore"] = [_risolvi_ancora(a, lookup, unverifiable) for a in r["ancore"]]
    return web.json_response({
        "disponibile": True,
        "ricordi": memories,
        # La pagina si chiama "cio' che HIRIS sa": senza il totale, i
        # ricordi oltre `_MEMORIES_SHOWN_LIMIT` sono invisibili, e un
        # ricordo invisibile e' indistinguibile da uno cancellato -- la
        # memoria non evapora (memoria/archivio.py), ma senza dichiarare
        # il taglio sembrerebbe farlo.
        "totale": store.count(),
        "mostrati": len(memories),
    })


async def handle_patch_memory(request: web.Request) -> web.Response:
    store = request.app.get("archivio_memoria")
    if store is None:
        return web.json_response(
            {"errore": "l'archivio della memoria non e' disponibile"}, status=503)
    try:
        memory_id = int(request.match_info["id"])
    except (TypeError, ValueError):
        return web.json_response({"errore": "id non valido"}, status=400)

    # Verificato PRIMA di validare il corpo: un ricordo cancellato da
    # un'altra scheda (o mai esistito) non e' un problema del corpo della
    # richiesta, e' l'assenza del ricordo stesso -- 404, non 400.
    existing = store.get(memory_id)
    if existing is None:
        return web.json_response(
            {"errore": f"nessun ricordo con id {memory_id}"}, status=404)

    try:
        body = await request.json()
    except Exception:
        return web.json_response(
            {"errore": "corpo della richiesta non valido: atteso JSON"}, status=400)
    if not isinstance(body, dict):
        return web.json_response(
            {"errore": "corpo della richiesta non valido: atteso un oggetto"}, status=400)

    # I campi della richiesta che non sono correggibili non si applicano in
    # silenzio (il testo, per esempio, resta giustamente intatto), ma la
    # risposta lo dichiara -- vedi `ignorati` piu' sotto.
    ignored = sorted(set(body) - _CORRECTABLE_FIELDS)
    fields = {k: v for k, v in body.items() if k in _CORRECTABLE_FIELDS}
    if not fields:
        return web.json_response(
            {"errore": "nessun campo correggibile nella richiesta"}, status=400)

    home_space_store = request.app.get("archivio_casa")
    topology_loaded = _topology_loaded(home_space_store)
    # L'anagrafe puo' mancare o non essere ancora stata letta (Home
    # Assistant non ancora pronto): un indice costruito su una casa vuota
    # non verifica NESSUNA ancora, che e' il comportamento giusto in
    # fail-closed -- "un'ancora senza riscontro non si scrive" vale anche
    # quando il riscontro non si puo' nemmeno cercare. Ma la RAGIONE che
    # arriva all'utente deve dirlo com'e' (`unverifiable_types`, sotto):
    # "non esiste nell'anagrafe" e' falso quando l'anagrafe non e' mai
    # stata letta.
    live_state = _page_mirror(request)
    lookup = (costruisci_indice(home_space_store.read(), live_state[1])
              if topology_loaded else costruisci_indice({}))
    unverifiable_types = _unverifiable_types(home_space_store, topology_loaded)
    # Le unita' vive, dalla stessa fonte che usa `ricorda` in chat. Senza,
    # correggere la grandezza di un ricordo DA QUESTA PAGINA avrebbe dedotto
    # un'unita' diversa da quella dedotta dalla chat sullo stesso ricordo: lo
    # stesso fatto con due forme a seconda della porta.
    reported_units = live_state[2]

    # Un intervallo e' una coppia, non due campi indipendenti: se la
    # richiesta tocca solo `minimo` o solo `massimo`, la coerenza (minimo
    # <= massimo) si verifica contro il valore GIA' ARCHIVIATO dell'altro
    # capo, non contro `None` -- altrimenti "fra 19 e 20" corretto con
    # `{"minimo": 25}` (refuso per 15) si archivierebbe come (25.0, 20.0)
    # senza che `_validate_intervallo` lo veda mai.
    requested_minimum = fields.get("minimo") if "minimo" in fields else existing["minimo"]
    requested_maximum = fields.get("massimo") if "massimo" in fields else existing["massimo"]

    # `validate()` e' il CANCELLO gia' scritto per l'interpretazione del
    # modello (interpretazione.py): qui si riusa per la correzione umana,
    # con la STESSA regola sulle ancore. I campi assenti dalla richiesta si
    # passano "neutri" (None/[]): non generano problemi propri (vedi
    # `_validate_modality`/`_validate_intervallo`/`_validate_ancore`/
    # `_validate_conditions`), cosi' ogni problema dichiarato viene sempre da
    # un campo che l'utente ha davvero toccato in questa richiesta (le
    # eccezioni sono `minimo`/`massimo`, sopra, apposta).
    interpretation = {
        "forza": fields.get("forza"),
        "grandezza": fields.get("grandezza"),
        "minimo": requested_minimum,
        "massimo": requested_maximum,
        "ancore": fields.get("ancore") or [],
        "condizioni": fields.get("condizioni") or [],
    }
    cleaned, problems, corrections = validate(
        interpretation, lookup, unverifiable_types, reported_units)
    if problems:
        # Rifiutata con la ragione, non accettata a meta' (regola 2 di
        # MemoryStore): nessuna delle correzioni si scrive, il ricordo
        # resta esattamente com'era.
        #
        # Solo i PROBLEMI rifiutano. Una CORREZIONE -- un intervallo
        # raddrizzato -- e' un dato riparato, non scartato: rifiutarla
        # significherebbe punire l'utente per un refuso gia' sistemato, e
        # per giunta solo quando ne corregge meta': lo stesso intervallo
        # mandato intero veniva accettato. Due comportamenti opposti per la
        # stessa situazione, a seconda di come arrivava.
        return web.json_response(
            {"errore": "; ".join(problems), "problemi": problems}, status=400)

    updates: dict = {}
    if "detto_da" in fields:
        updates["detto_da"] = fields["detto_da"]
    if "forza" in fields:
        updates["forza"] = cleaned["forza"]
    if "grandezza" in fields:
        updates["grandezza"] = cleaned["grandezza"]
    if "minimo" in fields or "massimo" in fields:
        # Si scrivono ENTRAMBI i capi, anche quando la richiesta ne
        # toccava uno solo: e' la coppia (gia' raddrizzata/dichiarata da
        # `_validate_intervallo` se serviva) che va archiviata, non il campo
        # isolato -- altrimenti un raddrizzamento sarebbe scritto a meta'.
        updates["minimo"] = cleaned["minimo"]
        updates["massimo"] = cleaned["massimo"]
    if "unita" in fields:
        # `validate()` non prende `unita` in input: la deduce sempre da ancora
        # + grandezza (interpretazione.deduci_unit), perche' quel percorso
        # e' per il modello ("l'unita' non si chiede, si deduce"). Qui invece
        # e' una correzione umana diretta a un campo che MemoryStore.
        # correggi() gia' accetta -- passa cosi' com'e', senza dedurla.
        updates["unita"] = fields["unita"]
    elif "grandezza" in fields or "ancore" in fields:
        # L'utente non ha toccato `unita` direttamente, ma ha corretto cio'
        # da cui si deduce (grandezza o ancore): senza rideduzione, resta
        # quella vecchia -- "umidita' 19-20 °C" dopo aver corretto la
        # grandezza da temperatura a umidita'. Si deduce dal valore NUOVO
        # se toccato in questa richiesta, altrimenti da quello archiviato.
        tethers_for_deduction = cleaned["ancore"] if "ancore" in fields else existing["ancore"]
        quantity_for_deduction = cleaned["grandezza"] if "grandezza" in fields \
            else existing["grandezza"]
        updates["unita"] = deduci_unit(
            tethers_for_deduction, quantity_for_deduction, lookup, reported_units)
    if "ancore" in fields:
        updates["ancore"] = cleaned["ancore"]
    if "condizioni" in fields:
        updates["condizioni"] = cleaned["condizioni"]

    found = store.correggi(memory_id, **updates)
    if not found:
        # Sparito fra il controllo di sopra e la scrittura (un'altra
        # scheda l'ha cancellato nel frattempo): stesso 404, stessa
        # ragione onesta -- non e' un "ok" travestito.
        return web.json_response(
            {"errore": f"nessun ricordo con id {memory_id}"}, status=404)

    answer: dict = {"ok": True}
    if ignored:
        answer["ignorati"] = ignored
    if corrections:
        answer["correzioni"] = corrections
    return web.json_response(answer)


async def handle_delete_memory(request: web.Request) -> web.Response:
    store = request.app.get("archivio_memoria")
    if store is None:
        return web.json_response(
            {"errore": "l'archivio della memoria non e' disponibile"}, status=503)
    try:
        memory_id = int(request.match_info["id"])
    except (TypeError, ValueError):
        return web.json_response({"errore": "id non valido"}, status=400)
    store.dimentica(memory_id)
    return web.Response(status=204)
