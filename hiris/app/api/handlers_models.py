from __future__ import annotations
import json
import logging
import os
import re

import aiohttp
from aiohttp import web

from ..decisione_modelli import componi_adesso, componi_topologia, nome
from ..env_util import env_bool

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
    "ponte": {"attivo": False, "scadenza_min": 5, "tetto_giornaliero": 50},
    "ollama": {"modello": "", "timeout_s": 120},
}

# Le sole chiavi che questa versione possiede. Tutto il resto che sta sul disco
# (a partire da 'brain_model') sopravvive intatto -- vedi la
# lettura-modifica-scrittura in save_models_config.
_CHIAVI_NOSTRE = (
    "chain_order", "provider_models", "ponte", "ollama",
    "nascondi_gratuiti", "strategia_ultima", "seminato",
)


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


def _pulisci_ponte(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    d = _PREDEFINITI_ARCHIVIO["ponte"]
    return {
        "attivo": bool(raw.get("attivo", d["attivo"])),
        "scadenza_min": _clamp_int(raw.get("scadenza_min"), d["scadenza_min"], 1, 120),
        "tetto_giornaliero": _clamp_int(
            raw.get("tetto_giornaliero"), d["tetto_giornaliero"], 0, 1000),
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
    }


def _models_config_path(data_dir: str) -> str:
    return os.path.join(data_dir, "models_config.json")


def load_models_config(data_dir: str) -> dict:
    try:
        with open(_models_config_path(data_dir), encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        raw = {}
    except Exception:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
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


def save_models_config(data_dir: str, data: dict) -> dict:
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
    disk_data: dict = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                disk_data = json.load(fh)
        except Exception:
            disk_data = {}
    if not isinstance(disk_data, dict):
        disk_data = {}
    # Task 6: la fusione parte dal CONTENUTO GIA' SU DISCO, non dai
    # predefiniti -- ed e' la STESSA ragione del fix di claude_runner._save_usage
    # per 'per_agent'. Da quando le chiavi scritte sono sette invece di due, un
    # corpo parziale (`{"chain_order": [...]}`) ricostruito sui predefiniti
    # azzererebbe ponte, Ollama e nascondi_gratuiti: una perdita di
    # configurazione silenziosa, cioe' esattamente cio' che la versione A
    # esiste per impedire. Il contratto della PUT e' «sempre l'oggetto intero»
    # e la pagina lo rispetta, ma un client diverso esiste (il gateway MCP).
    base = dict(disk_data)
    base.update({k: v for k, v in data.items() if k in _CHIAVI_NOSTRE})
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



# SP-2 Task 7B: fixed provider order for the enriched config payload.
# Distinct from handle_list_models' "anthropic" id — here we use the five ids
# del prodotto (subscription/claude/openai/openrouter/ollama) so the UI can
# honestly show ALL five, including subscription and any uncredentialed
# provider, without needing a separate id-mapping table.
#
# fetta «la catena diventa l'unica verità»: il campo "toggle" è uscito insieme
# a `_TOGGLE_ENV_VARS` e `_config_raw_toggle`. Leggevano i cinque interruttori
# `provider_*` dall'ambiente, e gli interruttori non decidono più niente: lo
# stato di un provider è l'appartenenza alla catena più la credenziale, e sono
# due fatti diversi che non collassano l'uno nell'altro. Il Task 13 toglierà le
# opzioni da `config.yaml`; qui smettono di essere LETTE, che è la condizione
# per poterle togliere.
#
# Task 5: la label non e' piu' letterale qui -- e' derivata da
# decisione_modelli.NOMI (via nome()), l'unico posto dove i cinque nomi sono
# scritti. L'ordine delle voci NON cambia (pinnato da
# tests/test_models_api.py::test_get_models_config_enriched_providers).
_CONFIG_PROVIDER_IDS = ("subscription", "claude", "openai", "openrouter", "ollama")
_CONFIG_PROVIDERS = tuple(
    (pid, nome(pid))
    for pid in _CONFIG_PROVIDER_IDS
)


def _config_has_credential(request: web.Request, provider_id: str) -> bool:
    """Boolean-only credential presence check — NEVER return the secret value."""
    if provider_id == "subscription":
        return bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip())
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


def _build_config_providers(request: web.Request) -> list[dict]:
    """Il payload storico `providers[]`, tenuto in vita finché il Task 8 non
    riscrive la pagina. `active` è stato rinominato `in_catena` perché è ciò
    che significa adesso: non c'è più un interruttore da incrociare con una
    credenziale, c'è l'appartenenza."""
    catena = list(request.app.get("catena_modelli") or [])
    ponte = bool(request.app.get("ponte_attivo"))
    return [
        {
            "id": pid,
            "label": label,
            # Il piano non è un membro di `chain_order`: sta in testa alla
            # catena quando il ponte è acceso, e fuori altrimenti. È la stessa
            # regola di `componi_topologia`, e viene da lì il campo che la
            # pagina disegnerà davvero (`catena`/`fuori_catena`).
            "in_catena": ponte if pid == "subscription" else (pid in catena),
            "has_credential": _config_has_credential(request, pid),
        }
        for pid, label in _CONFIG_PROVIDERS
    ]


def _modelli_in_uso(request: web.Request, provider_models: dict) -> dict[str, str]:
    """Il modello che il runtime userebbe ADESSO, per provider.

    Non «il modello configurato»: quello che il runner risolverebbe con
    `model="auto"`. Sono i due rami veri --
    `claude_runner.resolve_model` (default per-provider, altrimenti
    AUTO_MODEL_MAP["chat"]) e `OpenAICompatRunner._resolve_model` (idem, con
    la sua mappa) -- letti qui invece di essere reinventati.

    La riga di `subscription` è la parte scomoda, ed è VERA: il modello del
    ponte è un effetto collaterale del modello di Claude API.
    `api/handlers_chat._enqueue_chat_job` compone
    `modello_cli(resolve_model("auto", "chat", provider_models["claude"]))`,
    quindi cambiare il modello di Claude API cambia il modello che gira sul
    piano, e `claude-opus-4-7` / `claude-opus-4-1` producono lo stesso
    identico `opus`. La pagina lo mostra perché è così, non perché ci piaccia.

    Fino alla 2.4.1 quel primo argomento era `impostazioni.model`, e questa
    funzione passava `"auto"`: il campo `modello` della decisione MENTIVA a
    chiunque avesse fissato un modello in `#/impostazioni` -- e dal Task 2
    mentiva in corpo 20, in cima alla pagina. Il campo è uscito con la fetta
    «la catena diventa l'unica verità» (Task 4): ora le due composizioni sono
    lo stesso identico calcolo, e questa riga non può più divergere dal
    runtime perché non c'è più una seconda sorgente da cui divergere.
    """
    from ..agent.runner import modello_cli
    from ..backends.openai_compat_runner import AUTO_MODEL_MAP as _AUTO_COMPAT
    from ..claude_runner import resolve_model

    claude = resolve_model("auto", "chat", provider_models.get("claude", ""))
    return {
        "subscription": modello_cli(claude),
        "claude": claude,
        "openai": provider_models.get("openai", "") or _AUTO_COMPAT["chat"],
        "openrouter": provider_models.get("openrouter", "") or _AUTO_COMPAT["chat"],
        "ollama": request.app.get("local_model_name", ""),
    }


async def handle_get_models_config(request: web.Request) -> web.Response:
    data_dir = request.app.get("data_dir") or "/data"
    payload = load_models_config(data_dir)
    payload["providers"] = _build_config_providers(request)
    payload["llm_strategy"] = os.environ.get("LLM_STRATEGY", "balanced")
    payload["embeddings"] = {
        "provider": os.environ.get("MEMORY_EMBEDDING_PROVIDER", ""),
        "model": os.environ.get("MEMORY_EMBEDDING_MODEL", ""),
    }
    payload["ollama_model"] = request.app.get("local_model_name", "")
    payload["ponte_attivo"] = bool(request.app.get("ponte_attivo"))
    # I fatti si misurano UNA volta e si passano a entrambe le composizioni:
    # due derivazioni degli stessi fatti nello stesso handler sarebbero la
    # miniatura del difetto che questa fetta chiude.
    _credenziali = {p["id"]: p["has_credential"] for p in payload["providers"]}
    _modelli = _modelli_in_uso(request, payload["provider_models"])
    # LA catena, una sola: quella che il router ha in mano adesso. Non si
    # riderivano i nomi da `payload["chain_order"]` (l'archivio) perché
    # l'archivio e il runtime possono differire fino al riavvio -- è la
    # scrittura a caldo, invariante 4, che il Task 10 chiude. Finché quel
    # divario esiste, la pagina deve descrivere il RUNTIME, e descriverlo in un
    # modo solo: la frase e il disegno della catena leggono la stessa lista.
    _catena = list(request.app.get("catena_modelli") or [])
    payload["adesso"] = componi_adesso(
        catena=_catena,
        credenziali=_credenziali,
        modelli=_modelli,
        ponte_attivo=payload["ponte_attivo"],
        # La STESSA lettura che `handlers_chat._enqueue_chat_job` fa a ogni
        # turno per scrivere la scadenza (`now + BRIDGE_DEADLINE_MIN * 60`):
        # un numero solo, letto allo stesso modo in due punti, invece di due
        # default che possono divergere e far promettere alla pagina un'attesa
        # diversa da quella che il turno subisce davvero.
        scadenza_ponte_min=int(os.environ.get("BRIDGE_DEADLINE_MIN", "5") or 5),
    )
    # La topologia: chi è in catena, in che ordine, e chi ne sta fuori. La
    # pagina RICEVE due liste già ordinate e non ne calcola nessuna --
    # invariante 2 della spec.
    payload["catena"], payload["fuori_catena"] = componi_topologia(
        chain_order=_catena,
        credenziali=_credenziali,
        modelli=_modelli,
        ponte_attivo=payload["ponte_attivo"],
    )
    return web.json_response(payload)


async def handle_save_models_config(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON body"}, status=400)
    data_dir = request.app.get("data_dir") or "/data"
    clean = save_models_config(data_dir, body if isinstance(body, dict) else {})
    request.app["models_config"] = clean   # hot-update per la sessione corrente
    return web.json_response({"ok": True, **clean})


def _hide_free_models_enabled() -> bool:
    """Return True if HIRIS_HIDE_FREE_MODELS is set to a truthy value.

    Use case: an installer who has paid OpenRouter credit and wants the
    dropdown to surface only paid (more reliable) models — useful when the
    free :free models would otherwise tempt usage but their daily quota /
    upstream rate-limits make them unsuitable for the user's workflow.
    """
    return env_bool("HIRIS_HIDE_FREE_MODELS")

# Recent Claude models (Anthropic doesn't expose a public list-models endpoint)
_CLAUDE_MODELS = [
    "auto",
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-7",
]

# Fallback OpenAI models if the API call fails
_OPENAI_FALLBACK = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"]

# Pattern: keep only current-gen GPT + reasoning models, no legacy/instruct/embedding
_OPENAI_KEEP = re.compile(r"^(gpt-4[o.1]|o[1-9](-mini|-preview)?)")
_OPENAI_SKIP = re.compile(r"instruct|embed|vision|realtime|audio|transcribe|tts|whisper")


async def _fetch_openai_models(api_key: str) -> list[str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://api.openai.com/v1/models", headers=headers) as resp:
                if resp.status != 200:
                    logger.warning("OpenAI models list returned %s", resp.status)
                    return _OPENAI_FALLBACK
                data = await resp.json()
        models = [
            m["id"] for m in data.get("data", [])
            if _OPENAI_KEEP.match(m["id"]) and not _OPENAI_SKIP.search(m["id"])
        ]
        models.sort()
        return models if models else _OPENAI_FALLBACK
    except Exception as exc:
        logger.warning("Could not fetch OpenAI models: %s", exc)
        return _OPENAI_FALLBACK


async def _fetch_ollama_models(local_model_url: str, local_model_name: str) -> list[str]:
    from ..backends.ollama import _validate_ollama_url
    try:
        _validate_ollama_url(local_model_url)
    except ValueError as exc:
        logger.warning("Invalid local_model_url for Ollama listing: %s", exc)
        return [local_model_name] if local_model_name else []
    base = local_model_url.rstrip("/")
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{base}/api/tags") as resp:
                if resp.status != 200:
                    return [local_model_name] if local_model_name else []
                data = await resp.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception as exc:
        logger.warning("Could not fetch Ollama models: %s", exc)
        return [local_model_name] if local_model_name else []


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


async def _fetch_openrouter_models(api_key: str) -> list[str]:
    """Fetch the full OpenRouter model list and filter to a usable, tool-capable subset.

    Falls back to _OPENROUTER_PRESETS (best-effort, may include tool-incapable
    models) only if the live capability check cannot be performed.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://openrouter.ai/api/v1/models", headers=headers) as resp:
                if resp.status != 200:
                    logger.warning("OpenRouter models list returned %s", resp.status)
                    return _OPENROUTER_PRESETS
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
            return _OPENROUTER_PRESETS

        hide_free = _hide_free_models_enabled()

        # Keep curated presets first (in order), filtered by capability.
        result = [
            m for m in _OPENROUTER_PRESETS
            if m.removeprefix("openrouter:") in tool_capable_ids
            and not (hide_free and m.endswith(":free"))
        ]
        # Add any other ':free' tool-capable models not already in presets.
        # Skip them entirely if HIRIS_HIDE_FREE_MODELS is set.
        if not hide_free:
            for entry in data.get("data", []):
                mid = entry.get("id", "")
                if mid.endswith(":free") and mid in tool_capable_ids:
                    tagged = f"openrouter:{mid}"
                    if tagged not in result:
                        result.append(tagged)
        return result if result else _OPENROUTER_PRESETS
    except Exception as exc:
        logger.warning("Could not fetch OpenRouter models: %s", exc)
        return _OPENROUTER_PRESETS


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
# `_fetch_openrouter_models`/`_hide_free_models_enabled`/
# `_OPENROUTER_PRESETS` restano vivi (alimentano GET /api/models, il
# dropdown modelli, indipendente dal CRUD chatbot) e non sono toccati.


# Maps the provider "id" used in the /api/models payload to the name used in
# app["catena_modelli"]. Note: the payload id for Claude is "anthropic" but the
# chain name is "claude" — they diverge, hence the explicit mapping instead of
# a 1:1 lookup.
_NOMI_IN_CATENA = {
    "anthropic": "claude",
    "openai": "openai",
    "openrouter": "openrouter",
    "ollama": "ollama",
}


def _enrich_provider(request: web.Request, entry: dict, has_credential: bool) -> dict:
    """Attacca l'APPARTENENZA alla catena, mai il valore della credenziale.

    fetta «la catena diventa l'unica verità»: leggeva `app["active_providers"]`
    (interruttore AND credenziale) e pubblicava il campo `active`. Quella
    derivazione è uscita, e con lei la parola: un provider è usato se e solo se
    sta in catena, quindi il campo si chiama `in_catena` e legge la stessa
    lista che il router riceve.
    """
    catena = list(request.app.get("catena_modelli") or [])
    nome_catena = _NOMI_IN_CATENA.get(entry["id"], entry["id"])
    entry["in_catena"] = nome_catena in catena
    entry["has_credential"] = bool(has_credential)
    return entry


async def handle_list_models(request: web.Request) -> web.Response:
    providers = []

    # Anthropic / Claude
    claude_runner = request.app.get("claude_runner")
    if claude_runner is not None:
        providers.append(_enrich_provider(
            request,
            {"id": "anthropic", "label": nome("claude"), "models": _CLAUDE_MODELS},
            has_credential=True,
        ))

    # OpenAI
    openai_key = request.app.get("openai_api_key", "")
    if openai_key:
        models = await _fetch_openai_models(openai_key)
        providers.append(_enrich_provider(
            request,
            {"id": "openai", "label": nome("openai"), "models": models},
            has_credential=bool(openai_key),
        ))

    # OpenRouter (200+ models via single API key, includes free tier)
    openrouter_key = request.app.get("openrouter_api_key", "")
    if openrouter_key:
        models = await _fetch_openrouter_models(openrouter_key)
        providers.append(_enrich_provider(
            request,
            {"id": "openrouter", "label": nome("openrouter"), "models": models},
            has_credential=bool(openrouter_key),
        ))

    # Ollama / local
    local_url = request.app.get("local_model_url", "")
    local_name = request.app.get("local_model_name", "")
    if local_url:
        models = await _fetch_ollama_models(local_url, local_name)
        if models:
            providers.append(_enrich_provider(
                request,
                {"id": "ollama", "label": nome("ollama"), "models": models},
                has_credential=bool(local_url),
            ))

    return web.json_response({"providers": providers})
