"""L'archivio dei modelli: `models_config.json`, le decisioni della pagina Modelli.

Viveva in `api/handlers_models.py` fino al Task 10 della Tappa 7 (F-13): lo
strato delle rotte ospitava lo schema e il file, e `steering.py` -- il nucleo
-- importava da un gestore HTTP.
"""
from __future__ import annotations

import json
import logging
import os

from .providers import DEFAULT_PRESET, OLLAMA, all_providers, chain_members
from .storage import write_json_atomic

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
# Sono due migrazioni diverse, e un archivio puo' trovarsi a meta': per questo
# ognuna ha il suo segno. `seminato`, il segno della semina delle OPZIONI
# (uscita il 02/10/2026), e' uscito anche da qui col Task 10 della Tappa 7
# (M-80): nessuno lo scriveva ne' lo leggeva, e la rotta lo mostrava ancora.
# Un archivio che lo porta lo tiene sul disco (la scrittura e'
# lettura-modifica-scrittura), ma la rotta non lo dice piu'.
#
# Il valore sopravvive comunque a ogni PUT: `_store_keys` lo ricava da
# `base`, che parte dal contenuto GIA' SU DISCO. Solo l'avvio li scrive, con
# `flags=True` (`options_migration.seed_at_startup`).
_MIGRATION_FLAGS = ("catena_seminata", "piano_seminato")


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
    from .agent.runner import cli_model
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
        # I segni delle semine, uno per migrazione: vedi `_MIGRATION_FLAGS`,
        # da cui si leggono i nomi.
        **{flag: bool(raw.get(flag, False)) for flag in _MIGRATION_FLAGS},
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
    """`flags=True` e' riservato all'avvio (`options_migration.seed_at_startup`):
    e' l'unico momento in cui i segni delle semine si scrivono. Ogni altro
    chiamante -- la PUT, e quindi la pagina -- li lascia dove sono: vedi
    `_MIGRATION_FLAGS`."""
    if not isinstance(data, dict):
        data = {}
    path = _models_config_path(data_dir)
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
    write_json_atomic(path, disk_data)
    return clean
