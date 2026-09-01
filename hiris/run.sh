#!/usr/bin/with-contenv bashio

# L'ordine di questo file segue quello di `config.yaml`, che e' l'ordine della
# pagina che l'utente vede nel Supervisor. Se riordini la', riordina anche qui:
# leggere i due file appaiati e' l'unico modo per accorgersi che un'opzione ha
# perso il suo export.
#
# Versione B (3.0.0): quattordici export sono usciti da questo file insieme
# alle loro opzioni -- PROVIDER_CLAUDE, PROVIDER_SUBSCRIPTION,
# PROVIDER_OPENROUTER, PROVIDER_OPENAI, PROVIDER_OLLAMA, HIRIS_HIDE_FREE_MODELS,
# LLM_STRATEGY, BRIDGE_ENABLED, BRIDGE_DEADLINE_MIN, CHAT_DAILY_CAP,
# LOCAL_MODEL_NAME, OLLAMA_REQUEST_TIMEOUT, HISTORY_RETENTION_DAYS e
# HIRIS_DEBUG_EXPOSE_PORT. Quelle decisioni vivono adesso nell'archivio di
# HIRIS (`/data/models_config.json`, `/data/impostazioni_chat.json`), dove le
# scrive la pagina che le fa vedere. `migrazione_opzioni.semina` e
# `server._chain_as_it_was` continuano a LEGGERE alcune di quelle variabili
# d'ambiente: e' la migrazione, e serve a un'installazione che salti la
# versione A e arrivi qui con l'ambiente ancora popolato dal vecchio run.sh
# (non puo' succedere via Supervisor, ma puo' succedere in sviluppo). Escono
# con la fetta successiva.

# ── 1. Le credenziali dei provider ──────────────────────────────────────────
# Solo credenziali: chi le USA lo dice la catena, nella pagina Modelli di
# HIRIS. I cinque interruttori `provider_*` che stavano qui sopra sono usciti
# con la versione B -- erano la seconda rappresentazione dello stato di un
# provider, ed e' la seconda rappresentazione che permetteva alla pagina di
# mentire.
export CLAUDE_API_KEY=$(bashio::config 'claude_api_key')
export CLAUDE_CODE_OAUTH_TOKEN=$(bashio::config 'claude_code_oauth_token' '')
export CLAUDE_CONFIG_DIR=/data/claude
export OPENROUTER_API_KEY=$(bashio::config 'openrouter_api_key' '')
export OPENAI_API_KEY=$(bashio::config 'openai_api_key' '')
# L'INDIRIZZO di Ollama, e nient'altro: il nome del modello
# (`local_model.model`) e l'attesa per richiesta (`local_model.request_timeout`)
# si decidono nella riga di Ollama, nella pagina Modelli, e vivono
# nell'archivio (`ollama.modello`, `ollama.timeout_s`).
export LOCAL_MODEL_URL=$(bashio::config 'local_model.url' '')

# ── 2. Aspetto ──────────────────────────────────────────────────────────────
export THEME=$(bashio::config 'theme' 'auto')

# ── 3. Embedding (oggi inattivi) ────────────────────────────────────────────
# Fetta "esce il documentale": i due export qui sotto restano ma sono
# DICHIARATI INERTI -- server.py li legge per costruire il provider, ma dopo
# quella fetta nessun percorso chiama piu' `embed()`. Esce invece
# MEMORY_RAG_K/memory.rag_k: era il k del richiamo per somiglianza
# sull'archivio di conoscenza, uscito con la fetta.
export MEMORY_EMBEDDING_PROVIDER=$(bashio::config 'memory.embedding_provider' '')
export MEMORY_EMBEDDING_MODEL=$(bashio::config 'memory.embedding_model' '')

# HuggingFace model cache → persistent HA config directory. Resta esportata:
# la useranno i provider locali (model2vec/fastembed) se e quando i vettori
# verranno accesi. Nota: e' una cartella DENTRO la configurazione dell'utente
# (/config/hiris/models), fuori dall'add-on -- se un'installazione precedente
# ci ha scaricato un modello, quel file NON viene toccato da questa fetta.
export HF_HOME=/config/hiris/models/huggingface

# ── 4. Avanzate: registro, sicurezza ────────────────────────────────────────
export LOG_LEVEL=$(bashio::config 'log_level' 'info')
export INTERNAL_TOKEN=$(bashio::config 'internal_token' '')
export SUPERVISOR_INGRESS_CIDR=$(bashio::config 'supervisor_ingress_cidr' '172.30.32.0/23')

# Versione B: esce HIRIS_DEBUG_EXPOSE_PORT/debug_expose_port, con il blocco di
# sette `bashio::log.warning` che era il suo unico effetto. Non apriva niente:
# ad aprire la porta e' la sezione Rete di Home Assistant, e la sua descrizione
# in `config.yaml` (`ports_description`) adesso dice per intero cosa comporta.
# Un promemoria travestito da comando, con zero lettori nel codice.

bashio::log.info "Starting HIRIS"
bashio::log.info "Log level: ${LOG_LEVEL}"
bashio::log.info "Theme: ${THEME}"

# Pre-flight sanity checks (review mediums): warn early instead of surfacing a
# cryptic runtime error later. Sono WARNING soltanto — l'add-on parte lo stesso.
if ! echo "${SUPERVISOR_INGRESS_CIDR}" | grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}([[:space:]]*,[[:space:]]*([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2})*$'; then
  bashio::log.warning "supervisor_ingress_cidr non sembra un CIDR valido (${SUPERVISOR_INGRESS_CIDR}); l'app ignora le voci non parsabili e usa il default."
fi

# I due avvisi sul ponte -- «il piano e' acceso ma manca il token» e «hai il
# token ma il ponte e' spento» -- NON sono spariti: si sono SPOSTATI in
# `server.py::_bridge_notices`, chiamato all'avvio. Leggevano
# PROVIDER_SUBSCRIPTION e BRIDGE_ENABLED, che con la versione B non esistono
# piu': il ponte adesso e' `ponte.attivo` nell'archivio di HIRIS, e da qui
# l'archivio non si legge. In Python si legge, e le due frasi restano parole
# che arrivano PRIMA che l'utente apra la chat.
#
# Qui resta cio' che questo file puo' ancora misurare da solo: se non c'e'
# NESSUNA credenziale, non c'e' niente a cui chiedere una risposta, e non
# serve leggere nessun archivio per saperlo.
if [ -z "${CLAUDE_API_KEY}" ] && [ -z "${OPENAI_API_KEY}" ] && [ -z "${OPENROUTER_API_KEY}" ] \
   && [ -z "${LOCAL_MODEL_URL}" ] && [ -z "${CLAUDE_CODE_OAUTH_TOKEN}" ]; then
  bashio::log.warning "Nessuna credenziale configurata: ne' una chiave API, ne' un indirizzo Ollama, ne' il token del piano Claude Max. La chat non potra' rispondere finche' non ne metti almeno una in Configurazione, e non metti il provider in catena nella pagina Modelli di HIRIS."
fi

cd /usr/lib/hiris
exec python3 -m app.main
