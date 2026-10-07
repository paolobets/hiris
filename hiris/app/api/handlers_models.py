from __future__ import annotations

import json
import logging
import os
import re
import time

import aiohttp
from aiohttp import web

from ..model_resolution import (
    CHAIN_END,
    compose_now,
    compose_panel,
    compose_topology,
)
from ..providers import (
    CLAUDE,
    DEFAULT_PRESET,
    OLLAMA,
    OPENAI,
    OPENROUTER,
    SUBSCRIPTION,
    all_providers,
    chain_members,
    chosen_model,
    credentials_present,
)
from ..providers import get as provider_of
from .boundary import json_object

logger = logging.getLogger(__name__)

# brain_model e' uscito alla fetta E5 Task 7 ("Consumi e Modelli smettono di
# mentire"): il Brain che lo leggeva e' uscito con la E3, zero lettori di
# produzione da allora. Non e' un'opzione dell'add-on (vive solo in
# models_config.json), quindi esce dai tre posti reali -- lettore e
# scrittore qui sotto, UI in config/models-route.js -- nello stesso commit.
#
# Gli id che la catena accetta (`_VALID_BACKENDS`) e i provider che hanno un
# modello in `provider_models` (`_PROVIDER_MODEL_KEYS`) erano due elenchi
# scritti qui a mano: dal Task 9 della Tappa 7 si chiedono alla tabella dei
# provider (`chain_members()` e `Provider.model_path`).

#: La chiave dell'archivio che tiene il modello scelto dei provider che non
#: hanno una sezione propria (il piano sta in `ponte`, Ollama in `ollama`).
_PROVIDER_MODELS = "provider_models"


def _clean_provider_models(raw) -> dict:
    """Una stringa per ogni provider il cui modello vive in `provider_models`
    (`""` = automatico). Le altre chiavi si scartano in lettura E in
    scrittura: `provider_models["ollama"]` era un fantasma, e resta fuori."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for p in all_providers():
        if p.model_path[:1] != (_PROVIDER_MODELS,):
            continue
        v = raw.get(p.id, "")
        out[p.id] = v if isinstance(v, str) else ""
    return out


# Task 6 -- versione A della migrazione. Le decisioni che escono da config.yaml
# e vengono a vivere qui (fetta «la catena diventa l'unica verita'»). Un
# dizionario di predefiniti, non cinque costanti sparse: `load` e `save`
# leggono la stessa struttura, e un campo aggiunto qui non puo' dimenticarsi in
# uno dei due.
_STORE_DEFAULTS = {
    # `modello`: il modello del piano, che dalla fetta «il modello del piano»
    # e' un valore SUO e non piu' un effetto di `provider_models["claude"]`.
    # Il predefinito e' `"sonnet"` e NON la stringa vuota: vuoto
    # significherebbe «non so», e «non so» e' la forma con cui la regola «se
    # non so niente allora comportati come prima» e' gia' rientrata quattro
    # volte in questo prodotto, da quattro porte diverse. Il campo nasce con un
    # valore, e la semina (`options_migration.seed_subscription_model`) lo
    # sostituisce una volta sola con quello che l'installazione stava gia'
    # usando.
    # I numeri vivono qui e solo qui. Fino al 02/10/2026 stavano in
    # `options_migration._DEFAULTS`, accanto alla semina delle opzioni che li
    # copiava; uscita la semina, questo dizionario era rimasto il loro unico
    # lettore.
    "ponte": {"attivo": False, "scadenza_min": 5, "tetto_giornaliero": 50,
              "modello": "sonnet"},
    OLLAMA.id: {"modello": "", "timeout_s": OLLAMA.reply_timeout_s},
}

# Le sole chiavi che un CLIENT puo' scrivere: le sei decisioni della pagina
# Modelli. Tutto il resto che sta sul disco (a partire da 'brain_model')
# sopravvive intatto -- vedi la lettura-modifica-scrittura in
# save_models_config.
_OUR_KEYS = (
    "chain_order", _PROVIDER_MODELS, "ponte", OLLAMA.id,
    "nascondi_gratuiti", "strategia_ultima",
)

# I SEGNI DELLA MIGRAZIONE, che non sono decisioni e non viaggiano in una PUT.
# `catena_seminata` dice che la catena e' gia' stata composta, `piano_seminato`
# che il modello del piano e' gia' stato copiato. Stavano in `_OUR_KEYS` e ne
# sono usciti: un client che rimandasse `catena_seminata: false` -- la pagina
# lo faceva, con lo `state.cfg` di default, dopo un GET fallito; qualunque
# client con uno snapshot stale lo farebbe ancora -- farebbe RIGIRARE la semina
# al riavvio successivo, e una catena svuotata di proposito si ripopolerebbe.
# Cioe' una perdita silenziosa innescata da un click.
#
# `seminato` era il segno della semina delle OPZIONI, uscita il 02/10/2026:
# nessuno lo scrive ne' lo legge piu'. Resta in questo elenco e nella forma
# della rotta finche' il cambio di forma non e' dichiarato (registro, M-80).
#
# Il valore sopravvive comunque a ogni PUT: `_store_keys` lo ricava da
# `base`, che parte dal contenuto GIA' SU DISCO. Solo l'avvio li scrive, con
# `flags=True`.
_MIGRATION_FLAGS = ("seminato", "catena_seminata", "piano_seminato")


def bridge_deadline_min(models_config: dict | None) -> int:
    """Quanti minuti ha un turno accodato sul ponte per avere risposta.

    **Una lettura sola** (Tappa 6, Task 2). Fino a qui la stessa espressione
    era scritta in otto punti -- sei accodamenti, lo spazzino e la promessa
    scaduta -- e due ripiegavano su un `5` scritto a mano invece che sul
    predefinito di `_STORE_DEFAULTS` (spec §4.3, «scadenza riletta in 8
    punti»). Si legge all'ACCODAMENTO: da li' in poi la scadenza viaggia col
    turno (`deadline_ts`), e chi deve dire quanto ha aspettato un turno lo
    legge dal turno, non da qui.
    """
    return int((models_config or {}).get("ponte", {}).get(
        "scadenza_min", _STORE_DEFAULTS["ponte"]["scadenza_min"]))


def _clamp_int(value, default: int, minimum: int, maximum: int) -> int:
    """Gli stessi estremi dello `schema:` di config.yaml (`int(1,120)`,
    `int(0,1000)`, `int(10,1800)`). Il Supervisor li faceva rispettare per noi;
    da quando il valore arriva da una PUT tocca a noi -- e si RIPORTA DENTRO,
    come faceva il modulo, invece di rifiutare il salvataggio intero: un
    numero fuori range non e' un corpo malformato.

    Il massimo di `scadenza_min` resta 120 come nello schema, benche' il tetto
    UTILE sia 5 minuti (`static/chat/send.js`, CHAT_POLL_MAX_MS): abbassarlo
    qui farebbe rientrare a 5 il valore di chi ne aveva uno piu' alto, cioe' la
    migrazione perderebbe proprio cio' che esiste per conservare. Il disallineo
    fra i due numeri e' dichiarato, non risolto in questa fetta."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, n))


def _clean_subscription_model(value, default: str) -> str:
    """Uno dei tre alias, sempre. Si RIPORTA DENTRO come i due `_clamp_int`
    accanto: un valore fuori dall'insieme non e' un corpo malformato.

    Il riduttore e' `agent.runner.cli_model`, che qui trova il suo UNICO
    chiamante rimasto. Fino alla fetta «il modello del piano» ne aveva due --
    il turno del ponte (`handlers_chat._enqueue_chat_job`) e la riga della
    pagina (`_models_in_use`) -- che erano lo stesso calcolo fatto in due
    file, cioe' due implementazioni della stessa regola libere di divergere.
    Adesso traduce una volta sola, all'INGRESSO del campo: cio' che sta
    nell'archivio e' gia' un alias, e chi legge non ha niente da tradurre.

    L'import e' differito. Lo obbligava un ciclo (`api/handlers_chat.py`
    importava da quel modulo) che non c'e' piu': vedi
    `agent/runner._mcp_server_name`.
    """
    from ..agent.runner import cli_model
    if not isinstance(value, str) or not value.strip():
        return default
    return cli_model(value)


def _clean_bridge(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    d = _STORE_DEFAULTS["ponte"]
    return {
        "attivo": bool(raw.get("attivo", d["attivo"])),
        "scadenza_min": _clamp_int(raw.get("scadenza_min"), d["scadenza_min"], 1, 120),
        "tetto_giornaliero": _clamp_int(
            raw.get("tetto_giornaliero"), d["tetto_giornaliero"], 0, 1000),
        "modello": _clean_subscription_model(raw.get("modello"), d["modello"]),
    }


def _clean_ollama(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    d = _STORE_DEFAULTS[OLLAMA.id]
    model = raw.get("modello", d["modello"])
    return {
        "modello": model if isinstance(model, str) else "",
        "timeout_s": _clamp_int(raw.get("timeout_s"), d["timeout_s"], 10, 1800),
    }


def _store_keys(raw: dict) -> dict:
    """Le cinque chiavi nuove, pulite. Usata da `load` e da `save`: un solo
    posto in cui la forma e' definita."""
    strategy = raw.get("strategia_ultima")
    return {
        "ponte": _clean_bridge(raw.get("ponte")),
        OLLAMA.id: _clean_ollama(raw.get(OLLAMA.id)),
        "nascondi_gratuiti": bool(raw.get("nascondi_gratuiti", False)),
        # Debito F del Task 6, chiuso qui: il predefinito del campo e' quello
        # dell'opzione da cui viene (`llm_strategy: "balanced"` in
        # config.yaml). Valeva "", e la differenza faceva contare come
        # «copiato» un valore che nessuno aveva scelto.
        "strategia_ultima": strategy if isinstance(strategy, str) else DEFAULT_PRESET,
        "seminato": bool(raw.get("seminato", False)),
        # Il segno della semina della CATENA, distinto da `seminato` (che e'
        # quello delle OPZIONI). Prima non esisteva e la semina della catena si
        # regolava su «chain_order e' vuota»: ma una catena vuota, da questa
        # fetta, e' una DECISIONE esprimibile in due click, e al riavvio veniva
        # ripopolata dalla regola `legacy` -- cioe' la regola di compatibilita'
        # tolta dal prodotto rientrava dalla porta della migrazione.
        "catena_seminata": bool(raw.get("catena_seminata", False)),
        # Il segno della semina del MODELLO DEL PIANO, distinto dagli altri due:
        # e' la TERZA migrazione, e un archivio puo' trovarsi a due terzi. Come
        # gli altri vive fuori da `_OUR_KEYS`: un client che lo rimandasse
        # a `false` farebbe rigirare la semina al riavvio successivo, e la
        # semina ricopre `ponte.modello` -- cioe' la scelta dell'utente.
        "piano_seminato": bool(raw.get("piano_seminato", False)),
    }


def _models_config_path(data_dir: str) -> str:
    return os.path.join(data_dir, "models_config.json")


def _set_aside_unreadable_store(path: str) -> None:
    """Rinomina in `.corrotto` invece di lasciarlo sovrascrivere.

    `save_models_config` fa lettura-modifica-scrittura partendo dal disco: se
    il disco non si legge riparte da `{}` e al primo salvataggio -- che
    dall'avvio arriva da solo, con la semina -- i byte di prima sono persi per
    sempre. Un byte di disco contro dodici decisioni.

    Il piu' VECCHIO `.corrotto` non si sovrascrive: e' quello scritto quando il
    file era ancora quello dell'utente. Un secondo guasto salverebbe sopra di
    lui l'archivio dei predefiniti gia' riscritto, cioe' niente.
    """
    corrupted_path = path + ".corrotto"
    try:
        if os.path.exists(corrupted_path):
            logger.error(
                "%s esiste gia' e non viene sovrascritto: contiene la copia "
                "piu' vecchia, cioe' l'unica che puo' ancora avere i tuoi "
                "valori. Il file illeggibile di adesso resta dov'e'.", corrupted_path)
            return
        os.replace(path, corrupted_path)
        logger.error(
            "Il file illeggibile e' stato messo da parte in %s invece di essere "
            "sovrascritto: da li' si possono ancora recuperare a mano i valori "
            "che conteneva.", corrupted_path)
    except OSError as error:
        logger.error(
            "Non si e' potuto mettere da parte %s (%s): il prossimo salvataggio "
            "lo sovrascrivera'.", path, error)


def _read_raw_store(path: str) -> dict:
    """Legge `models_config.json`, e quando NON si legge lo dice e lo mette da parte.

    Questa lettura falliva in `{}` senza una riga di log. Da questa versione
    l'archivio e' l'UNICA copia esistente di dodici decisioni dell'utente (le
    quattordici opzioni sono uscite dallo schema dell'add-on): un file troncato
    -- una scrittura interrotta su una scheda SD -- faceva ripartire l'avvio
    dai predefiniti, ricomporre la catena con la regola di compatibilita', e
    riscrivere sopra. Le due sole righe che parlavano erano quelle della
    semina, e affermavano entrambe il contrario («erano tutti ai predefiniti»,
    «la catena e' stata copiata»).

    Stessa disciplina di `brain_model` qui sotto -- «il silenzio si dichiara»
    -- su una posta incomparabilmente piu' alta. `FileNotFoundError` resta
    silenzioso: e' il primo avvio, ed e' normale.

    Unico lettore del file: `load_models_config` e `save_models_config` passano
    di qui, o la regola varrebbe in un posto solo -- e il posto scoperto
    sarebbe proprio quello che riscrive.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return {}
    except Exception as error:
        logger.error(
            "%s non si e' potuto leggere (%s: %s). HIRIS riparte dai predefiniti: "
            "catena, ponte, Ollama, filtro dei gratuiti e preset che avevi "
            "scelto NON sono stati letti. Da questa versione questo file e' "
            "l'unica copia di quelle decisioni.",
            path, type(error).__name__, error)
        _set_aside_unreadable_store(path)
        return {}
    if not isinstance(raw, dict):
        logger.error(
            "%s contiene %s invece di un oggetto JSON. HIRIS riparte dai "
            "predefiniti: le decisioni che conteneva NON sono state lette.",
            path, type(raw).__name__)
        _set_aside_unreadable_store(path)
        return {}
    return raw


def load_models_config(data_dir: str) -> dict:
    raw = _read_raw_store(_models_config_path(data_dir))
    raw_chain = raw.get("chain_order", [])
    if not isinstance(raw_chain, list):
        raw_chain = []
    members = chain_members()
    chain = [n for n in raw_chain if n in members]
    # fetta E5 Task 7: un models_config.json scritto da una versione
    # precedente puo' avere 'brain_model' popolato -- non viene ne' migrato
    # ne' cancellato (mai dati utente rimossi silenziosamente), ma il
    # silenzio si dichiara: stessa disciplina di
    # tests/test_startup_legacy_db_silence.py. save_models_config (sotto) fa
    # lettura-modifica-scrittura, quindi la chiave sopravvive anche a un
    # salvataggio, non solo al load.
    if "brain_model" in raw:
        logger.info(
            "models_config.json contiene 'brain_model' (%r) di un'installazione "
            "precedente -- non piu' letto ne' scritto da questa versione.",
            raw.get("brain_model"),
        )
    return {
        "chain_order": chain,
        _PROVIDER_MODELS: _clean_provider_models(raw.get(_PROVIDER_MODELS)),
        **_store_keys(raw),
    }


def save_models_config(data_dir: str, data: dict, *, flags: bool = False) -> dict:
    """`flags=True` e' riservato all'avvio (`server._on_startup`): e' l'unico
    momento in cui `seminato`/`catena_seminata` si scrivono. Ogni altro
    chiamante -- la PUT, e quindi la pagina -- li lascia dove sono: vedi
    `_MIGRATION_FLAGS`."""
    if not isinstance(data, dict):
        data = {}
    path = _models_config_path(data_dir)
    tmp = path + ".tmp"
    # Lettura-modifica-scrittura (stesso fix di claude_runner._save_usage per
    # 'per_agent'): senza questo, il PRIMO salvataggio dopo un upgrade
    # cancellerebbe silenziosamente un 'brain_model' legacy dal disco -- il
    # contrario di quanto dichiara il log in load_models_config ("non piu'
    # letto ne' scritto", che un operatore legge come "e' ancora li'"). Solo
    # le chiavi che questa versione possiede (_OUR_KEYS) vengono
    # aggiornate; qualunque altra chiave gia' sul disco (incl. 'brain_model')
    # resta intatta.
    # Stessa lettura di `load_models_config`, e quindi stessa regola quando il
    # file non si legge: lo dice e lo mette da parte. Qui vale ancora di piu',
    # perche' e' la riga DOPO che sovrascrive.
    disk_data = _read_raw_store(path)
    # Task 6: la fusione parte dal CONTENUTO GIA' SU DISCO, non dai
    # predefiniti -- ed e' la STESSA ragione del fix di claude_runner._save_usage
    # per 'per_agent'. Da quando le chiavi scritte sono sette invece di due, un
    # corpo parziale (`{"chain_order": [...]}`) ricostruito sui predefiniti
    # azzererebbe ponte, Ollama e nascondi_gratuiti: una perdita di
    # configurazione silenziosa, cioe' esattamente cio' che la versione A
    # esiste per impedire. Il contratto della PUT e' «sempre l'oggetto intero»
    # e la pagina lo rispetta. La difesa resta anche se OGGI la pagina e'
    # l'unico client: misurato l'01/09 (fetta «la rinomina», lotto delle
    # rotte) su `hiris-mcp-gateway`, il gateway non chiama questa rotta ne'
    # nessun'altra di quelle convertite -- nomina solo `/api/reasoning/*`. Il
    # commento che lo dava per cliente diceva il falso; il CODICE no, e non si
    # toglie: e' la difesa che rende sicuro il giorno in cui un secondo client
    # nascera' davvero.
    writable = _OUR_KEYS + (_MIGRATION_FLAGS if flags else ())
    base = dict(disk_data)
    base.update({k: v for k, v in data.items() if k in writable})
    raw_chain = base.get("chain_order", [])
    if not isinstance(raw_chain, list):
        # Una chain_order non-lista (null, un numero) non e' un 500: si azzera,
        # come faceva la guardia che stava qui prima della fusione.
        raw_chain = []
    clean = {
        "chain_order": [n for n in raw_chain if n in chain_members()],
        _PROVIDER_MODELS: _clean_provider_models(base.get(_PROVIDER_MODELS)),
        **_store_keys(base),
    }
    disk_data.update(clean)
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(disk_data, fh)
    os.replace(tmp, path)
    return clean



# La credenziale di un provider si misura con `providers.credentials_present`,
# sull'app: e' la STESSA misura dell'avvio. Qui vivevano `_CONFIG_PROVIDER_IDS`
# (i cinque id scritti una tredicesima volta), `_config_has_credential` (che
# per Claude API guardava l'ambiente OPPURE il runner costruito, e diceva di
# se' che la regola di Ollama andava «tenuta d'accordo a mano» con l'avvio) e
# `_credentials_of_the_five`: sono usciti col Task 9 della Tappa 7.


def _models_in_use(store: dict) -> dict[str, str]:
    """Il modello che il runtime userebbe ADESSO, per provider.

    Non «il modello configurato»: quello che il runner risolverebbe con
    `model="auto"` -- la scelta, letta dove la tabella dice che vive
    (`Provider.model_path`), oppure il modello automatico del provider
    (`Provider.auto_model`), che e' lo stesso che i runner leggono
    (`claude_runner.AUTO_MODEL_MAP`, `OpenAICompatRunner._resolve_model`,
    `OpenRouterRunner._resolve_model`). Il modello di Ollama non ha un
    automatico: senza una scelta la riga resta vuota, ed e' la verita'.

    La riga di `subscription` era la parte scomoda, ed è la cosa che la fetta
    «il modello del piano» ha tolto. Diceva: *il modello del ponte è un effetto
    collaterale del modello di Claude API*, e la pagina lo mostrava «perché è
    così, non perché ci piaccia». Era vero, ed era il difetto -- un campo solo
    per due economie opposte: su Claude API si paga a token e `haiku` è la
    scelta frugale, sul piano il modello non costa di più. Il proprietario si
    ritrovava il piano che aveva pagato a girare col modello scelto per non
    spendere sull'API.

    Adesso è un campo, `ponte.modello`, e questa funzione lo LEGGE. Lo stesso
    campo che il turno legge (`handlers_chat._enqueue_chat_job`), non lo stesso
    calcolo fatto due volte in due file: da due implementazioni della stessa
    regola a un valore letto da due posti.
    """
    return {p.id: chosen_model(p, store) or p.auto_model for p in all_providers()}


async def handle_get_models_config(request: web.Request) -> web.Response:
    data_dir = request.app.get("data_dir") or "/data"
    payload = load_models_config(data_dir)
    _bridge_on = payload["ponte"]["attivo"]
    # I fatti si misurano UNA volta e si passano a entrambe le composizioni:
    # due derivazioni degli stessi fatti nello stesso handler sarebbero la
    # miniatura del difetto che questa fetta chiude.
    _credentials = credentials_present(request.app)
    _models = _models_in_use(payload)
    # LA catena, una sola: quella che il router ha in mano adesso. Non si
    # riderivano i nomi da `payload["chain_order"]` (l'archivio) perché
    # l'archivio e il runtime possono differire fino al riavvio -- è la
    # scrittura a caldo, invariante 4, che il Task 10 chiude. Finché quel
    # divario esiste, la pagina deve descrivere il RUNTIME, e descriverlo in un
    # modo solo: la frase e il disegno della catena leggono la stessa lista.
    _chain = list(request.app.get("model_chain") or [])
    # I due tempi che l'utente ha scelto, letti UNA volta e DOVE LI LEGGE IL
    # RUNTIME -- che dal Task 10 è l'ARCHIVIO, non l'ambiente. Fino alla 2.4.1
    # venivano da `BRIDGE_DEADLINE_MIN` e `OLLAMA_REQUEST_TIMEOUT` perché era
    # lì che li leggevano `_enqueue_chat_job` e `OpenAICompatRunner.__init__`,
    # e la copia d'archivio (Task 6) non aveva lettori: due rappresentazioni
    # dello stesso numero nello stesso payload (invariante 1), che divergevano
    # appena qualcuno salvava da questa pagina. Adesso il numero è uno solo, e
    # questa lettura è la STESSA che il turno subisce: `_enqueue_chat_job`
    # legge `ponte.scadenza_min` e il runner locale riceve `ollama.timeout_s`
    # (via `apply_timeout`, rifatto a ogni salvataggio).
    #
    # I valori arrivano già riportati dentro gli estremi da `load_models_config`
    # (`_clamp_int`), quindi qui non si ripulisce una seconda volta.
    _bridge_deadline = payload["ponte"]["scadenza_min"]
    _ollama_timeout = payload[OLLAMA.id]["timeout_s"]
    payload["adesso"] = compose_now(
        chain=_chain,
        credentials=_credentials,
        models=_models,
        bridge_active=_bridge_on,
        # La STESSA lettura che `handlers_chat._enqueue_chat_job` fa a ogni
        # turno per scrivere la scadenza (`now + ponte.scadenza_min * 60`), e
        # lo STESSO numero che va ai connettori qui sotto: la frase in cima e
        # la riga sotto il piano non possono dire due minuti diversi.
        bridge_deadline_min=_bridge_deadline,
    )
    # La topologia: chi è in catena, in che ordine, e chi ne sta fuori. La
    # pagina RICEVE due liste già ordinate e non ne calcola nessuna --
    # invariante 2 della spec.
    payload["catena"], payload["fuori_catena"] = compose_topology(
        chain_order=_chain,
        credentials=_credentials,
        models=_models,
        bridge_active=_bridge_on,
        # Che cosa è successo DAVVERO, per provider (Task 11). Non una sonda:
        # `OccurrenceRegistry` è alimentato dal ciclo di ripiego del router, cioè
        # dal traffico vero. Sondare cinque provider a ogni apertura della
        # pagina costerebbe denaro e quota per un'informazione che scade
        # subito, e trasformerebbe questa pagina in una cosa che conviene non
        # aprire (progetto §11.2).
        #
        # Il `{}` non è un ripiego «comportati come prima»: è il registro di
        # una app che non ne ha uno (una fixture che non fa girare
        # `create_app`), e produce esattamente ciò che è vero in quel caso --
        # nessuna osservazione, e la pagina lo dice.
        occurrences=(request.app["occurrence_registry"].occurrences()
               if request.app.get("occurrence_registry") is not None else {}),
        # L'orologio di parete, letto QUI e passato: `model_resolution` è un
        # modulo di funzioni pure e non ne legge nessuno. È anche l'unico modo
        # in cui «3 min fa» è una cosa che si possa provare.
        now=time.time(),
        bridge_deadline_min=_bridge_deadline,
        ollama_timeout_s=_ollama_timeout,
    )
    # Cosa c'è dopo l'ultimo anello: una frase sulla catena, non su una riga.
    # Quale riga sia l'ultima cambia con un gesto, e la pagina riordina da sé
    # fra il gesto e la risposta del server -- attaccata a una riga, dopo un
    # riordino direbbe «ultimo della catena» di uno che non lo è più.
    payload["fine_catena"] = CHAIN_END if payload["catena"] else ""
    return web.json_response(payload)


async def handle_save_models_config(request: web.Request) -> web.Response:
    body = await json_object(request)
    data_dir = request.app.get("data_dir") or "/data"
    clean = save_models_config(data_dir, body)
    request.app["models_config"] = clean   # hot-update per la sessione corrente
    # E poi si RIMETTE IN VIGORE. Aggiornare solo il dizionario cambiava la
    # PAGINA e non il RUNTIME: la catena del router e il timeout del backend
    # locale si costruivano all'avvio, quindi un riordino salvato non toccava
    # il turno successivo e, alla ricarica, questa stessa rotta rimostrava
    # l'ordine vecchio (il GET descrive il runtime, che è la sola misura che
    # ha). Fino al Task 10 la pagina aveva una riga che lo confessava.
    #
    # `callable` e non un `try`: in una app costruita da una fixture, o in un
    # processo dove `_on_startup` non è girato, la funzione non c'è -- e non
    # esserci non è un errore da inghiottire, è l'assenza del runtime da
    # rimettere in vigore.
    recompute = request.app.get("recompute_chain")
    if callable(recompute):
        recompute()
    return web.json_response({"ok": True, **clean})


# Il filtro dei modelli gratuiti arriva come argomento a
# `_fetch_openrouter_models`, letto dall'archivio (`nascondi_gratuiti`): la
# variabile d'ambiente `HIRIS_HIDE_FREE_MODELS` non la legge piu' nessuno.

# Recent Claude models (Anthropic doesn't expose a public list-models endpoint)
#
# Task 9: la voce "auto" è USCITA da questa lista. Non era un modello: era la
# parola con cui il vecchio picker diceva «scegli tu», e salvarla come valore è
# un difetto -- `resolve_model("auto", "chat", "auto")` restituisce "auto" e la
# richiesta parte con `model="auto"` verso un provider che quel nome non lo
# conosce. Nell'archivio «auto» è la STRINGA VUOTA, e il pannello la offre come
# prima voce con la sua nota (`model_resolution.AUTO_NOTE`), che dice anche a
# quale modello si risolve oggi.
#
# La riserva di ciascun provider vive nella tabella (`Provider.reserve_models`):
# qui c'erano `_CLAUDE_MODELS`, `_OPENAI_FALLBACK` e `_OPENROUTER_PRESETS`.

# Pattern: keep only current-gen GPT + reasoning models, no legacy/instruct/embedding
_OPENAI_KEEP = re.compile(r"^(gpt-4[o.1]|o[1-9](-mini|-preview)?)")
_OPENAI_SKIP = re.compile(r"instruct|embed|vision|realtime|audio|transcribe|tts|whisper")


# ── Le tre letture, e la loro PROVENIENZA ─────────────────────────────────
#
# Ognuna restituisce `(models, source)`, dove `source` è "viva" (letta adesso
# dal provider) o "riserva" (elenco scritto nel sorgente). Non è un dettaglio
# di registrazione: cinque secondi di pazienza e, se falliscono, queste
# funzioni restituivano una lista scritta a mano DUE ANNI FA con un
# `logger.warning` e niente altro -- indistinguibile, a schermo, da una lista
# vera. Peggio: un provider con la chiave sbagliata compare lo stesso
# nell'elenco, perché la condizione è la PRESENZA della chiave, non la sua
# validità. Da qui si poteva stare davanti a un elenco che sembra vero, per un
# provider che non risponderebbe comunque. Il valore torna al chiamante e
# arriva fino al pannello, che lo dice con le parole di
# `model_resolution.provenance`.
async def _fetch_openai_models(api_key: str) -> tuple[list[str], str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get("https://api.openai.com/v1/models", headers=headers) as resp,
        ):
            if resp.status != 200:
                logger.warning("OpenAI models list returned %s", resp.status)
                return list(OPENAI.reserve_models), "riserva"
            data = await resp.json()
        models = [
            m["id"] for m in data.get("data", [])
            if _OPENAI_KEEP.match(m["id"]) and not _OPENAI_SKIP.search(m["id"])
        ]
        models.sort()
        # Una risposta 200 che non contiene NESSUN modello utilizzabile non è
        # una lettura riuscita: quello che si mostra viene dal sorgente, e si
        # dichiara per quello che è.
        return (models, "viva") if models else (list(OPENAI.reserve_models), "riserva")
    except Exception as exc:
        logger.warning("Could not fetch OpenAI models: %s", exc)
        return list(OPENAI.reserve_models), "riserva"


async def _fetch_claude_models(api_key: str) -> tuple[list[str], str]:
    """L'elenco dei modelli di Anthropic, letto adesso.

    Fino alla fetta «il modello del piano» questa lettura non esisteva, e il
    codice ne dichiarava la ragione: che Anthropic non avrebbe nessuna rotta
    pubblica di elenco. **E' FALSO**, verificato sulla documentazione ufficiale il
    15/08/2026: `GET /v1/models` c'è, paginato (`limit` 1-1000, predefinito
    20), ordinato dai più recenti, e ogni voce porta `id`, `display_name`,
    `created_at` e `capabilities`. `CLAUDE.reserve_models` resta come RISERVA -- tre
    nomi scritti a mano che invecchiano -- e da adesso si dichiara per quello
    che è invece di presentarsi come tutto ciò che esiste.

    Vuole una CHIAVE API: col token del piano non risponde. Per questo il
    chiamante non prova nemmeno, quando la chiave non c'è.

    `limit=100` su una pagina sola: il catalogo reale non ci arriva vicino, e
    seguire `has_more` sarebbe codice che non si può provare col vero.
    """
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session, session.get(
                "https://api.anthropic.com/v1/models?limit=100",
                headers=headers) as resp:
            if resp.status != 200:
                logger.warning("Anthropic models list returned %s", resp.status)
                return list(CLAUDE.reserve_models), "riserva"
            data = await resp.json()
        # NESSUNA CURATELA e nessun riordino: a differenza di OpenAI qui non
        # c'è rumore da filtrare (niente embedding, niente audio, niente
        # legacy-instruct), e l'ordine È un'informazione -- i più recenti per
        # primi, come li manda l'API. Riordinare nasconderebbe qual è il
        # modello nuovo.
        models = [m["id"] for m in data.get("data", []) if m.get("id")]
        # Una risposta 200 che non contiene nessun modello non è una lettura
        # riuscita: la stessa regola già scritta in `_fetch_openai_models`.
        return (models, "viva") if models else (list(CLAUDE.reserve_models), "riserva")
    except Exception as exc:
        logger.warning("Could not fetch Anthropic models: %s", exc)
        return list(CLAUDE.reserve_models), "riserva"


async def _fetch_ollama_models(local_model_url: str,
                               chosen_model: str) -> tuple[list[str], str]:
    """L'elenco di ciò che è SCARICATO su quella macchina, da `/api/tags`.

    Il ripiego è il modello scelto e basta: non è un catalogo di riserva, è
    «quello che so, e non ho potuto verificare che ci sia ancora». Quando
    nemmeno quello c'è, la lista è vuota -- ed è la verità, non un guasto.
    """
    from ..backends.ollama import _validate_ollama_url
    reserve = [chosen_model] if chosen_model else []
    try:
        _validate_ollama_url(local_model_url)
    except ValueError as exc:
        logger.warning("Invalid local_model_url for Ollama listing: %s", exc)
        return reserve, "riserva"
    base = local_model_url.rstrip("/")
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(f"{base}/api/tags") as resp,
        ):
            if resp.status != 200:
                logger.warning("Ollama /api/tags returned %s", resp.status)
                return reserve, "riserva"
            data = await resp.json()
        return [m["name"] for m in data.get("models", [])], "viva"
    except Exception as exc:
        logger.warning("Could not fetch Ollama models: %s", exc)
        return reserve, "riserva"


# La riserva di OpenRouter (`OPENROUTER.reserve_models`) e' cio' che si mostra
# quando openrouter.ai non risponde, e soltanto quello: il filtro dell'elenco
# vivo e' `_supports_tools`, che porta tutti i modelli utilizzabili. Tutte le
# voci DEVONO saper usare gli strumenti -- HIRIS manda sempre il catalogo delle
# azioni, e un modello che non lo sa fare risponde 404 «No endpoints found
# that support tool use» (hermes-3-llama-3.1-405b:free, tolto nella v0.9.8).


def _supports_tools(entry: dict) -> bool:
    """Return True if an OpenRouter model entry advertises tool/function support.

    OpenRouter exposes per-model capability via the ``supported_parameters``
    array. Models without ``tools`` (or the legacy ``function_calling``) in
    that list will reject any HIRIS chat request with HTTP 404
    ``"No endpoints found that support tool use"`` — exactly the failure
    mode reported on hermes-3-llama-3.1-405b:free. We hide them at list
    time so users can't accidentally pick them.
    """
    params = entry.get("supported_parameters") or []
    if not isinstance(params, list):
        return False
    params_set = {str(p).lower() for p in params}
    return "tools" in params_set or "function_calling" in params_set


async def _fetch_openrouter_models(api_key: str,
                                   hide_free_models: bool = False,
                                   ) -> tuple[list[str], str]:
    """Fetch the full OpenRouter model list and filter to a usable, tool-capable subset.

    Falls back to OPENROUTER.reserve_models (best-effort, may include tool-incapable
    models) only if the live capability check cannot be performed.

    `hide_free_models` arriva dall'ARCHIVIO (`models_config["nascondi_gratuiti"]`),
    non dall'ambiente: è la casella che sta sotto l'elenco che filtra, e deve
    agire sulla lista che l'utente sta guardando nello stesso istante in cui la
    spunta. Sul ramo di RISERVA non ha effetto -- i preset tornano non filtrati
    -- ed è un difetto gemello che si DICHIARA invece di correggerlo: filtrarli
    qui renderebbe la riserva una lista diversa da quella scritta nel sorgente,
    cioè una terza cosa. Lo dice il pannello, nella riga di provenienza.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get("https://openrouter.ai/api/v1/models", headers=headers) as resp,
        ):
            if resp.status != 200:
                logger.warning("OpenRouter models list returned %s", resp.status)
                return list(OPENROUTER.reserve_models), "riserva"
            data = await resp.json()

        # Build live capability index. Tool support is required because every
        # HIRIS agent ships with the standard tool schema in the chat request;
        # picking a non-tool-capable model produces immediate API errors.
        tool_capable_ids: set[str] = set()
        for entry in data.get("data", []):
            mid = entry.get("id")
            if mid and _supports_tools(entry):
                tool_capable_ids.add(mid)

        if not tool_capable_ids:
            # OpenRouter response shape changed or capability data missing —
            # don't silently degrade to a list users cannot use; return
            # presets and let runtime errors surface.
            logger.warning(
                "OpenRouter returned no tool-capable models (capability "
                "field missing?). Falling back to presets."
            )
            return list(OPENROUTER.reserve_models), "riserva"

        hide_free = bool(hide_free_models)

        # TUTTI i modelli utilizzabili, non un sottoinsieme curato a mano.
        #
        # Fino al 22/08/2026 qui si partiva dalla riserva -- undici
        # nomi scritti nel sorgente -- e si teneva solo l'intersezione con
        # quelli capaci di usare gli strumenti. Misurato sull'installazione del
        # proprietario: OpenRouter pubblicava 421 modelli, 352 capaci, e HIRIS
        # gliene mostrava QUATTRO, perche' SETTE degli undici erano stati nel
        # frattempo ritirati o rinominati. Non era il suo account: era una
        # lista scritta a mano che aveva marcito in silenzio -- lo stesso
        # difetto di `pricing.py`, che non conosce nessun id OpenRouter e per
        # questo il costo usciva zero.
        #
        # Il filtro sulle capacita' RESTA, ed e' l'unico che serva: HIRIS manda
        # sempre il catalogo delle azioni, e un modello che non sa usarle
        # rifiuta ogni richiesta con un 404. Ma escludere i 69 incapaci non
        # significa mostrarne quattro.
        #
        # La pagina Modelli era gia' fatta per un elenco lungo: ha un filtro di
        # ricerca e la voce «scritto da te» per un identificatore che l'elenco
        # non ha. La lista corta era l'anomalia, non il vincolo.
        #
        # Ordinato: due letture uguali devono disegnare la stessa pagina.
        result = sorted(
            f"openrouter:{mid}" for mid in tool_capable_ids
            if not (hide_free and mid.endswith(":free"))
        )
        return (result, "viva") if result else (list(OPENROUTER.reserve_models), "riserva")
    except Exception as exc:
        logger.warning("Could not fetch OpenRouter models: %s", exc)
        return list(OPENROUTER.reserve_models), "riserva"


async def handle_list_models(request: web.Request) -> web.Response:
    """L'elenco dei modelli, per il pannello che li fa scegliere.

    Non è più «lo stato dei provider»: quello lo dice `/api/models/config`, in
    due liste. Qui c'è una cosa sola -- che cosa si può scegliere per un
    provider, da dove viene l'elenco, e dove va scritta la scelta -- e si
    chiede UN provider alla volta (`?provider=<id>`), quando il pannello si
    apre. Prima l'intero elenco veniva letto al caricamento della pagina, che
    significava interrogare davvero OpenAI, OpenRouter e Ollama, cinque secondi
    di pazienza ciascuno, per un risultato che nessuno guardava (il picker era
    uscito col Task 8). E «letti adesso» diventa vero: senza la lettura pigra
    sarebbe «letti quando hai aperto la pagina», che è una parola più larga del
    fatto.

    Senza `?provider=` risponde per tutti, come prima: è la forma che un
    client diverso dalla pagina (uno script) si aspetterebbe, e una rotta che
    cambia significato in silenzio è la cosa che questa fetta ritira. Oggi
    quel client non esiste — misurato l'01/09, vedi `save_models_config`.
    """
    requested = request.query.get("provider", "")
    store = load_models_config(request.app.get("data_dir") or "/data")
    hide_free = bool(store["nascondi_gratuiti"])
    # Gli stessi modelli che la riga mostra, dalla stessa funzione: il pannello
    # e la riga da cui si apre non possono dire due cose diverse.
    in_use = _models_in_use(store)
    credentials = credentials_present(request.app)
    claude_key = request.app.get("claude_api_key", "")
    openai_key = request.app.get("openai_api_key", "")
    openrouter_key = request.app.get("openrouter_api_key", "")
    local_url = request.app.get("local_model_url", "")

    async def read(pid: str) -> tuple[list[str], str, str, str]:
        """`(values, source, chosen, auto_resolved)` per un provider.

        La fonte "assente" non è un errore: è «non c'è nessun elenco da
        leggere, e il perché è la credenziale». Serve perché un pannello che si
        apre deve SEMPRE dare una risposta -- nascondere è comodo per chi
        capisce e crudele per chi non capisce perché una cosa è sparita -- e la
        risposta la scrive `model_resolution`, non questa pagina.
        """
        p = provider_of(pid)
        chosen = chosen_model(p, store)
        if pid == SUBSCRIPTION.id:
            # Tre alias, sempre gli stessi: non si leggono da nessuna parte
            # perché non c'è niente da leggere. `cli_model` ne produce
            # esattamente tre. Senza il token il piano non risponde e non c'è
            # niente da scegliere: la riga lo dice già, e il pannello lo ridice
            # con la stessa parola invece di offrire tre voci inerti.
            if not credentials[pid]:
                return [], "assente", "", ""
            return [], "fissa", in_use[pid], ""
        if not credentials[pid]:
            return [], "assente", chosen, ""
        if pid == CLAUDE.id:
            # Uguale a OpenAI e a OpenRouter dalla fetta «il modello del
            # piano». Qui il ramo era diverso in DUE modi, e tutti e due sono
            # usciti: l'elenco non si leggeva mai (il codice dichiarava
            # inesistente la rotta di elenco di Anthropic -- falso,
            # `GET /v1/models` esiste) e c'era anche SENZA chiave. La seconda
            # eccezione aveva una ragione
            # scritta -- su un'installazione col solo Piano Claude Max questo
            # era l'unico posto da cui si sceglieva il modello del piano -- e
            # quella ragione è morta col campo `ponte.modello`.
            #
            # PERDITA DICHIARATA: senza chiave non si sfogliano più i modelli
            # di Claude API. Erano voci inerti (senza chiave quel provider non
            # entra in catena), ma è una capacità che c'era.
            values, source = await _fetch_claude_models(claude_key)
            return values, source, chosen, in_use[pid]
        if pid == OPENAI.id:
            values, source = await _fetch_openai_models(openai_key)
            return values, source, chosen, in_use[pid]
        if pid == OPENROUTER.id:
            values, source = await _fetch_openrouter_models(
                openrouter_key, hide_free_models=hide_free)
            return values, source, chosen, in_use[pid]
        # Ollama. Nessuna voce «auto»: il runner locale usa SEMPRE il modello
        # scelto (`local=True` fa vincere `_chosen_model()` su ogni altro
        # ramo di `_resolve_model`),
        # perché quell'istanza ne ha scaricato uno solo e chiedergliene un
        # altro fallirebbe.
        if pid == OLLAMA.id:
            values, source = await _fetch_ollama_models(local_url, chosen)
            return values, source, chosen, ""
        # Un provider della tabella che questa rotta non sa ancora leggere:
        # si dichiara la sua riserva, per quello che e'.
        return list(p.reserve_models), "riserva", chosen, in_use[pid]

    providers: list[dict] = []
    for pid in (p.id for p in all_providers()):
        if requested and requested != pid:
            continue
        values, source, chosen, auto = await read(pid)
        # LA REGOLA, in una riga: chi viene CHIESTO riceve sempre una risposta;
        # senza una richiesta compaiono solo quelli per cui un elenco esiste.
        # Un pannello che si apre su una riga e non dice niente sarebbe la
        # forma piccola del difetto che questa fetta chiude.
        if not requested and source == "assente":
            continue
        providers.append(compose_panel(
            provider_id=pid, values=values, source=source, chosen=chosen,
            auto_resolved=auto, address=local_url, hide_free_models=hide_free,
        ))

    return web.json_response({"providers": providers})
