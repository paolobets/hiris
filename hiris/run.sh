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
# scrive la pagina che le fa vedere. Nessuna riga dell'add-on legge piu' quelle
# variabili d'ambiente: le ultime letture sono uscite il 02/10/2026.

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

# ── 4. Chi usa HIRIS ────────────────────────────────────────────────────────
# `true`/`false`, come `bashio::config` scrive un `bool`. Il codice apre solo
# su `true` (`panel_visibility.parse_access_flag`) e lo legge una volta,
# in `create_app`.
export HIRIS_NON_ADMIN_ACCESS=$(bashio::config 'non_admin_access')

# ── 5. Avanzate: registro, sicurezza ────────────────────────────────────────
export LOG_LEVEL=$(bashio::config 'log_level' 'info')
# `INTERNAL_TOKEN` e' uscito il 22/09/2026 col segreto condiviso (reperto A-5):
# un servizio esterno adesso si accoppia dalla pagina Servizi e firma.
# Il valore di fabbrica ha UNA casa, `api/ingresso.py::RETE_PREDEFINITA` (S-15,
# F-10, Tappa 7): qui si esporta solo cio' che il proprietario ha scritto, e
# vuoto se non ha scritto niente. Non `bashio::config 'chiave' ''`: letto il
# 07/10/2026 il sorgente di bashio (`lib/config.sh`), `${2:-null}` trasforma un
# default vuoto in «null», e la stringa «null» arriverebbe al Python come una
# rete sbagliata. `config.has_value` e' falso per «null» e per il vuoto.
SUPERVISOR_INGRESS_CIDR=""
if bashio::config.has_value 'supervisor_ingress_cidr'; then
    SUPERVISOR_INGRESS_CIDR=$(bashio::config 'supervisor_ingress_cidr')
fi
export SUPERVISOR_INGRESS_CIDR

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
# Qui c'era un controllo a espressione regolare su `supervisor_ingress_cidr`,
# ed e' uscito il 22/09/2026 col reperto A-3. Due ragioni, e la seconda e' la
# vera: diceva una cosa FALSA -- «l'app ignora le voci non parsabili e usa il
# default», che Python non faceva -- e diceva la stessa cosa in un secondo
# linguaggio, libera di divergere da quella vera. Adesso a validare e'
# `api/ingresso.py::reti_fidate`, che nomina ogni voce rifiutata e dice perche'.

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
