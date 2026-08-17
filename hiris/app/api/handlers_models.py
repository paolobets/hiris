from __future__ import annotations
import json
import logging
import os
import re
import time

import aiohttp
from aiohttp import web

from ..migrazione_opzioni import _PREDEFINITI as _PREDEFINITI_SEMINA
from ..decisione_modelli import (FINE_CATENA, componi_adesso, componi_pannello,
                                 piano_ha_il_token,
                                 componi_topologia)

logger = logging.getLogger(__name__)

# SP-2 Task 4: models-config store (chain_order), see §8 code map.
# brain_model e' uscito alla fetta E5 Task 7 ("Consumi e Modelli smettono di
# mentire"): il Brain che lo leggeva e' uscito con la E3, zero lettori di
# produzione da allora. Non e' un'opzione dell'add-on (vive solo in
# models_config.json), quindi esce dai tre posti reali -- lettore e
# scrittore qui sotto, UI in config/models-route.js -- nello stesso commit.
_VALID_BACKENDS = ("claude", "openai", "openrouter", "ollama")

# SP-2 Task 5C: per-provider DEFAULT model, e.g. {"claude": "claude-opus-4-7"}.
# Empty string ("") = auto (fall back to AUTO_MODEL_MAP). Ollama excluded — it
# always uses its fixed `local_model.model`.
_PROVIDER_MODEL_KEYS = ("claude", "openai", "openrouter")


def _clean_provider_models(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for k in _PROVIDER_MODEL_KEYS:
        v = raw.get(k, "")
        out[k] = v if isinstance(v, str) else ""
    return out


# Task 6 -- versione A della migrazione. Le decisioni che escono da config.yaml
# e vengono a vivere qui (fetta «la catena diventa l'unica verita'»). Un
# dizionario di predefiniti, non cinque costanti sparse: `load` e `save`
# leggono la stessa struttura, e un campo aggiunto qui non puo' dimenticarsi in
# uno dei due.
_PREDEFINITI_ARCHIVIO = {
    # `modello`: il modello del piano, che dalla fetta «il modello del piano»
    # e' un valore SUO e non piu' un effetto di `provider_models["claude"]`.
    # Il predefinito e' `"sonnet"` e NON la stringa vuota: vuoto
    # significherebbe «non so», e «non so» e' la forma con cui la regola «se
    # non so niente allora comportati come prima» e' gia' rientrata quattro
    # volte in questo prodotto, da quattro porte diverse. Il campo nasce con un
    # valore, e la semina (`migrazione_opzioni.semina_modello_del_piano`) lo
    # sostituisce una volta sola con quello che l'installazione stava gia'
    # usando.
    # I numeri vengono da `migrazione_opzioni._PREDEFINITI`, non ridigitati:
    # erano gli stessi valori in due moduli (piu' due volte dentro l'altro), ed
    # e' la struttura che ha gia' prodotto il debito F. `modello` e' l'UNICO
    # campo in piu' -- la semina lo tratta a parte
    # (`semina_modello_del_piano`), quindi non sta nell'altro elenco: la
    # differenza e' voluta, e adesso e' l'unica.
    "ponte": {**_PREDEFINITI_SEMINA["ponte"], "modello": "sonnet"},
    "ollama": dict(_PREDEFINITI_SEMINA["ollama"]),
}

# Le sole chiavi che un CLIENT puo' scrivere: le sei decisioni della pagina
# Modelli. Tutto il resto che sta sul disco (a partire da 'brain_model')
# sopravvive intatto -- vedi la lettura-modifica-scrittura in
# save_models_config.
_CHIAVI_NOSTRE = (
    "chain_order", "provider_models", "ponte", "ollama",
    "nascondi_gratuiti", "strategia_ultima",
)

# I SEGNI DELLA MIGRAZIONE, che non sono decisioni e non viaggiano in una PUT.
# `seminato` dice che le opzioni dell'add-on sono gia' state copiate;
# `catena_seminata` che la catena e' gia' stata copiata dalla vecchia regola.
# Stavano in `_CHIAVI_NOSTRE` e ne sono usciti: un client che rimandasse
# `seminato: false` -- la pagina lo faceva, con lo `state.cfg` di default, dopo
# un GET fallito; un gateway MCP con uno snapshot stale lo farebbe ancora --
# farebbe RIGIRARE la semina al riavvio successivo, e dopo la versione B, con
# l'ambiente muto, ricopierebbe i predefiniti sopra le decisioni dell'utente.
# Cioe' la perdita silenziosa che le due versioni della migrazione esistono per
# evitare, innescata da un click.
#
# Il valore sopravvive comunque a ogni PUT: `_chiavi_archivio` lo ricava da
# `base`, che parte dal contenuto GIA' SU DISCO. Solo l'avvio li scrive, con
# `segni=True`.
_SEGNI_MIGRAZIONE = ("seminato", "catena_seminata", "piano_seminato")


def _clamp_int(valore, predefinito: int, minimo: int, massimo: int) -> int:
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
        n = int(valore)
    except (TypeError, ValueError):
        return predefinito
    return max(minimo, min(massimo, n))


def _pulisci_modello_del_piano(valore, predefinito: str) -> str:
    """Uno dei tre alias, sempre. Si RIPORTA DENTRO come i due `_clamp_int`
    accanto: un valore fuori dall'insieme non e' un corpo malformato.

    Il riduttore e' `agent.runner.modello_cli`, che qui trova il suo UNICO
    chiamante rimasto. Fino alla fetta «il modello del piano» ne aveva due --
    il turno del ponte (`handlers_chat._enqueue_chat_job`) e la riga della
    pagina (`_modelli_in_uso`) -- che erano lo stesso calcolo fatto in due
    file, cioe' due implementazioni della stessa regola libere di divergere.
    Adesso traduce una volta sola, all'INGRESSO del campo: cio' che sta
    nell'archivio e' gia' un alias, e chi legge non ha niente da tradurre.

    L'import e' DIFFERITO per la ragione misurata in `agent/runner.py:122-131`:
    `api/handlers_chat.py` importa da quel modulo e `api/handlers_mcp.py`
    importa `handlers_chat`; un import in cima chiude il cerchio e rompe
    l'avvio con `ImportError ... partially initialized module`.
    """
    from ..agent.runner import modello_cli
    if not isinstance(valore, str) or not valore.strip():
        return predefinito
    return modello_cli(valore)


def _pulisci_ponte(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    d = _PREDEFINITI_ARCHIVIO["ponte"]
    return {
        "attivo": bool(raw.get("attivo", d["attivo"])),
        "scadenza_min": _clamp_int(raw.get("scadenza_min"), d["scadenza_min"], 1, 120),
        "tetto_giornaliero": _clamp_int(
            raw.get("tetto_giornaliero"), d["tetto_giornaliero"], 0, 1000),
        "modello": _pulisci_modello_del_piano(raw.get("modello"), d["modello"]),
    }


def _pulisci_ollama(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    d = _PREDEFINITI_ARCHIVIO["ollama"]
    modello = raw.get("modello", d["modello"])
    return {
        "modello": modello if isinstance(modello, str) else "",
        "timeout_s": _clamp_int(raw.get("timeout_s"), d["timeout_s"], 10, 1800),
    }


def _chiavi_archivio(raw: dict) -> dict:
    """Le cinque chiavi nuove, pulite. Usata da `load` e da `save`: un solo
    posto in cui la forma e' definita."""
    strategia = raw.get("strategia_ultima")
    return {
        "ponte": _pulisci_ponte(raw.get("ponte")),
        "ollama": _pulisci_ollama(raw.get("ollama")),
        "nascondi_gratuiti": bool(raw.get("nascondi_gratuiti", False)),
        # Debito F del Task 6, chiuso qui: il predefinito del campo e' quello
        # dell'opzione da cui viene (`llm_strategy: "balanced"` in
        # config.yaml). Valeva "", e la differenza faceva contare come
        # «copiato» un valore che nessuno aveva scelto -- vedi
        # `migrazione_opzioni._PREDEFINITI`.
        "strategia_ultima": strategia if isinstance(strategia, str) else "balanced",
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
        # gli altri vive fuori da `_CHIAVI_NOSTRE`: un client che lo rimandasse
        # a `false` farebbe rigirare la semina al riavvio successivo, e la
        # semina ricopre `ponte.modello` -- cioe' la scelta dell'utente.
        "piano_seminato": bool(raw.get("piano_seminato", False)),
    }


def _models_config_path(data_dir: str) -> str:
    return os.path.join(data_dir, "models_config.json")


def _metti_da_parte_l_archivio_illeggibile(path: str) -> None:
    """Rinomina in `.corrotto` invece di lasciarlo sovrascrivere.

    `save_models_config` fa lettura-modifica-scrittura partendo dal disco: se
    il disco non si legge riparte da `{}` e al primo salvataggio -- che
    dall'avvio arriva da solo, con la semina -- i byte di prima sono persi per
    sempre. Un byte di disco contro dodici decisioni.

    Il piu' VECCHIO `.corrotto` non si sovrascrive: e' quello scritto quando il
    file era ancora quello dell'utente. Un secondo guasto salverebbe sopra di
    lui l'archivio dei predefiniti gia' riscritto, cioe' niente.
    """
    guasto = path + ".corrotto"
    try:
        if os.path.exists(guasto):
            logger.error(
                "%s esiste gia' e non viene sovrascritto: contiene la copia "
                "piu' vecchia, cioe' l'unica che puo' ancora avere i tuoi "
                "valori. Il file illeggibile di adesso resta dov'e'.", guasto)
            return
        os.replace(path, guasto)
        logger.error(
            "Il file illeggibile e' stato messo da parte in %s invece di essere "
            "sovrascritto: da li' si possono ancora recuperare a mano i valori "
            "che conteneva.", guasto)
    except OSError as errore:
        logger.error(
            "Non si e' potuto mettere da parte %s (%s): il prossimo salvataggio "
            "lo sovrascrivera'.", path, errore)


def _leggi_archivio_grezzo(path: str) -> dict:
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
            grezzo = json.load(fh)
    except FileNotFoundError:
        return {}
    except Exception as errore:
        logger.error(
            "%s non si e' potuto leggere (%s: %s). HIRIS riparte dai predefiniti: "
            "catena, ponte, Ollama, filtro dei gratuiti e preset che avevi "
            "scelto NON sono stati letti. Da questa versione questo file e' "
            "l'unica copia di quelle decisioni.",
            path, type(errore).__name__, errore)
        _metti_da_parte_l_archivio_illeggibile(path)
        return {}
    if not isinstance(grezzo, dict):
        logger.error(
            "%s contiene %s invece di un oggetto JSON. HIRIS riparte dai "
            "predefiniti: le decisioni che conteneva NON sono state lette.",
            path, type(grezzo).__name__)
        _metti_da_parte_l_archivio_illeggibile(path)
        return {}
    return grezzo


def load_models_config(data_dir: str) -> dict:
    raw = _leggi_archivio_grezzo(_models_config_path(data_dir))
    raw_chain = raw.get("chain_order", [])
    if not isinstance(raw_chain, list):
        raw_chain = []
    chain = [n for n in raw_chain if n in _VALID_BACKENDS]
    # fetta E5 Task 7: un models_config.json scritto da una versione
    # precedente puo' avere 'brain_model' popolato -- non viene ne' migrato
    # ne' cancellato (mai dati utente rimossi silenziosamente), ma il
    # silenzio si dichiara: stessa disciplina di
    # tests/test_startup_legacy_db_silence.py e dello stesso identico
    # precedente in claude_runner._load_usage per 'per_agent' di usage.json
    # (tests/test_claude_runner.py:721-780). save_models_config (sotto) fa
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
        "provider_models": _clean_provider_models(raw.get("provider_models")),
        **_chiavi_archivio(raw),
    }


def save_models_config(data_dir: str, data: dict, *, segni: bool = False) -> dict:
    """`segni=True` e' riservato all'avvio (`server._on_startup`): e' l'unico
    momento in cui `seminato`/`catena_seminata` si scrivono. Ogni altro
    chiamante -- la PUT, e quindi la pagina e il gateway MCP -- li lascia dove
    sono: vedi `_SEGNI_MIGRAZIONE`."""
    if not isinstance(data, dict):
        data = {}
    path = _models_config_path(data_dir)
    tmp = path + ".tmp"
    # Lettura-modifica-scrittura (stesso fix di claude_runner._save_usage per
    # 'per_agent'): senza questo, il PRIMO salvataggio dopo un upgrade
    # cancellerebbe silenziosamente un 'brain_model' legacy dal disco -- il
    # contrario di quanto dichiara il log in load_models_config ("non piu'
    # letto ne' scritto", che un operatore legge come "e' ancora li'"). Solo
    # le chiavi che questa versione possiede (_CHIAVI_NOSTRE) vengono
    # aggiornate; qualunque altra chiave gia' sul disco (incl. 'brain_model')
    # resta intatta.
    # Stessa lettura di `load_models_config`, e quindi stessa regola quando il
    # file non si legge: lo dice e lo mette da parte. Qui vale ancora di piu',
    # perche' e' la riga DOPO che sovrascrive.
    disk_data = _leggi_archivio_grezzo(path)
    # Task 6: la fusione parte dal CONTENUTO GIA' SU DISCO, non dai
    # predefiniti -- ed e' la STESSA ragione del fix di claude_runner._save_usage
    # per 'per_agent'. Da quando le chiavi scritte sono sette invece di due, un
    # corpo parziale (`{"chain_order": [...]}`) ricostruito sui predefiniti
    # azzererebbe ponte, Ollama e nascondi_gratuiti: una perdita di
    # configurazione silenziosa, cioe' esattamente cio' che la versione A
    # esiste per impedire. Il contratto della PUT e' «sempre l'oggetto intero»
    # e la pagina lo rispetta, ma un client diverso esiste (il gateway MCP).
    scrivibili = _CHIAVI_NOSTRE + (_SEGNI_MIGRAZIONE if segni else ())
    base = dict(disk_data)
    base.update({k: v for k, v in data.items() if k in scrivibili})
    raw_chain = base.get("chain_order", [])
    if not isinstance(raw_chain, list):
        # Una chain_order non-lista (null, un numero) non e' un 500: si azzera,
        # come faceva la guardia che stava qui prima della fusione.
        raw_chain = []
    clean = {
        "chain_order": [n for n in raw_chain if n in _VALID_BACKENDS],
        "provider_models": _clean_provider_models(base.get("provider_models")),
        **_chiavi_archivio(base),
    }
    disk_data.update(clean)
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(disk_data, fh)
    os.replace(tmp, path)
    return clean



# I cinque id del prodotto (subscription/claude/openai/openrouter/ollama),
# distinti dagli id di `handle_list_models` ("anthropic" per storia
# dell'endpoint): sono le cinque righe di cui questa rotta misura la
# credenziale.
#
# fetta «la catena diventa l'unica verità»: il campo "toggle" è uscito insieme
# a `_TOGGLE_ENV_VARS` e `_config_raw_toggle`. Leggevano i cinque interruttori
# `provider_*` dall'ambiente, e gli interruttori non decidono più niente: lo
# stato di un provider è l'appartenenza alla catena più la credenziale, e sono
# due fatti diversi che non collassano l'uno nell'altro. Il Task 13 toglierà le
# opzioni da `config.yaml`; qui smettono di essere LETTE, che è la condizione
# per poterle togliere.
#
# Task 8: accanto viveva `_CONFIG_PROVIDERS`, le stesse cinque voci con la
# label, per il payload `providers[]`. Le label le compone `decisione_modelli`
# per le due liste vere (`catena`/`fuori_catena`), e un secondo elenco di nomi
# non serviva più a nessuno.
_CONFIG_PROVIDER_IDS = ("subscription", "claude", "openai", "openrouter", "ollama")


def _config_has_credential(request: web.Request, provider_id: str) -> bool:
    """Boolean-only credential presence check — NEVER return the secret value."""
    if provider_id == "subscription":
        return piano_ha_il_token()
    if provider_id == "claude":
        if os.environ.get("CLAUDE_API_KEY", "").strip():
            return True
        return request.app.get("claude_runner") is not None
    if provider_id == "openai":
        return bool(request.app.get("openai_api_key"))
    if provider_id == "openrouter":
        return bool(request.app.get("openrouter_api_key"))
    if provider_id == "ollama":
        # fetta «la catena diventa l'unica verità»: la credenziale di Ollama è
        # il SOLO indirizzo, come in `server._credenziali`. Il nome del modello
        # è una decisione, non una credenziale, e da questa fetta vive
        # nell'archivio. Due definizioni della stessa credenziale, una qui e
        # una nell'avvio, sarebbero la seconda rappresentazione in miniatura.
        return bool(request.app.get("local_model_url"))
    return False


def _credenziali_dei_cinque(request: web.Request) -> dict[str, bool]:
    """I cinque fatti di credenziale, misurati UNA volta per richiesta.

    Task 8: qui viveva `_build_config_providers`, che componeva il payload
    storico `providers[]` -- `{id, label, in_catena, has_credential}` per tutti
    e cinque. Il Task 7 l'aveva tenuto in vita con una data di scadenza scritta
    nel docstring («finché il Task 8 non riscrive la pagina»), ed è oggi:
    `in_catena` era l'APPARTENENZA ALLA CATENA detta una seconda volta, accanto
    a `catena`/`fuori_catena` che la dicono per esteso. Due rappresentazioni
    della stessa cosa nello stesso payload sono la miniatura del difetto che
    questa fetta chiude, e l'unico lettore di quella seconda copia era la
    pagina, che adesso disegna la prima.

    Resta il fatto grezzo, che non è una rappresentazione dello stato ma la sua
    misura, e serve a `componi_adesso` e a `componi_topologia`: entrambe la
    ricevono dallo stesso dizionario, perché due misure degli stessi fatti
    nello stesso handler sarebbero lo stesso difetto un piano più sotto.
    """
    return {pid: _config_has_credential(request, pid)
            for pid in _CONFIG_PROVIDER_IDS}


def _modelli_in_uso(provider_models: dict, modello_ollama: str,
                    modello_piano: str) -> dict[str, str]:
    """Il modello che il runtime userebbe ADESSO, per provider.

    Non «il modello configurato»: quello che il runner risolverebbe con
    `model="auto"`. Sono i due rami veri --
    `claude_runner.resolve_model` (default per-provider, altrimenti
    AUTO_MODEL_MAP["chat"]) e `OpenAICompatRunner._resolve_model` (idem, con
    la sua mappa) -- letti qui invece di essere reinventati.

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
    regola a un valore letto da due posti. Il chiamante lo passa, come già fa
    per il modello di Ollama e per la stessa ragione -- ha una casa sola, e
    questa funzione non va a cercarsela.
    """
    from ..backends.openai_compat_runner import AUTO_MODEL_MAP as _AUTO_COMPAT
    from ..backends.openrouter_runner import AUTO_OPENROUTER
    from ..claude_runner import resolve_model

    claude = resolve_model("auto", "chat", provider_models.get("claude", ""))
    return {
        "subscription": modello_piano,
        "claude": claude,
        "openai": provider_models.get("openai", "") or _AUTO_COMPAT["chat"],
        # `OpenRouterRunner._resolve_model` NON usa `AUTO_MODEL_MAP` (è la
        # mappa di OpenAI: su OpenRouter `gpt-4o` non è nemmeno un nome
        # valido). Fino a questa fetta la riga di OpenRouter mostrava `gpt-4o`
        # a chiunque non avesse scelto un modello -- un identificatore preciso,
        # e falso.
        "openrouter": provider_models.get("openrouter", "") or AUTO_OPENROUTER,
        # Il modello di Ollama ha UNA SOLA CASA, `models_config["ollama"]
        # ["modello"]`, e il chiamante la legge da lì. Fino a questa fetta
        # veniva da `app["local_model_name"]`, cioè da `LOCAL_MODEL_NAME`:
        # dopo il Task 6 quello slot era una COPIA dell'archivio, ferma al
        # momento dell'avvio, e una copia che non si aggiorna a una PUT è la
        # seconda rappresentazione da cui questa fetta esiste per liberarsi.
        "ollama": modello_ollama,
    }


async def handle_get_models_config(request: web.Request) -> web.Response:
    data_dir = request.app.get("data_dir") or "/data"
    payload = load_models_config(data_dir)
    # Task 8: qui stava `payload["llm_strategy"]`, l'ultimo residuo
    # dell'invariante 1 in questo handler. Era il preset LETTO DALL'AMBIENTE
    # accanto a `strategia_ultima` letto dall'archivio -- la stessa cosa detta
    # due volte da due sorgenti che possono divergere -- e il suo unico lettore
    # era la riga «Preset corrente: …» di una pagina che presentava un ordine
    # come uno stato. Dalla fetta «la catena è l'unica verità» le tre strategie
    # sono tre GESTI che riscrivono la catena, non uno stato da cui la catena si
    # deriva: non c'è più un preset corrente da dichiarare, e quindi non c'è più
    # niente da leggere. `LLM_STRATEGY` resta letta da `server.py` per costruire
    # il router (l'opzione esce con il Task 13); qui smette di essere pubblicata.
    #
    # Task 9: escono anche gli ultimi due passeggeri senza lettori.
    # `embeddings` (`MEMORY_EMBEDDING_PROVIDER`/`_MODEL`) alimentava la sezione
    # «03 Embeddings», uscita col Task 8: la pagina dichiara che nessun testo
    # viene vettorizzato e NON mostra più i due valori, quindi pubblicarli era
    # una lettura che nessuno faceva. Le due variabili restano lette da
    # `server.py`, dove decidono qualcosa.
    # `ollama_model` era `app["local_model_name"]` accanto a
    # `payload["ollama"]["modello"]`: la stessa cosa detta due volte, e la
    # copia era pure ferma all'avvio. Era l'ultimo residuo dell'invariante 1 in
    # questo handler, dichiarato dal Task 7 e assegnato al Task 9.
    #
    # Versione B (3.0.0): esce anche `ponte_attivo`, l'ULTIMO residuo
    # dell'invariante 1 di tutto il payload. Era `app["ponte_attivo"]`, cioe'
    # `BRIDGE_ENABLED or _sub_first_class`, pubblicato ACCANTO a
    # `payload["ponte"]["attivo"]`: non un doppione esatto -- il valore vero
    # poteva essere `true` con l'archivio a `false`, e la pagina riceveva due
    # risposte alla stessa domanda. Tolta l'implicazione in `server.py`, il
    # secondo valore e' il primo: qui ne resta uno, `ponte["attivo"]`, e la
    # pagina lo legge di li'.
    _ponte_acceso = payload["ponte"]["attivo"]
    # I fatti si misurano UNA volta e si passano a entrambe le composizioni:
    # due derivazioni degli stessi fatti nello stesso handler sarebbero la
    # miniatura del difetto che questa fetta chiude.
    _credenziali = _credenziali_dei_cinque(request)
    _modelli = _modelli_in_uso(payload["provider_models"],
                               payload["ollama"]["modello"],
                               payload["ponte"]["modello"])
    # LA catena, una sola: quella che il router ha in mano adesso. Non si
    # riderivano i nomi da `payload["chain_order"]` (l'archivio) perché
    # l'archivio e il runtime possono differire fino al riavvio -- è la
    # scrittura a caldo, invariante 4, che il Task 10 chiude. Finché quel
    # divario esiste, la pagina deve descrivere il RUNTIME, e descriverlo in un
    # modo solo: la frase e il disegno della catena leggono la stessa lista.
    _catena = list(request.app.get("catena_modelli") or [])
    # I due tempi che l'utente ha scelto, letti UNA volta e DOVE LI LEGGE IL
    # RUNTIME -- che dal Task 10 è l'ARCHIVIO, non l'ambiente. Fino alla 2.4.1
    # venivano da `BRIDGE_DEADLINE_MIN` e `OLLAMA_REQUEST_TIMEOUT` perché era
    # lì che li leggevano `_enqueue_chat_job` e `OpenAICompatRunner.__init__`,
    # e la copia d'archivio (Task 6) non aveva lettori: due rappresentazioni
    # dello stesso numero nello stesso payload (invariante 1), che divergevano
    # appena qualcuno salvava da questa pagina. Adesso il numero è uno solo, e
    # questa lettura è la STESSA che il turno subisce: `_enqueue_chat_job`
    # legge `ponte.scadenza_min` e il runner locale riceve `ollama.timeout_s`
    # (via `applica_timeout`, rifatto a ogni salvataggio).
    #
    # I valori arrivano già riportati dentro gli estremi da `load_models_config`
    # (`_clamp_int`), quindi qui non si ripulisce una seconda volta.
    _scadenza_ponte = payload["ponte"]["scadenza_min"]
    _timeout_ollama = payload["ollama"]["timeout_s"]
    payload["adesso"] = componi_adesso(
        catena=_catena,
        credenziali=_credenziali,
        modelli=_modelli,
        ponte_attivo=_ponte_acceso,
        # La STESSA lettura che `handlers_chat._enqueue_chat_job` fa a ogni
        # turno per scrivere la scadenza (`now + ponte.scadenza_min * 60`), e
        # lo STESSO numero che va ai connettori qui sotto: la frase in cima e
        # la riga sotto il piano non possono dire due minuti diversi.
        scadenza_ponte_min=_scadenza_ponte,
    )
    # La topologia: chi è in catena, in che ordine, e chi ne sta fuori. La
    # pagina RICEVE due liste già ordinate e non ne calcola nessuna --
    # invariante 2 della spec.
    payload["catena"], payload["fuori_catena"] = componi_topologia(
        chain_order=_catena,
        credenziali=_credenziali,
        modelli=_modelli,
        ponte_attivo=_ponte_acceso,
        # Che cosa è successo DAVVERO, per provider (Task 11). Non una sonda:
        # `RegistroEsiti` è alimentato dal ciclo di ripiego del router, cioè
        # dal traffico vero. Sondare cinque provider a ogni apertura della
        # pagina costerebbe denaro e quota per un'informazione che scade
        # subito, e trasformerebbe questa pagina in una cosa che conviene non
        # aprire (progetto §11.2).
        #
        # Il `{}` non è un ripiego «comportati come prima»: è il registro di
        # una app che non ne ha uno (una fixture che non fa girare
        # `create_app`), e produce esattamente ciò che è vero in quel caso --
        # nessuna osservazione, e la pagina lo dice.
        esiti=(request.app["registro_esiti"].tutti()
               if request.app.get("registro_esiti") is not None else {}),
        # L'orologio di parete, letto QUI e passato: `decisione_modelli` è un
        # modulo di funzioni pure e non ne legge nessuno. È anche l'unico modo
        # in cui «3 min fa» è una cosa che si possa provare.
        adesso=time.time(),
        scadenza_ponte_min=_scadenza_ponte,
        timeout_ollama_s=_timeout_ollama,
    )
    # Cosa c'è dopo l'ultimo anello: una frase sulla catena, non su una riga.
    # Quale riga sia l'ultima cambia con un gesto, e la pagina riordina da sé
    # fra il gesto e la risposta del server -- attaccata a una riga, dopo un
    # riordino direbbe «ultimo della catena» di uno che non lo è più.
    payload["fine_catena"] = FINE_CATENA if payload["catena"] else ""
    return web.json_response(payload)


async def handle_save_models_config(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON body"}, status=400)
    data_dir = request.app.get("data_dir") or "/data"
    clean = save_models_config(data_dir, body if isinstance(body, dict) else {})
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
    ricalcola = request.app.get("ricalcola_catena")
    if callable(ricalcola):
        ricalcola()
    return web.json_response({"ok": True, **clean})


# `_hide_free_models_enabled()` è uscito con questa fetta. Leggeva
# `HIRIS_HIDE_FREE_MODELS` dall'ambiente, cioè l'opzione dell'add-on, mentre il
# valore vive nell'archivio dal Task 6 (`nascondi_gratuiti`, seminato proprio
# da quella variabile): finché il lettore restava qui, la casella del pannello
# avrebbe scritto nell'archivio e la lista avrebbe continuato a filtrare
# sull'ambiente -- una casella che non fa niente, cioè il difetto di questa
# fetta rimesso in un pannello nuovo. Adesso il valore arriva come argomento a
# `_fetch_openrouter_models`, e `HIRIS_HIDE_FREE_MODELS` perde il suo unico
# lettore di comportamento (resta letta da `migrazione_opzioni` per la semina,
# e l'opzione esce da `config.yaml` col Task 13).

# Recent Claude models (Anthropic doesn't expose a public list-models endpoint)
#
# Task 9: la voce "auto" è USCITA da questa lista. Non era un modello: era la
# parola con cui il vecchio picker diceva «scegli tu», e salvarla come valore è
# un difetto -- `resolve_model("auto", "chat", "auto")` restituisce "auto" e la
# richiesta parte con `model="auto"` verso un provider che quel nome non lo
# conosce. Nell'archivio «auto» è la STRINGA VUOTA, e il pannello la offre come
# prima voce con la sua nota (`decisione_modelli.NOTA_AUTO`), che dice anche a
# quale modello si risolve oggi.
_CLAUDE_MODELS = [
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-7",
]

# Fallback OpenAI models if the API call fails
_OPENAI_FALLBACK = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"]

# Pattern: keep only current-gen GPT + reasoning models, no legacy/instruct/embedding
_OPENAI_KEEP = re.compile(r"^(gpt-4[o.1]|o[1-9](-mini|-preview)?)")
_OPENAI_SKIP = re.compile(r"instruct|embed|vision|realtime|audio|transcribe|tts|whisper")


# ── Le tre letture, e la loro PROVENIENZA ─────────────────────────────────
#
# Ognuna restituisce `(modelli, fonte)`, dove `fonte` è "viva" (letta adesso
# dal provider) o "riserva" (elenco scritto nel sorgente). Non è un dettaglio
# di registrazione: cinque secondi di pazienza e, se falliscono, queste
# funzioni restituivano una lista scritta a mano DUE ANNI FA con un
# `logger.warning` e niente altro -- indistinguibile, a schermo, da una lista
# vera. Peggio: un provider con la chiave sbagliata compare lo stesso
# nell'elenco, perché la condizione è la PRESENZA della chiave, non la sua
# validità. Da qui si poteva stare davanti a un elenco che sembra vero, per un
# provider che non risponderebbe comunque. Il valore torna al chiamante e
# arriva fino al pannello, che lo dice con le parole di
# `decisione_modelli.provenienza`.
async def _fetch_openai_models(api_key: str) -> tuple[list[str], str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://api.openai.com/v1/models", headers=headers) as resp:
                if resp.status != 200:
                    logger.warning("OpenAI models list returned %s", resp.status)
                    return _OPENAI_FALLBACK, "riserva"
                data = await resp.json()
        models = [
            m["id"] for m in data.get("data", [])
            if _OPENAI_KEEP.match(m["id"]) and not _OPENAI_SKIP.search(m["id"])
        ]
        models.sort()
        # Una risposta 200 che non contiene NESSUN modello utilizzabile non è
        # una lettura riuscita: quello che si mostra viene dal sorgente, e si
        # dichiara per quello che è.
        return (models, "viva") if models else (_OPENAI_FALLBACK, "riserva")
    except Exception as exc:
        logger.warning("Could not fetch OpenAI models: %s", exc)
        return _OPENAI_FALLBACK, "riserva"


async def _fetch_claude_models(api_key: str) -> tuple[list[str], str]:
    """L'elenco dei modelli di Anthropic, letto adesso.

    Fino alla fetta «il modello del piano» questa lettura non esisteva, e il
    codice ne dichiarava la ragione: che Anthropic non avrebbe nessuna rotta
    pubblica di elenco. **E' FALSO**, verificato sulla documentazione ufficiale il
    15/08/2026: `GET /v1/models` c'è, paginato (`limit` 1-1000, predefinito
    20), ordinato dai più recenti, e ogni voce porta `id`, `display_name`,
    `created_at` e `capabilities`. `_CLAUDE_MODELS` resta come RISERVA -- tre
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
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                    "https://api.anthropic.com/v1/models?limit=100",
                    headers=headers) as resp:
                if resp.status != 200:
                    logger.warning("Anthropic models list returned %s", resp.status)
                    return _CLAUDE_MODELS, "riserva"
                data = await resp.json()
        # NESSUNA CURATELA e nessun riordino: a differenza di OpenAI qui non
        # c'è rumore da filtrare (niente embedding, niente audio, niente
        # legacy-instruct), e l'ordine È un'informazione -- i più recenti per
        # primi, come li manda l'API. Riordinare nasconderebbe qual è il
        # modello nuovo.
        modelli = [m["id"] for m in data.get("data", []) if m.get("id")]
        # Una risposta 200 che non contiene nessun modello non è una lettura
        # riuscita: la stessa regola già scritta in `_fetch_openai_models`.
        return (modelli, "viva") if modelli else (_CLAUDE_MODELS, "riserva")
    except Exception as exc:
        logger.warning("Could not fetch Anthropic models: %s", exc)
        return _CLAUDE_MODELS, "riserva"


async def _fetch_ollama_models(local_model_url: str,
                               modello_scelto: str) -> tuple[list[str], str]:
    """L'elenco di ciò che è SCARICATO su quella macchina, da `/api/tags`.

    Il ripiego è il modello scelto e basta: non è un catalogo di riserva, è
    «quello che so, e non ho potuto verificare che ci sia ancora». Quando
    nemmeno quello c'è, la lista è vuota -- ed è la verità, non un guasto.
    """
    from ..backends.ollama import _validate_ollama_url
    riserva = [modello_scelto] if modello_scelto else []
    try:
        _validate_ollama_url(local_model_url)
    except ValueError as exc:
        logger.warning("Invalid local_model_url for Ollama listing: %s", exc)
        return riserva, "riserva"
    base = local_model_url.rstrip("/")
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{base}/api/tags") as resp:
                if resp.status != 200:
                    logger.warning("Ollama /api/tags returned %s", resp.status)
                    return riserva, "riserva"
                data = await resp.json()
        return [m["name"] for m in data.get("models", [])], "viva"
    except Exception as exc:
        logger.warning("Could not fetch Ollama models: %s", exc)
        return riserva, "riserva"


# Curated subset of popular OpenRouter models. The full catalog (200+) is
# obtainable via openrouter.ai/api/v1/models but we surface only the most
# requested presets so the dropdown stays usable. Free-tier models marked
# ':free' have rate limits but no charge. User can still type any model
# manually with prefix 'openrouter:provider/model[:variant]'.
#
# All entries SHOULD support tool use — HIRIS always sends the tool schema in
# chat requests. Models without tool support fail with HTTP 404
# "No endpoints found that support tool use" (see hermes-3-llama-3.1-405b:free,
# removed in v0.9.8 after observed failures). The live filter in
# `_fetch_openrouter_models` is authoritative when available.
_OPENROUTER_PRESETS = [
    # Free tier (rate-limited but $0)
    "openrouter:meta-llama/llama-3.3-70b-instruct:free",
    "openrouter:google/gemma-3-27b-it:free",
    "openrouter:qwen/qwen-2.5-72b-instruct:free",
    "openrouter:deepseek/deepseek-chat:free",
    "openrouter:mistralai/mistral-nemo:free",
    # Popular paid models accessible through OpenRouter
    "openrouter:anthropic/claude-sonnet-4-6",
    "openrouter:anthropic/claude-opus-4-7",
    "openrouter:openai/gpt-4o",
    "openrouter:openai/gpt-4.1",
    "openrouter:google/gemini-2.5-flash",
    "openrouter:mistralai/mistral-large",
]


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
                                   nascondi_gratuiti: bool = False,
                                   ) -> tuple[list[str], str]:
    """Fetch the full OpenRouter model list and filter to a usable, tool-capable subset.

    Falls back to _OPENROUTER_PRESETS (best-effort, may include tool-incapable
    models) only if the live capability check cannot be performed.

    `nascondi_gratuiti` arriva dall'ARCHIVIO (`models_config["nascondi_gratuiti"]`),
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
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://openrouter.ai/api/v1/models", headers=headers) as resp:
                if resp.status != 200:
                    logger.warning("OpenRouter models list returned %s", resp.status)
                    return _OPENROUTER_PRESETS, "riserva"
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
            return _OPENROUTER_PRESETS, "riserva"

        hide_free = bool(nascondi_gratuiti)

        # Keep curated presets first (in order), filtered by capability.
        result = [
            m for m in _OPENROUTER_PRESETS
            if m.removeprefix("openrouter:") in tool_capable_ids
            and not (hide_free and m.endswith(":free"))
        ]
        # Add any other ':free' tool-capable models not already in presets.
        # Skip them entirely when the box is ticked.
        if not hide_free:
            for entry in data.get("data", []):
                mid = entry.get("id", "")
                if mid.endswith(":free") and mid in tool_capable_ids:
                    tagged = f"openrouter:{mid}"
                    if tagged not in result:
                        result.append(tagged)
        return (result, "viva") if result else (_OPENROUTER_PRESETS, "riserva")
    except Exception as exc:
        logger.warning("Could not fetch OpenRouter models: %s", exc)
        return _OPENROUTER_PRESETS, "riserva"


# `is_openrouter_model_tool_capable` (uscita, fetta E4 Task 3 "un bot
# solo"): validava un modello OpenRouter contro la capability list live al
# salvataggio di un chatbot -- il suo unico chiamante era
# `handlers_chatbots._validate_openrouter_model`, uscito insieme a
# `handle_create_chatbot`/`handle_update_chatbot` (le tre strade di
# creazione sopravvissute alla E3 convergevano tutte su POST /api/chatbots
# con `enabled: true` di default, il contrario di quanto prescrive lo
# scope). Orfana per costruzione di questo task (non prevista dal brief,
# trovata dal censimento), raccolta subito insieme ai suoi sei test in
# tests/test_handlers_models_openrouter.py -- `_supports_tools`/
# `_fetch_openrouter_models`/`_OPENROUTER_PRESETS` restano vivi (alimentano
# GET /api/models, adesso il pannello del modello, indipendente dal CRUD
# chatbot) e non sono toccati. (`_hide_free_models_enabled`, che era nominata
# qui accanto, è uscita col Task 9: vedi il commento sopra `_CLAUDE_MODELS`.)


# `_enrich_provider` e `_NOMI_IN_CATENA` sono USCITI con il Task 9.
# `_enrich_provider` attaccava a ogni voce `in_catena` + `has_credential`: era
# la TERZA superficie che descriveva l'appartenenza alla catena, dopo che il
# Task 7 aveva tolto `providers[].active` e il Task 8 l'intero `providers[]`
# da `/api/models/config`. Il suo unico lettore era il picker della vecchia
# sezione 01, uscito col Task 8; questa rotta serve adesso UN SOLO cliente --
# il pannello del modello -- che l'appartenenza non la usa: la riga da cui il
# pannello si apre sta già dentro `catena` o dentro `fuori_catena`, e sono
# quelle due liste a dirlo. `_NOMI_IN_CATENA` esisteva solo per riconciliare
# l'id storico "anthropic" di questa rotta col nome "claude" della catena: gli
# id di questa rotta sono adesso i CINQUE del prodotto, gli stessi di ogni
# altra superficie, e non c'è più niente da riconciliare.


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
    client diverso dalla pagina (il gateway, uno script) si aspetta, e una
    rotta che cambia significato in silenzio è la cosa che questa fetta ritira.
    """
    voluto = request.query.get("provider", "")
    archivio = load_models_config(request.app.get("data_dir") or "/data")
    provider_models = archivio["provider_models"]
    modello_ollama = archivio["ollama"]["modello"]
    nascondi = bool(archivio["nascondi_gratuiti"])
    # Gli stessi modelli che la riga mostra, dalla stessa funzione: il pannello
    # e la riga da cui si apre non possono dire due cose diverse.
    in_uso = _modelli_in_uso(provider_models, modello_ollama,
                             archivio["ponte"]["modello"])
    claude_key = request.app.get("claude_api_key", "")
    openai_key = request.app.get("openai_api_key", "")
    openrouter_key = request.app.get("openrouter_api_key", "")
    local_url = request.app.get("local_model_url", "")

    async def leggi(pid: str) -> tuple[list[str], str, str, str]:
        """`(valori, fonte, scelto, auto_risolto)` per un provider.

        La fonte "assente" non è un errore: è «non c'è nessun elenco da
        leggere, e il perché è la credenziale». Serve perché un pannello che si
        apre deve SEMPRE dare una risposta -- nascondere è comodo per chi
        capisce e crudele per chi non capisce perché una cosa è sparita -- e la
        risposta la scrive `decisione_modelli`, non questa pagina.
        """
        if pid == "subscription":
            # Tre alias, sempre gli stessi: non si leggono da nessuna parte
            # perché non c'è niente da leggere. `modello_cli` ne produce
            # esattamente tre. Senza il token il piano non risponde e non c'è
            # niente da scegliere: la riga lo dice già, e il pannello lo ridice
            # con la stessa parola invece di offrire tre voci inerti.
            if not _config_has_credential(request, "subscription"):
                return [], "assente", "", ""
            return [], "fissa", in_uso["subscription"], ""
        if pid == "claude":
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
            if not claude_key:
                return [], "assente", provider_models.get("claude", ""), ""
            valori, fonte = await _fetch_claude_models(claude_key)
            return valori, fonte, provider_models.get("claude", ""), in_uso["claude"]
        if pid == "openai":
            if not openai_key:
                return [], "assente", provider_models.get("openai", ""), ""
            valori, fonte = await _fetch_openai_models(openai_key)
            return valori, fonte, provider_models.get("openai", ""), in_uso["openai"]
        if pid == "openrouter":
            if not openrouter_key:
                return [], "assente", provider_models.get("openrouter", ""), ""
            valori, fonte = await _fetch_openrouter_models(
                openrouter_key, nascondi_gratuiti=nascondi)
            return (valori, fonte, provider_models.get("openrouter", ""),
                    in_uso["openrouter"])
        # Ollama. Nessuna voce «auto»: il runner locale usa SEMPRE il modello
        # scelto (`locale=True` fa vincere `_modello_scelto()` su ogni altro
        # ramo di `_resolve_model`),
        # perché quell'istanza ne ha scaricato uno solo e chiedergliene un
        # altro fallirebbe.
        if not local_url:
            return [], "assente", modello_ollama, ""
        valori, fonte = await _fetch_ollama_models(local_url, modello_ollama)
        return valori, fonte, modello_ollama, ""

    providers: list[dict] = []
    for pid in _CONFIG_PROVIDER_IDS:
        if voluto and voluto != pid:
            continue
        valori, fonte, scelto, auto = await leggi(pid)
        # LA REGOLA, in una riga: chi viene CHIESTO riceve sempre una risposta;
        # senza una richiesta compaiono solo quelli per cui un elenco esiste.
        # Un pannello che si apre su una riga e non dice niente sarebbe la
        # forma piccola del difetto che questa fetta chiude.
        if not voluto and fonte == "assente":
            continue
        providers.append(componi_pannello(
            provider_id=pid, valori=valori, fonte=fonte, scelto=scelto,
            auto_risolto=auto, indirizzo=local_url, nascondi_gratuiti=nascondi,
        ))

    return web.json_response({"providers": providers})
