"""L'anagrafe: i registri grezzi di Home Assistant diventano LA CASA.

Quattro livelli di gerarchia — piano → area → dispositivo → entita' — dove
HIRIS ne conosceva uno solo. Il significato non si deduce e non si compra: e'
gia' dichiarato dall'utente in Home Assistant.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def rebuild(client, store) -> dict:
    """Rilegge tutti i registri da HA e sostituisce l'anagrafe.

    Restituisce `{"conteggi": {...}, "non_disponibili": [...]}`.

    I conteggi servono a chi guarda: se domani sono la meta' di ieri, e'
    successo qualcosa. `non_disponibili` serve a distinguere una casa senza
    piani da un registro dei piani caduto — producono la stessa lista vuota, e
    senza questo elenco l'anagrafe costruirebbe sul silenzio credendolo un
    dato. Va REGISTRATO, non ingoiato.

    Se TUTTI i registri sono in `non_disponibili` (Home Assistant
    irraggiungibile: riavvio, blip di rete, il ritardo dell'antirimbalzo
    scaduto a HA spento), non si sostituisce niente. `archivio.replace`
    e' incondizionato: chiamato lo stesso, rimpiazzerebbe la casa buona di
    ieri con dieci liste vuote, e la casa resterebbe vuota finche' qualcuno
    non ritocca un registro — anche per settimane, se il ② (rilettura ad ogni
    riconnessione) non basta a farla ritentare subito. Una replica vecchia e
    dichiarata stantia e' meglio di una vuota spacciata per fresca.
    """
    registries, unavailable = await client.read_registries()
    frame, frame_loaded = await _read_reference_frame(client)
    if not frame_loaded:
        unavailable = list(unavailable) + ["sistema_di_riferimento"]
    counts = {key: len(value) for key, value in registries.items()}
    # "categorie:script" fallisce per un solo ambito, non per l'intero
    # registro "categorie": si confronta il nome del registro (prima dei
    # due punti), non la stringa intera.
    failed_registries = {name.split(":", 1)[0] for name in unavailable}
    if unavailable and failed_registries >= set(registries):
        logger.warning(
            "lettura dei registri fallita per intero (%s): la casa precedente resta "
            "quella di prima, non sostituita da un vuoto", unavailable)
    else:
        store.replace(registries, unavailable, reference_frame=frame)
        if unavailable:
            logger.warning("anagrafe ricostruita, ma questi registri non hanno risposto: %s",
                           unavailable)
        logger.info("anagrafe ricostruita: %s", counts)
    return {"conteggi": counts, "non_disponibili": unavailable}


# I campi di `get_config` che HIRIS tiene, e sotto quale nome. La chiave a
# sinistra e' quella di Home Assistant (`Config.as_dict()` in
# `homeassistant/core_config.py`), quella a destra e' il nome italiano con cui
# vive nell'archivio: l'anagrafe parla la lingua di HIRIS ovunque -- `nome`,
# `alias`, `etichette` -- e un dizionario meta' inglese sarebbe l'unico posto
# in cui non lo fa.
_REFERENCE_FRAME_FIELDS = {
    "time_zone": "fuso",
    "currency": "valuta",
    "language": "lingua",
    "country": "paese",
    "location_name": "nome",
    "version": "versione_ha",
    "unit_system": "unita",
}


def reference_frame(config) -> dict:
    """Il sistema di riferimento della casa, distillato dalla config di HA.

    Un valore senza il suo sistema di riferimento non e' un dato, e' un
    numero: "72" non significa niente finche' non si sa se sono gradi Celsius
    o Fahrenheit, e "domani alle 8" non significa niente senza il fuso. Questo
    e' il pezzo che mancava perche' cio' che HIRIS legge sia INTERPRETABILE da
    solo (fondamenta: atomicita').

    ATTENZIONE, e vale per chiunque tocchi questo codice: `unita` dice come
    ragiona la CASA, non come si legge una singola entita'. Home Assistant
    converte al momento in cui l'entita' entra, non alla lettura: una casa
    metrica puo' contenere un sensore in Fahrenheit, e un sensore senza unita'
    (un indice, un contatore) non e' "gradi" solo perche' la casa e' metrica.
    Usare questo come ripiego per un'entita' senza unita' significa scrivere
    un'unita' sotto un numero che non ce l'ha. C'e' una prova apposta che
    fallisce se qualcuno lo fa (`test_casa_riferimento.py`).

    Cosa NON entra, e perche':
    - `components`: e' l'elenco delle integrazioni, che l'anagrafe ha gia'
      nella propria tabella `integrazioni` (fondamenta: nessun doppione);
    - `latitude`/`longitude`: non servono a nessuna domanda di oggi, e un dato
      del genere non si tiene "per ogni evenienza";
    - `state`: e' momentaneo. In un archivio che si rilegge di rado
      mentirebbe poche ore dopo, ed e' peggio che non saperlo. Chi vuole
      sapere se HA e' su lo chiede a HA, non a una fotografia di ieri.
    """
    if not isinstance(config, dict):
        return {}
    return {our: config[their]
            for their, our in _REFERENCE_FRAME_FIELDS.items()
            if config.get(their)}


async def _read_reference_frame(client) -> tuple[dict, bool]:
    """`(sistema, letto)`. Separati perche' sono due domande diverse: un
    riferimento vuoto perche' HA non ha risposto e uno vuoto perche' HA non
    ha niente da dire producono lo stesso dizionario, e chi ci costruisce
    sopra deve poterli distinguere -- lo stesso motivo per cui esiste
    `non_disponibili`.

    Un client vecchio senza `get_config` (o un finto di prova che non lo
    dichiara) non deve far fallire l'intera ricostruzione dell'anagrafe: la
    casa senza riferimento e' incompleta, la casa non ricostruita e' vuota.
    """
    reader = getattr(client, "get_config", None)
    if reader is None:
        return {}, False
    try:
        frame = reference_frame(await reader())
    except Exception as e:  # rete caduta, comando rifiutato, HA a meta' avvio
        logger.warning("sistema di riferimento della casa non letto: %s", e)
        return {}, False
    return frame, bool(frame)


# Id espliciti per le pseudo-aree e i piani-contenitore: mai None, cosi' un
# consumatore che indicizzi per id (naturale, su un albero con id) non fa
# sparire in silenzio due contenitori diversi che per caso condividevano la
# stessa chiave.
_ID_WITHOUT_AREA = "__senza_area__"
_ID_UNLOADED_AREA = "__aree_non_lette__"
_ID_UNKNOWN_AREA = "__area_sconosciuta__"
_ID_UNLOADED_DEVICE = "__dispositivi_non_letti__"
_ID_WITHOUT_FLOOR = "__senza_piano__"
_ID_UNLOADED_FLOOR = "__piani_non_letti__"
_ID_OUTSIDE_AREAS = "__fuori_dalle_aree__"

# Le pseudo-aree che una vista di dettaglio (`domande.guarda("area", ...)`)
# sa raggiungere per ID -- MAI per nome: "Senza area" e' un nome che due case
# diverse possono condividere (e' generico, non dichiarato dall'utente), e
# `cerca()`/l'indice (resolver.py) non lo indicizzano perche' non
# esistono nell'anagrafe grezza di Home Assistant, solo nell'albero che
# `hierarchy()` costruisce. Chi mostra il nome da solo (IMPORTANT ⑦) mostra
# un vicolo cieco: il nome non porta a nessun `guarda()` che funzioni.
_ID_PSEUDO_AREA = frozenset(
    {_ID_WITHOUT_AREA, _ID_UNLOADED_AREA, _ID_UNKNOWN_AREA, _ID_UNLOADED_DEVICE})


def is_pseudo_area(area_id: str) -> bool:
    """Vero se `area_id` e' una pseudo-area generata da `hierarchy()` (non
    un'area vera di Home Assistant): chi la mostra per nome deve mostrare
    anche l'id, l'unica chiave con cui `guarda('area', ...)` la ritrova
    davvero (IMPORTANT ⑦)."""
    return area_id in _ID_PSEUDO_AREA


def live_mirror(rows) -> tuple[dict[str, str], dict[str, str], dict[str, str],
                               dict[str, str], dict[str, str], dict[str, dict]]:
    """Lo specchio dello stato in sei dizionari:
    `(stato, nomi, unita, classi, da_quando, attributi)`.

    `righe` e' cio' che `entity_cache.all_states()` restituisce: dizionari
    nella forma di `_to_minimal` -- chiave `id` (non `entity_id`), piu' `state`,
    `name` (il `friendly_name`), `unit`, `last_changed` e, quando il dominio ne
    ha, `attributes`.

    Una passata sola per tutti i dizionari, e in un posto solo per tutti i
    chiamanti. Prima lo specchio si leggeva in `casa/strumenti.py` e basta: chi
    stava altrove (la correzione di un ricordo dalla pagina, per esempio) o
    rileggeva la cache per conto suo, o faceva a meno di cio' che ci sta
    dentro. Nel secondo caso la stessa domanda dava due risposte diverse a
    seconda della porta -- l'unita' dedotta in chat e non dedotta dalla pagina.

    Nomi, unita', classi e istanti vuoti si saltano: una stringa vuota non e'
    un nome e non e' un'unita', e' l'assenza dell'una e dell'altra.

    `classi` (entity_id -> `device_class`) e' arrivata per ultima ed e' la piu'
    importante: il registro delle entita' NON manda la classe (vedi
    `actual_class`), quindi finche' nessuno leggeva questa nessun sensore
    binario ha mai avuto una classe in tutto il prodotto.

    `da_quando` (entity_id -> `last_changed`) e' l'ultima arrivata: il campo
    che Home Assistant manda a ogni cambio di stato e che la proiezione della
    cache (`entity_cache._to_minimal`) scartava. HIRIS sapeva che in camera ci
    sono 22,4 gradi e non sapeva da quando -- non poteva nemmeno dire «e'
    fermo da tre ore». Costa un campo e zero chiamate a Home Assistant.

    `attributi` (entity_id -> il dizionario `attributes` di `_to_minimal`,
    quando non e' vuoto) e' il difetto misurato dal proprietario, fetta
    "attributi al modello" (2026-08-25): `entity_cache._to_minimal` raccoglie
    gia' `hvac_action`, `current_temperature`, la luminosita' di una luce, la
    posizione di una tapparella -- `_DOMAIN_ATTRS` in `proxy/entity_cache.py`
    -- e QUESTA funzione, l'unico punto da cui passano `guarda`, `cerca` e il
    nucleo, li buttava tutti tenendo solo `state`. Un termostato IMPOSTATO su
    riscaldamento e FERMO (`hvac_mode: heat`, `hvac_action: idle`) usciva da
    `guarda` come `stato: "heat"` e basta -- indistinguibile da uno che sta
    scaldando davvero. Il modello ha risposto con quell'unica informazione,
    ed era vera solo a meta'.
    """
    state: dict[str, str] = {}
    names: dict[str, str] = {}
    unit: dict[str, str] = {}
    classes: dict[str, str] = {}
    since_when: dict[str, str] = {}
    attributes: dict[str, dict] = {}
    for e in rows:
        if not isinstance(e, dict):
            continue
        entity_id = e.get("id")
        if not entity_id:
            continue
        state[entity_id] = e.get("state")
        name = e.get("name")
        if isinstance(name, str) and name.strip():
            names[entity_id] = name.strip()
        measurement = e.get("unit")
        if isinstance(measurement, str) and measurement.strip():
            unit[entity_id] = measurement.strip()
        device_class = e.get("device_class")
        if isinstance(device_class, str) and device_class.strip():
            classes[entity_id] = device_class.strip()
        instant = e.get("last_changed")
        if isinstance(instant, str) and instant.strip():
            since_when[entity_id] = instant.strip()
        extra = e.get("attributes")
        if isinstance(extra, dict) and extra:
            attributes[entity_id] = extra
    return state, names, unit, classes, since_when, attributes


def name_with_id(name: str, id_: str | None) -> str:
    """Nome con l'id accanto tra parentesi, quando l'id dice qualcosa che il
    nome da solo non dice (R1/R2, fetta "i riferimenti", incidente
    2026-08-20).

    LA regola unica dietro ogni riferimento della casa che deve portare
    entrambi -- il nome protagonista, l'id accessorio: nata in `nucleo.py`
    per l'albero (aree, piani, automazioni/script -- le pseudo-aree la
    applicavano gia' da sole), qui perche' `labels_with_name` sotto la
    riusa per lo stesso motivo (T8, R2) -- **un posto solo**, non una
    seconda formattazione che domani diverge dalla prima (fondamenta:
    stessa forma per lo stesso fatto).

    Tace in due casi: id assente, e id identico al nome (un riferimento
    penzolante, dove l'unica cosa che si conosce di lui e' il suo id) -- in
    entrambi una parentesi in piu' sarebbe rumore, non informazione.
    """
    if not id_ or id_ == name:
        return name
    return f"{name} (id: {id_})"


def label_names(home_space: dict) -> dict[str, str]:
    """label_id -> nome, dal registro delle etichette dell'anagrafe.

    Home Assistant mette nei registri di aree, dispositivi ed entita' i soli
    **label_id** (`labels: set[str]`, verificato in
    `helpers/entity_registry.py`), e tiene i nomi in un registro a parte
    (`helpers/label_registry.py`: `label_id` + `name`). L'anagrafe li salva
    entrambi -- la tabella `etichette` -- ma finche' nessuno li unisce, un
    `label_id` che esce da una porta e' un identificativo senza il suo nome:
    ATOMICITA'.

    Non e' una pignoleria di forma. Un `label_id` e' uno slug: «Da controllare»
    diventa `da_controllare`, e chi lo riceve legge una stringa che l'utente
    non ha mai scritto. Peggio: lo slug non cambia MAI piu' -- rinominare
    l'etichetta in Home Assistant lascia l'id com'era, quindi HIRIS
    continuerebbe a dire il vecchio nome per sempre.

    Qui, e non in `domande.py`, perche' la stessa unione serve anche
    all'indice di `cerca` (`memoria/resolver.py`): scritta due volte
    sarebbe una ricerca che trova per un nome e una risposta che ne mostra un
    altro.
    """
    return {e["id"]: e.get("nome") or e["id"]
            for e in home_space.get("etichette") or [] if e.get("id")}


def _label_id_and_name(entry: dict, names: dict[str, str]) -> list[tuple[str, str]]:
    """(label_id, nome) per ogni etichetta valida della voce -- la base
    condivisa da `labels_with_name` (ricerca: nomi PURI, mai l'id nel
    testo che si indicizza) ed `labels_with_id` (display: nome+id
    accessorio, T8). Un id che il registro non conosce resta com'e' invece
    di sparire: e' un riferimento penzolante (o un registro delle etichette
    non letto), e «questa cosa ha un'etichetta che non so nominare» e' piu'
    vero di «questa cosa non ha etichette». Stessa scelta di `hierarchy()`
    con le aree sconosciute.
    """
    return [(str(e), names.get(str(e), str(e))) for e in (entry.get("etichette") or [])
            if str(e).strip()]


def labels_with_name(entry: dict, names: dict[str, str]) -> list[str]:
    """Le etichette di una voce dell'anagrafe, coi nomi al posto degli id.

    SOLO nomi, MAI l'id nel testo: alimenta anche l'indice di `cerca`
    (`memoria/resolver.py::costruisci_indice`), che indicizza questi
    stessi nomi come TERMINI di ricerca -- un `label_id` mescolato nel
    testo renderebbe "da controllare" irriconoscibile, perche' il termine
    indicizzato sarebbe "da controllare (id: da_controllare)" e nessuno lo
    scrive cosi'. Chi vuole l'id accanto per un display usa
    `labels_with_id` sotto: due usi diversi, due funzioni -- non una che
    prova a servirli entrambi.
    """
    return [name for _, name in _label_id_and_name(entry, names)]


def labels_with_id(entry: dict, names: dict[str, str]) -> list[str]:
    """Come `labels_with_name`, ma col `label_id` accanto come dato
    ACCESSORIO -- `Nome (id: X)`, la stessa forma di `name_with_id` che
    l'albero del nucleo usa gia' per aree/piani/automazioni (T8, R2:
    decisione del proprietario 2026-08-20,
    docs/design/2026-08-20-i-riferimenti.md §2).

    Fino a questa fetta il `label_id` non usciva da NESSUNA porta:
    `esegui(bersaglio.etichette=[...])` lo pretende, e nessuna sequenza di
    chiamate lo produceva mai -- il vicolo cieco piu' radicale della
    famiglia (R2). Per USARE questa funzione al posto di
    `labels_with_name`: solo dove il testo e' per un umano/modello da
    LEGGERE (`guarda`), mai dove diventa un termine da CERCARE -- vedi il
    docstring di `labels_with_name`.
    """
    return [name_with_id(name, id_) for id_, name in _label_id_and_name(entry, names)]


def category_names(home_space: dict) -> dict[tuple[str, str], str]:
    """(ambito, category_id) -> nome, dal registro delle categorie.

    Le categorie sono la SECONDA tassonomia scritta a mano dall'utente in Home
    Assistant, accanto alle etichette: «Luci esterne», «Vacanza», «Da rifare».
    E vale identica la trappola gia' pagata con le etichette: nei registri HA
    manda gli **identificativi** (`categories: dict[str, str]` su ogni voce
    delle entita', verificato in `helpers/entity_registry.py`), e i nomi
    stanno in un registro a parte (`config/category_registry/list` risponde
    con `category_id` + `name` + `icon`, verificato in
    `components/config/category_registry.py`). Un id che esce senza il suo
    nome e' un frammento: ATOMICITA'.

    La chiave e' la COPPIA, non il solo id. Il registro delle categorie di
    Home Assistant e' partizionato per ambito (`automation`, `script`,
    `scene`, `helpers`: e' il parametro obbligatorio `scope` del comando) e le
    righe che torna NON lo riportano -- lo aggiunge `ha_client.read_registries`
    marcando ogni riga col proprio. Due categorie omonime in ambiti diversi
    sono due cose diverse, e indicizzarle per il solo id lascerebbe che l'una
    rispondesse per l'altra.

    Qui, e non in `domande.py`, per la stessa ragione di
    `label_names`: la stessa unione serve all'indice di `cerca`
    (`memoria/resolver.py`), e scritta due volte sarebbe una ricerca che
    trova per un nome e una risposta che ne mostra un altro.
    """
    names: dict[tuple[str, str], str] = {}
    for c in home_space.get("categorie") or []:
        identifier = str(c.get("id") or "").strip()
        if not identifier:
            continue
        scope = str(c.get("ambito") or "").strip()
        names[(scope, identifier)] = str(c.get("nome") or "").strip() or identifier
    return names


def categories_with_name(entry: dict, names: dict[tuple[str, str], str]) -> dict[str, str]:
    """Le categorie di una voce dell'anagrafe: `{ambito: nome}`.

    Resta un dizionario e non diventa una lista di nomi -- come sono invece le
    etichette -- perche' l'ambito e' parte del significato: «Luci esterne»
    fra le automazioni e «Luci esterne» fra le scene sono due tassonomie
    diverse, e chi riceve il solo nome non puo' piu' distinguerle.

    Un id che il registro non conosce resta com'e' invece di sparire: e' un
    riferimento penzolante (o un registro delle categorie non letto -- ne
    esistono quattro, uno per ambito, e possono cadere separatamente), e
    «questa cosa sta in una categoria che non so nominare» e' piu' vero di
    «questa cosa non ha categoria». Stessa scelta di `labels_with_name`.
    """
    assigned = entry.get("categorie")
    if not isinstance(assigned, dict):
        return {}
    resolved: dict[str, str] = {}
    for scope, identifier in assigned.items():
        scope = str(scope).strip()
        identifier = str(identifier).strip()
        if not scope or not identifier:
            continue
        resolved[scope] = names.get((scope, identifier), identifier)
    return resolved


# Le tre severita' di un problema diagnosticato da Home Assistant, dalla piu'
# grave. I valori sono quelli veri di `IssueSeverity`
# (`helpers/issue_registry.py`), verificati.
#
# Stanno QUI e non in `proxy/ha_client.py`, dove sono nate: le legge anche il
# nucleo per ordinare cio' che dice, e importare il client di rete dentro il
# digesto per tre parole significava trascinare httpx dentro un modulo che si
# dichiara PURO. Questa e' gia' la casa degli altri vocabolari di Home
# Assistant (i significati delle classi, le traduzioni degli stati), ed e' una
# foglia: la puo' importare chiunque.
PROBLEM_SEVERITY = ("critical", "error", "warning")


# --- il vocabolario degli stati -------------------------------------------
#
# Sta QUI e non in `nucleo.py`, dov'era nato: il significato di uno stato e' un
# fatto sulla casa, non una proprieta' del digesto. Finche' e' stato li' dentro,
# il digesto traduceva «bagnato» e `guarda` -- l'altra porta, quella che il
# modello usa quando la domanda e' precisa -- rispondeva «on». La stessa
# perdita d'acqua aveva la forma di una lampadina accesa a seconda di chi la
# chiedeva.

_STATE_TRANSLATION = {
    "on": "acceso", "off": "spento", "open": "aperta", "closed": "chiusa",
    "home": "in casa", "not_home": "fuori casa", "unlocked": "sbloccata",
    "locked": "bloccata", "playing": "in riproduzione", "paused": "in pausa",
    "unavailable": "non disponibile", "detected": "rilevato",
    "problem": "in problema", "triggered": "in allarme",
}

# COSA SIGNIFICANO I VALORI, per classe.
#
# "on"/"off" non bastano per una porta o una finestra: "acceso"/"spento"
# affermerebbe un'alimentazione che l'oggetto non ha. Il principio era gia'
# scritto qui, e copriva CINQUE classi (`_CLASSI_APERTURA`) sul totale che
# Home Assistant documenta (le stesse di `_CLASS_MEANING`, qui sotto):
# per questo un allagamento si leggeva «1 sensore binario (acceso)»,
# indistinguibile da una lampadina.
#
# I significati NON sono inventati: sono quelli dichiarati in
# developers.home-assistant.io/docs/core/entity/binary-sensor/, verificati il
# 16/08/2026. Dove HA dice «on means wet», qui c'e' «bagnato».
_CLASS_MEANING: dict[str, tuple[str, str]] = {
    # allarmi
    "moisture": ("bagnato", "asciutto"),
    "smoke": ("fumo rilevato", "nessun fumo"),
    "gas": ("gas rilevato", "nessun gas"),
    # ATTENZIONE: il valore-stringa e' `carbon_monoxide`, NON `co`. E' l'unica
    # classe di `_CLASS_MEANING` in cui la stringa non e' il nome della
    # costante in minuscolo (`BinarySensorDeviceClass.CO = "carbon_monoxide"`, verificato
    # su homeassistant/components/binary_sensor/__init__.py). Scritto `co`,
    # un allarme monossido non entra nel digesto e non viene tradotto: la
    # classe piu' critica dell'elenco, muta.
    "carbon_monoxide": ("monossido rilevato", "nessun monossido"),
    "safety": ("non sicuro", "sicuro"),
    "tamper": ("manomissione rilevata", "nessuna manomissione"),
    "problem": ("problema rilevato", "nessun problema"),
    "heat": ("caldo", "normale"),
    "cold": ("freddo", "normale"),
    # aperture (erano `_CLASSI_APERTURA`: assorbite qui, non affiancate)
    "door": ("aperto", "chiuso"),
    "window": ("aperto", "chiuso"),
    "garage_door": ("aperto", "chiuso"),
    "opening": ("aperto", "chiuso"),
    "damper": ("aperto", "chiuso"),
    "lock": ("sbloccato", "bloccato"),
    # presenza e movimento
    "motion": ("movimento rilevato", "nessun movimento"),
    "occupancy": ("occupato", "libero"),
    "presence": ("in casa", "fuori"),
    "moving": ("in movimento", "fermo"),
    "vibration": ("vibrazione rilevata", "nessuna vibrazione"),
    # alimentazione e collegamento
    "plug": ("collegato", "scollegato"),
    "power": ("alimentato", "non alimentato"),
    "connectivity": ("connesso", "disconnesso"),
    "battery": ("carica bassa", "carica normale"),
    "battery_charging": ("in carica", "non in carica"),
    "running": ("in funzione", "fermo"),
    # altro
    "light": ("luce rilevata", "nessuna luce"),
    "sound": ("suono rilevato", "nessun suono"),
    "update": ("aggiornamento disponibile", "aggiornato"),
}


# Un termostato ha DUE fatti, non uno: `hvac_mode` (il valore di `stato`)
# dice a cosa e' IMPOSTATO, `hvac_action` dice se sta FUNZIONANDO adesso.
# `heat` da solo confonde i due -- e' esattamente il difetto misurato dal
# proprietario (2026-08-25): due termostati impostati su riscaldamento e
# FERMI (`hvac_action: idle`, target 17, temperatura reale 25) sono usciti
# da `guarda` come «heat», e il modello ha letto «in modalita'
# riscaldamento» come se stessero scaldando davvero.
#
# I valori sono quelli veri di `ClimateEntityFeature`/`HVACMode`
# (`components/climate/const.py`), verificati: il dominio non ha una
# `device_class` propria (a differenza di sensori e binary_sensor), quindi
# questa tabella si applica per DOMINIO, non per classe.
_READABLE_HVAC_MODE = {
    "off": "spento", "heat": "riscaldamento", "cool": "raffrescamento",
    "heat_cool": "riscaldamento/raffrescamento", "auto": "automatica",
    "dry": "deumidificazione", "fan_only": "sola ventilazione",
}

# `hvac_action`: cosa sta succedendo ADESSO, non cosa e' impostato. Un
# termostato senza questo attributo (integrazioni che non lo mandano) resta
# onesto per omissione -- vedi `_readable_climate_state` sotto, che senza
# azione nota dice solo l'impostazione e non inventa un funzionamento.
_READABLE_HVAC_ACTION = {
    "heating": "sta scaldando", "cooling": "sta raffrescando",
    "drying": "sta deumidificando", "fan": "sta ventilando",
    "preheating": "sta preriscaldando", "idle": "fermo", "off": "spento",
}


def _readable_climate_state(value, hvac_action: str | None) -> str:
    """Lo stato di un termostato in parole, onesto sulla differenza fra
    impostazione e funzionamento (vedi `_READABLE_HVAC_MODE`).

    Senza `hvac_action` (integrazione che non lo manda, o valore fuori
    vocabolario) si dichiara solo l'impostazione -- «impostato su
    riscaldamento» -- perche' e' l'unica cosa che si sa davvero: MEGLIO
    un'informazione parziale dichiarata come tale che una frase che
    suggerisce un funzionamento che nessuno ha confermato.
    """
    v = str(value).lower()
    mode = _READABLE_HVAC_MODE.get(v)
    if mode is None:
        return str(value)
    if v == "off":
        return mode
    action = _READABLE_HVAC_ACTION.get(str(hvac_action).lower()) if hvac_action else None
    if action:
        return f"impostato su {mode}, {action}"
    return f"impostato su {mode}"


def translate_state(value, device_class: str | None = None, domain: str | None = None,
                    hvac_action: str | None = None) -> str:
    """Il valore in parole. La CLASSE decide: `on` di un `moisture` e' «bagnato»,
    `on` di un `door` e' «aperto», `on` di una luce e' «acceso». Vedi
    `_CLASS_MEANING`, che porta i significati dichiarati da Home Assistant.

    `dominio` e `hvac_action` sono opzionali e servono a UN solo dominio,
    `climate`: senza di loro un termostato traduce come qualunque altro stato
    sconosciuto (la stringa grezza, `heat`), che e' esattamente il difetto che
    questa firma esiste per chiudere -- vedi `_readable_climate_state`.
    Chi non li passa (il nucleo, per scelta: e' testo pagato a ogni turno, e
    il climate non entra mai in "Notevole adesso") si comporta come prima."""
    if domain == "climate":
        return _readable_climate_state(value, hvac_action)
    v = str(value).lower()
    meaning = _CLASS_MEANING.get(device_class or "")
    if meaning:
        if v == "on":
            return meaning[0]
        if v == "off":
            return meaning[1]
    return _STATE_TRANSLATION.get(v, str(value))


def domain_of(entity_id) -> str:
    """Il dominio di un `entity_id`: `light.cucina` -> `light`.

    Lo DICHIARA Home Assistant nell'id stesso -- non e' un elenco nostro -- e
    per questo la lettura e' banale. Il punto non e' la logica: e' che era
    scritta SEI volte (`nucleo`, `domande`, `entity_cache`, `azione/verifica`,
    `casa/comportamento` due volte, `api/handlers_entities`) e due copie non
    erano d'accordo. Su un id senza punto -- una riga di registro corrotta, un
    id sintetico di un'integrazione mal formata -- una restituiva l'id intero e
    l'altra la stringa vuota, cosi' il nucleo stampava «1 unknown» fra i
    conteggi della casa e `cerca` sulla stessa entita' rispondeva
    `dominio: ""`. Due porte, due risposte sullo stesso oggetto.

    Vince l'ID INTERO, che era anche la scelta del nucleo: un dominio vuoto
    sparisce dai raggruppamenti e dai conteggi -- cioe' fa raccontare una casa
    piu' piccola di com'e' -- mentre un dominio strano si vede e si va a
    guardare. Stesso principio per cui `_domain_name` lascia uscire un
    dominio che non sa tradurre invece di saltare la riga.
    """
    text = str(entity_id)
    return text.split(".", 1)[0] if "." in text else text


def actual_area(entity: dict, device_area: dict[str, str | None]) -> str | None:
    """L'area di un'entita': la PROPRIA se ce l'ha, altrimenti quella del suo
    dispositivo.

    E' una regola di Home Assistant, non una scelta di HIRIS, e sbagliarla fa
    sparire meta' della casa: moltissime entita' non hanno un'area propria, e
    la portano dal dispositivo -- e' il caso NORMALE, non l'eccezione.

    Esiste come funzione per la stessa ragione di `actual_unit`: la
    prendono due posti diversi. `hierarchy()` la usa per costruire l'albero, e
    `memoria.interpretazione.deduci_unit` per capire quale entita' di
    un'area puo' dare l'unita' a un ricordo. Scritta due volte lo era gia': il
    secondo confrontava il solo `area_id` proprio, quindi su una casa vera non
    trovava mai niente e archiviava «in cucina non sotto i 20» come «da 20»
    nudo, senza scala, per sempre.

    `device_area` e' `{device_id: area_id}` -- la costruisce
    `device_areas()`, qui sotto -- vuoto quando il
    registro dei dispositivi non ha risposto. Chi deve DISTINGUERE "non ha
    area" da "non ho potuto leggere i dispositivi" (l'albero lo fa, con la
    pseudo-area «Dispositivi non letti») lo decide prima di chiamare qui:
    questa funzione risponde alla domanda, non la qualifica.
    """
    return entity.get("area_id") or device_area.get(entity.get("dispositivo_id"))


def device_areas(devices) -> dict[str, str | None]:
    """`{device_id: area_id}`, la mappa che `actual_area` legge.

    **Esisteva due volte, e due nomi diversi l'avevano resa invisibile**
    (misura ordine-e-preposizioni, 31/08): la stessa dict-comprehension viveva
    qui dentro `hierarchy()` come `device_area` e in
    `memoria/interpretazione.py::deduci_unit` come `device_area`, passata
    alla stessa `actual_area()`. Nessuno strumento poteva vederlo -- il
    rilevatore di doppioni confronta i PEZZI dei nomi, e li' i pezzi erano gli
    stessi ma l'ordine no. E' la stessa ragione per cui `actual_area` esiste
    come funzione: il fatto e' uno, e scritto due volte diverge.

    **Prende gli oggetti, non la casa**, perche' le due fonti non sono la
    stessa struttura: `hierarchy()` legge il registro grezzo
    (`home_space["dispositivi"]`), `deduci_unit` legge l'indice gia' costruito
    (`Lookup.tutti("dispositivo")`). E' la sola differenza vera fra le due
    copie, ed e' un argomento, non un secondo corpo.

    **La guardia sull'id non e' tolleranza, e' correttezza**: la mappa serve
    SOLO a essere interrogata per `dispositivo_id`, e un oggetto senza id non
    puo' essere il bersaglio del `dispositivo_id` di nessuna entita' --
    tenerlo dentro non aggiungerebbe una risposta, aggiungerebbe una chiave
    che nessuno puo' chiedere. Nel ramo dell'indice la guardia c'era gia' ed
    e' morta per costruzione (`costruisci_indice` salta le voci con `id is
    None`); nel ramo del registro non c'era, e la comprehension diceva
    `d["id"]`: una riga di registro malformata faceva saltare con `KeyError`
    l'INTERO albero della casa, per un oggetto che comunque non sarebbe mai
    stato usato.
    """
    return {d["id"]: d.get("area_id") for d in devices or [] if d.get("id")}


def actual_class(declared: str | None, live: str | None) -> str | None:
    """La classe di un'entita' (`device_class`): la VIVA vince su quella del
    registro -- e sul campo e' l'unica che esista.

    IL PUNTO, misurato sul sorgente di Home Assistant: il comando con cui
    HIRIS legge le entita', `config/entity_registry/list`, risponde con
    `RegistryEntry.as_partial_dict` (`helpers/entity_registry.py:335`), che
    **non contiene `device_class`**, ne' `original_device_class`, ne'
    `aliases`. Quei campi stanno solo in `extended_dict` (`:369`), servito da
    `config/entity_registry/get` e `.../get_entries`.

    Quindi la colonna `classe` dell'anagrafe e' sempre NULL, su ogni casa, e
    per tutto il tempo in cui e' stata l'unica fonte:

    - `nucleo._is_event("binary_sensor", None, "on")` era sempre falso:
      NESSUN sensore binario e' mai entrato in «Notevole adesso». Un
      allagamento, un principio d'incendio, il monossido: muti;
    - le voci di `_CLASS_MEANING` -- l'intera fetta 3.4.0, con
      `carbon_monoxide` verificato una riga per volta -- erano irraggiungibili;
    - `guarda` prometteva la classe e rispondeva `null` su ogni entita'.

    E nessuna prova poteva accorgersene, perche' ogni finta scriveva
    `device_class` dentro la riga del registro: un campo che Home Assistant li'
    non mette. La finta non sapeva produrre il difetto.

    Il rimedio non costa nessuna chiamata in piu': `device_class` e' gia' in
    RAM in ogni voce dello specchio dello stato (`entity_cache._to_minimal`),
    perche' HA lo scrive fra gli attributi di OGNI entita'. Ed e' anche la
    fonte che Home Assistant stesso preferisce
    (`helpers/entity.py::get_device_class`).

    Il ripiego sul registro resta per il giorno in cui HIRIS chiamera'
    `get_entries`: allora le due fonti coesisteranno, e questa funzione dira'
    gia' quale vince.
    """
    for candidate in (live, declared):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def actual_unit(declared: str | None, live: str | None) -> str | None:
    """L'unita' vera di un'entita': la VIVA vince su quella del registro.

    Home Assistant converte le unita' **solo alla prima aggiunta del sensore**:
    il registro puo' quindi portare quella vecchia mentre lo specchio dello
    stato porta quella che HA sta usando adesso. Sul campo il registro non ne
    porta quasi mai una -- e' un campo che HA riempie solo se l'utente l'ha
    forzata a mano (misurato: NULL su 842 entita' su 842) -- ma dove c'e', non
    e' quella che conta.

    Esiste come funzione, e non come due righe scritte dove servono, perche'
    questa decisione la prendono DUE posti diversi: cosa mostrare
    (`domande._con_nome_dedotto`) e cosa dedurre
    (`memoria.interpretazione.deduci_unit`). Scritta due volte sarebbe la
    stessa forma di difetto che ha reso la pagina Modelli vera riga per riga e
    falsa nel complesso: due copie di una regola che nessuno tiene allineate.

    Una stringa vuota o di soli spazi non e' un'unita': e' l'assenza di
    un'unita', esattamente come `None`. E se non c'e' ne' l'una ne' l'altra,
    resta `None`: **non si inventa** -- vedi `sistema_di_riferimento`, che
    descrive la casa e non le sue entita'.
    """
    for candidate in (live, declared):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def hierarchy(home_space: dict[str, list[dict]], unavailable: tuple[str, ...] = ()) -> list[dict]:
    """La casa in forma di albero: piani → aree → entita'.

    Due regole di Home Assistant che vanno rispettate o meta' della casa
    sparisce:

    - un'entita' appartiene alla PROPRIA area se ce l'ha, altrimenti a quella
      del proprio dispositivo. Moltissime entita' non hanno area propria: e'
      il dispositivo a portarla — e' il caso normale, non l'eccezione;
    - un'area puo' non avere piano: le aree vere di Home Assistant senza piano
      finiscono nel contenitore "Senza piano" (`__senza_piano__`), separato da
      tutto il resto.

    Cinque cause distinte producono un silenzio che va dichiarato invece che
    ingoiato — e vanno tenute separate perche' sono cause contrapposte, non
    varianti di un unico "non si sa":

    - se il registro delle aree e' stato letto con successo (`"aree"` non e'
      in `non_disponibili`), un'entita' senza `area_id` (ne' proprio ne'
      ereditato dal dispositivo) davvero non sta in nessuna stanza: va in
      "Senza area" (`__senza_area__`). Se invece ha un `area_id` che non
      corrisponde a nessuna area nota, e' un riferimento penzolante —
      un'incoerenza vera dell'anagrafe, non un'assenza: va in "Area
      sconosciuta" (`__area_sconosciuta__`), cosi' resta visibile invece di
      confondersi con chi davvero non ha casa;
    - se il registro delle aree NON e' stato letto, non possiamo piu' fidarci
      di nessuna delle due letture sopra: un'entita' con `area_id` a None
      potrebbe davvero non avere area, ma un'entita' con un `area_id` che
      "non risulta noto" potrebbe semplicemente stare in un'area che non
      abbiamo potuto leggere. Non potendo distinguerle, non si distinguono:
      finiscono tutte insieme in "Aree non lette" (`__aree_non_lette__`),
      cosi' chi guarda vede "non ho potuto leggere le aree" e non "questa
      casa non ha organizzazione";
    - se un'entita' non ha area propria e la eredita dal dispositivo (il caso
      normale), ma il registro dei DISPOSITIVI non e' stato letto, non
      possiamo sapere quale area avrebbe ereditato: trattarla come "senza
      area" affermerebbe un dato che non abbiamo. Va in "Dispositivi non
      letti" (`__dispositivi_non_letti__`), cosi' una casa vera non appare ne'
      vuota ne' senza organizzazione solo perche' e' caduto il registro che
      porta l'ereditarieta';
    - se ci sono aree vere senza piano ma il registro dei PIANI non e' stato
      letto, quelle aree NON vanno in "Senza piano": quel nome afferma "questa
      casa non organizza per piani", e potrebbe non essere vero — sappiamo
      solo di non aver potuto leggere i piani. Vanno in "Piani non letti"
      (`__piani_non_letti__`), distinto da "Senza piano".

    I quattro gruppi di entita' fuori dalle aree note (quelli non vuoti) stanno
    dentro un secondo piano-contenitore, "Fuori dalle aree"
    (`__fuori_dalle_aree__`), distinto dal "Senza piano"/"Piani non letti"
    delle aree vere — sono concetti diversi che in una versione precedente
    condividevano per errore lo stesso id `None`, facendo sparire in silenzio
    l'uno o l'altro a chiunque indicizzasse i piani per id.

    Le entita' disabilitate restano nell'archivio ma non nei CONTEGGI: sono in
    Home Assistant e non funzionano, quindi contarle come stanze arredate
    ingannerebbe chi legge. Restano pero' raggiungibili per area, nella chiave
    parallela `entita_disabilitate` di ogni area (mai in `entita`, che conta):
    una vista di DETTAGLIO su un'area (`domande.guarda`) deve poter mostrare
    "questa luce c'e' ma e' disabilitata", marcata, non farla sparire in
    silenzio come se non esistesse (IMPORTANT ⑦-adiacente, Minor).

    Le entita' NASCOSTE (`hidden_by` non nullo: l'utente le ha tolte dalle
    proprie viste in Home Assistant) prendono la STESSA forma, dalla fetta
    "nascoste fuori dagli elenchi" (2026-08-25): fuori da `entita` -- che
    conta, e che alimenta anche "La casa" del nucleo (`nucleo._home_space_lines`
    legge `area["entita"]` cosi' com'e') -- dentro una terza chiave
    parallela, `entita_nascoste`. Il proprietario ha misurato in produzione
    che `guarda("area", "sala_da_pranzo")` restituiva sette luci mescolate,
    quattro delle quali nascoste: il campo `nascosta` c'era gia' su ogni
    entita' (`domande._enrich_entity`), ma stare nella STESSA lista non
    ha impedito che venissero elencate lo stesso -- la prova che un dato
    presente non basta, la sua POSIZIONE deve escluderlo da chi legge solo
    "cosa c'e' in questa stanza". Regola del proprietario: "HIRIS non prende
    in considerazione le entita' nascoste, a meno che non gli vengano
    chieste esplicitamente" -- e "non prende in considerazione" vuol dire
    fuori dalla lista che si legge per prima, non un campo da ricordarsi di
    filtrare.

    Una disabilitata e nascosta insieme finisce in `entita_disabilitate`, non
    in `entita_nascoste`: stessa precedenza che `nucleo.py` applica gia' al
    proprio conteggio delle nascoste (`nascosta and not disabilitata`) -- non
    due modi diversi di dire la stessa cosa su due rami diversi del prodotto.

    Effetto collaterale voluto, non un caso: "La casa" del nucleo, che legge
    lo stesso `area["entita"]`, smette anch'essa di contare le nascoste nei
    conteggi per dominio -- allineandosi a "Notevole adesso"
    (`nucleo._highlight_lines`), che le esclude gia' da prima con un `if
    e.get("nascosta"): continue` esplicito. Prima di questa fetta le due
    sezioni del nucleo si contraddicevano fra loro: una le contava, l'altra
    no.
    """
    device_loaded = "dispositivi" not in unavailable
    device_area = device_areas(home_space.get("dispositivi"))

    per_area: dict[str | None, list[dict]] = {}
    per_area_disabled: dict[str | None, list[dict]] = {}
    per_area_hidden: dict[str | None, list[dict]] = {}
    unloaded_device = []
    for entity in home_space.get("entita", []):
        own_area = entity.get("area_id")
        device_id = entity.get("dispositivo_id")
        if not own_area and device_id and not device_loaded:
            # Erediterebbe l'area dal dispositivo, ma il registro dei
            # dispositivi non ha risposto: non possiamo sapere quale sarebbe,
            # quindi non finge di essere "senza area". Vale anche per le
            # disabilitate e le nascoste: non risolvibili, non tracciate
            # nemmeno a parte.
            if not entity.get("disabilitata"):
                unloaded_device.append(entity)
            continue
        area_id = actual_area(entity, device_area)
        if entity.get("disabilitata"):
            per_area_disabled.setdefault(area_id, []).append(entity)
        elif entity.get("nascosta"):
            per_area_hidden.setdefault(area_id, []).append(entity)
        else:
            per_area.setdefault(area_id, []).append(entity)

    areas_per_floor: dict[str | None, list[dict]] = {}
    known_areas = set()
    for area in home_space.get("aree", []):
        known_areas.add(area["id"])
        areas_per_floor.setdefault(area.get("piano_id"), []).append({
            "id": area["id"],
            "nome": area["nome"],
            "alias": area.get("alias", []),
            "etichette": area.get("etichette", []),
            # Quale entita' e' LA temperatura (e l'umidita') di questa stanza,
            # dichiarata dall'utente in Home Assistant.
            "entita_temperatura": area.get("entita_temperatura"),
            "entita_umidita": area.get("entita_umidita"),
            "entita": per_area.get(area["id"], []),
            # Non nei conteggi (vedi il docstring), ma raggiungibili nel
            # dettaglio di un'area -- vedi `domande._view_area`.
            "entita_disabilitate": per_area_disabled.get(area["id"], []),
            # Stessa forma, per le nascoste: non nei conteggi, raggiungibili
            # a parte -- vedi il docstring qui sopra.
            "entita_nascoste": per_area_hidden.get(area["id"], []),
        })

    # Le entita' fuori dalle aree note si dividono per causa. Se le aree non
    # sono state lette, non possiamo fidarci nemmeno della distinzione fra
    # "area_id assente" e "area_id sconosciuto": vanno tutte in un unico
    # bucket "Aree non lette".
    area_loaded = "aree" not in unavailable
    without_area, unloaded_area, unknown_area = [], [], []
    for area_id, entries in per_area.items():
        if area_id in known_areas:
            continue
        if not area_loaded:
            unloaded_area.extend(entries)
        elif area_id is None:
            without_area.extend(entries)
        else:
            unknown_area.extend(entries)

    floors = []
    for floor in home_space.get("piani", []):
        floors.append({
            "id": floor["id"], "nome": floor["nome"], "livello": floor.get("livello"),
            "aree": areas_per_floor.pop(floor["id"], []),
        })
    floors.sort(key=lambda p: (p["livello"] is None, p["livello"] or 0, p["nome"]))

    # Le aree senza piano si dividono per la stessa causa delle entita' senza
    # area sopra: se i piani non sono stati letti, "Senza piano" affermerebbe
    # un dato che non abbiamo.
    floor_loaded = "piani" not in unavailable
    rest = [a for entries in areas_per_floor.values() for a in entries]
    if rest:
        if floor_loaded:
            floors.append({"id": _ID_WITHOUT_FLOOR, "nome": "Senza piano", "livello": None,
                          "aree": rest})
        else:
            floors.append({"id": _ID_UNLOADED_FLOOR, "nome": "Piani non letti", "livello": None,
                          "aree": rest})

    outside_areas = []
    if unloaded_area:
        outside_areas.append({"id": _ID_UNLOADED_AREA, "nome": "Aree non lette",
                                 "alias": [], "etichette": [], "entita": unloaded_area})
    if unknown_area:
        outside_areas.append({"id": _ID_UNKNOWN_AREA, "nome": "Area sconosciuta",
                                 "alias": [], "etichette": [], "entita": unknown_area})
    if without_area:
        outside_areas.append({"id": _ID_WITHOUT_AREA, "nome": "Senza area",
                                 "alias": [], "etichette": [], "entita": without_area})
    if unloaded_device:
        outside_areas.append({"id": _ID_UNLOADED_DEVICE, "nome": "Dispositivi non letti",
                                 "alias": [], "etichette": [], "entita": unloaded_device})
    if outside_areas:
        floors.append({"id": _ID_OUTSIDE_AREAS, "nome": "Fuori dalle aree", "livello": None,
                      "aree": outside_areas})

    return floors


# --- il confronto: l'albero smette di essere un'affermazione ---------------
#
# `hierarchy()` qui sopra e' una REPLICA che HIRIS costruisce dai registri: e'
# un'affermazione sulla casa, e fino a questa fetta niente la verificava. Se
# un'area contiene cose che HIRIS non le attribuisce, o se HIRIS le attribuisce
# cose che non ci sono, non c'era modo di accorgersene -- se non sbagliando una
# risposta davanti all'utente.
#
# Il secondo parere e' di Home Assistant su se stesso: `extract_from_target`
# (`HAClient.extract_from_target`) RISOLVE un'area invece di dedurla. Le
# funzioni qui sotto sono la meta' pura di quel confronto: la rete la fa il
# chiamante (`server.tree_comparison_round`), qui arrivano solo le risposte
# gia' lette -- la stessa disciplina di `compose()`, che riceve `stato` e
# `problemi` come argomenti.

# QUANTE aree per giro, e perche' non tutte.
#
# Un controllo che costa quanto la cosa che controlla non si esegue mai: una
# casa vera ha 16-30 aree, e confrontarle tutte vorrebbe dire trenta comandi
# WebSocket a giro contro gli otto che costa leggere l'intera anagrafe. Tre e'
# il numero che tiene il costo del controllo sotto la meta' di quello della
# ricostruzione, e che con la rotazione qui sotto copre comunque tutta la casa
# in poche decine di minuti. Non e' un tetto di sicurezza: e' il CAMPIONE, e
# chi lo legge deve saperlo -- per questo `compare_with_home_assistant`
# dichiara sempre `aree_totali`, e il nucleo non dice mai una divergenza senza
# dire su quante aree l'ha cercata.
AREAS_PER_ROUND = 3


def _area_lookup(floors: list[dict]) -> dict[str, dict]:
    """`{area_id: area}` per le sole aree VERE dell'albero.

    Le pseudo-aree (`is_pseudo_area`: «Senza area», «Aree non lette», «Area
    sconosciuta», «Dispositivi non letti») restano fuori, e non e' un
    dettaglio: non esistono in Home Assistant, quindi chiedergli cosa contiene
    `__senza_area__` risponderebbe `aree_mancanti` -- una divergenza inventata
    da noi, sull'unico contenitore che dichiara gia' di essere una nostra
    costruzione. Confrontare vuol dire chiedere all'originale qualcosa che
    l'originale conosce.
    """
    lookup: dict[str, dict] = {}
    for floor in floors or []:
        for area in floor.get("aree") or []:
            identifier = area.get("id")
            if not identifier or is_pseudo_area(identifier):
                continue
            lookup[identifier] = area
    return lookup


def tree_areas(floors: list[dict]) -> list[dict]:
    """Le aree vere dell'albero -- `[{"id", "nome"}]` -- ordinate per id.

    L'ordine e' per ID e non per nome: e' l'unica chiave che Home Assistant
    garantisce stabile (rinominare un'area non cambia il suo `area_id`), e la
    rotazione del campione (`choose_sample`) ci si appoggia -- un ordine che
    cambia quando l'utente rinomina una stanza farebbe saltare il turno a
    un'area a caso.
    """
    return sorted(({"id": identifier, "nome": area.get("nome") or identifier}
                   for identifier, area in _area_lookup(floors).items()),
                  key=lambda a: a["id"])


def choose_sample(areas: list[dict], count: int = AREAS_PER_ROUND,
                  after: str | None = None) -> list[dict]:
    """Le prossime `quante` aree da confrontare, a ROTAZIONE.

    A rotazione e non a caso, per due ragioni che contano entrambe:

    - **copertura garantita**. Un campione casuale rigirerebbe sulla stessa
      area due volte e ne lascerebbe un'altra mai guardata per ore; la
      rotazione garantisce che ogni area della casa venga confrontata entro un
      giro completo (`len(aree) / quante` esecuzioni), che e' l'unica forma in
      cui un campione parziale ha un limite dichiarabile;
    - **riproducibilita'**. Il nucleo e' un testo che si legge e si confronta
      fra due momenti: due esecuzioni identiche devono produrre lo stesso
      nucleo. Un campione casuale lo farebbe cambiare senza che sia cambiato
      niente nella casa, ed e' esattamente il rumore che rende una riga
      illeggibile a forza di comparire ogni volta diversa.

    `dopo` e' l'id dell'ULTIMA area del giro precedente, non un indice: un
    indice dentro una lista che cambia -- un'area aggiunta, una cancellata --
    salterebbe o ripeterebbe una posizione in silenzio, mentre «la prima dopo
    questa» resta vera comunque. Finito il giro si ricomincia da capo.
    """
    if count <= 0 or not areas:
        return []
    start = 0
    if after:
        for i, area in enumerate(areas):
            if area["id"] > after:
                start = i
                break
        else:
            start = 0
    count = min(count, len(areas))
    doubled = list(areas) + list(areas)
    return doubled[start:start + count]


def _excluded_from_comparison(entity: dict | None) -> bool:
    """Vero se questa entita' NON e' confrontabile fra i due alberi.

    Tre differenze fra la nostra lista e quella di Home Assistant NON sono
    divergenze: sono regole di HA, verificate alla fonte
    (`homeassistant/helpers/target.py`, `helpers/entity_registry.py`), e
    contarle come divergenze produrrebbe un avviso su ogni casa del mondo --
    cioe' una riga che smette subito di essere letta.

    - **nascoste**: `_include_entry` scarta ogni voce con `hidden_by` non
      nullo. `hierarchy()` le tiene anche lei -- fuori da `entita` (che
      conta) e dalla `nostre` di questo confronto, dentro la chiave parallela
      `entita_nascoste` (fetta "nascoste fuori dagli elenchi", 2026-08-25):
      sono entita' vere, che l'utente ha solo tolto dalle proprie viste, non
      voci che HIRIS ha perso. Questa funzione non deve piu' scartarle a
      mano sul lato "nostre" -- non ci sono gia' -- ma resta l'unico modo di
      scartarle sul lato "loro" (`note`, letto dall'anagrafe grezza qui
      sotto, non dall'albero di `hierarchy()`);
    - **di servizio** (`entity_category`, cioe' `config`/`diagnostic`): lo
      stesso `_include_entry` le scarta quando `primary_entities_only` e'
      vero, ed e' vero -- `extract_from_target` lo passa esplicito, perche'
      cosi' fa una chiamata di servizio reale. Nell'anagrafe e' la colonna
      `categoria`, da non confondere con `categorie` (la tassonomia
      dell'utente);
    - **disabilitate**: HA le esclude quando l'entita' eredita l'area dal
      dispositivo (`get_entries_for_device_id` ha
      `include_disabled_entities=False` come predefinito) e le INCLUDE quando
      l'area e' dell'entita' stessa (`get_entries_for_area_id` non filtra
      niente). Due regole diverse per lo stesso stato: tenerle fuori da
      entrambi i lati e' l'unico modo di non far dipendere l'esito da quale
      delle due strade un'entita' ha preso per arrivare nell'area.

    `None` -- un id che Home Assistant riporta e l'anagrafe non conosce affatto
    -- NON e' fuori dal confronto: e' la divergenza piu' netta che esista, e
    scartarla per prudenza sarebbe il difetto che questa fetta esiste per
    chiudere.
    """
    if not isinstance(entity, dict):
        return False
    return bool(entity.get("nascosta")
                or entity.get("disabilitata")
                or str(entity.get("categoria") or "").strip())


def _compare_area(area: dict | None, identifier: str, answer,
                  known: dict[str, dict]) -> dict:
    """Il verdetto su UNA area: `{"area", "nome"}` piu' uno dei due esiti.

    O `errore` (non si e' potuto guardare) o la coppia `mancanti`/`in_piu`
    (si e' guardato). Mai entrambi, e mai nessuno dei due: un confronto non
    letto non e' un confronto riuscito, e vale per la singola area
    esattamente come per il giro intero.
    """
    entry = {"area": identifier, "nome": (area or {}).get("nome") or identifier}
    if area is None:
        # Il campione nasce dall'albero, quindi in produzione questo ramo
        # scatta solo se l'anagrafe si e' ricostruita fra la domanda e la
        # risposta. Non e' un combaciare: e' un confronto perso.
        entry["errore"] = ("quest'area non e' piu' nell'albero: l'anagrafe si e' "
                          "ricostruita mentre la si confrontava")
        return entry
    if not isinstance(answer, dict):
        entry["errore"] = "Home Assistant non ha risposto"
        return entry
    fault = str(answer.get("errore") or "").strip()
    if fault:
        entry["errore"] = fault
        return entry

    # L'area che HA dichiara MANCANTE e' il caso peggiore in forma pura: HIRIS
    # ha una stanza intera che l'originale non ha piu'. Si dice a parte perche'
    # «quell'area non c'e'» spiega in una parola cio' che altrimenti
    # arriverebbe come un elenco di entita' che non si toccano -- la stessa
    # distinzione fra «l'area e' vuota» e «quell'area non c'e'» che
    # `extract_from_target` porta gia' nelle sue due meta'.
    entry["assente_in_ha"] = identifier in (answer.get("aree_mancanti") or [])

    ours = {e.get("id") for e in area.get("entita") or []
              if e.get("id") and not _excluded_from_comparison(e)}
    theirs = {i for i in answer.get("entita") or []
            if i and not _excluded_from_comparison(known.get(i))}
    entry["mancanti"] = sorted(theirs - ours)
    entry["in_piu"] = sorted(ours - theirs)
    return entry


def compare_with_home_assistant(floors: list[dict], home_space: dict,
                                answers: dict[str, dict]) -> dict:
    """Il giro di confronto, in forma pura: albero + risposte di HA -> esito.

    `risposte` e' `{area_id: cio' che ha risposto extract_from_target}`, nello
    stesso ordine in cui le aree sono state chieste. Restituisce::

        {"aree_totali": 16, "guardate": [{...}, {...}, {...}]}

    `aree_totali` esce SEMPRE, anche quando tutto combacia: un campione taciuto
    fa sembrare completo un controllo parziale, ed e' l'unica riga da cui chi
    legge puo' sapere che si sono guardate tre aree su sedici.

    Nessuna data qui dentro: la mette il chiamante, come mette la rete. Una
    funzione pura che leggesse l'orologio non sarebbe piu' confrontabile con se
    stessa.
    """
    lookup = _area_lookup(floors)
    known = {e.get("id"): e for e in (home_space.get("entita") or []) if e.get("id")}
    checked = [_compare_area(lookup.get(identifier), identifier, answer, known)
                for identifier, answer in (answers or {}).items()]
    return {"aree_totali": len(lookup), "guardate": checked}
