#!/usr/bin/with-contenv bashio

# L'ordine di questo file segue quello di `config.yaml`, che e' l'ordine della
# pagina che l'utente vede nel Supervisor. Se riordini la', riordina anche qui:
# leggere i due file appaiati e' l'unico modo per accorgersi che un'opzione ha
# perso il suo export.

# ── 1. Provider AI ──────────────────────────────────────────────────────────
# SP-2: attivazione provider esplicita. Default false su tutti => l'app
# migra derivando gli attivi dalle credenziali presenti (retro-compat).
export PROVIDER_CLAUDE=$(bashio::config 'provider_claude' 'false')
export CLAUDE_API_KEY=$(bashio::config 'claude_api_key')
export PROVIDER_SUBSCRIPTION=$(bashio::config 'provider_subscription' 'false')
export CLAUDE_CODE_OAUTH_TOKEN=$(bashio::config 'claude_code_oauth_token' '')
export CLAUDE_CONFIG_DIR=/data/claude
export PROVIDER_OPENROUTER=$(bashio::config 'provider_openrouter' 'false')
export OPENROUTER_API_KEY=$(bashio::config 'openrouter_api_key' '')
# Hide :free OpenRouter models from the model dropdown. Useful for users
# with paid credit who want to avoid the low daily quota / upstream
# rate-limits that come with the free tier.
export HIRIS_HIDE_FREE_MODELS=$(bashio::config 'hide_free_models' 'false')
export PROVIDER_OPENAI=$(bashio::config 'provider_openai' 'false')
export OPENAI_API_KEY=$(bashio::config 'openai_api_key' '')
export PROVIDER_OLLAMA=$(bashio::config 'provider_ollama' 'false')
export LOCAL_MODEL_URL=$(bashio::config 'local_model.url' '')
export LOCAL_MODEL_NAME=$(bashio::config 'local_model.model' '')
# Per-request HTTP timeout for the Ollama backend, in seconds. Default 120.
# Bump for slow hardware running large local models (gemma4:e4b on Pi5 may
# need 240–300s before completion).
export OLLAMA_REQUEST_TIMEOUT=$(bashio::config 'local_model.request_timeout' '120')

# ── 2. Scelta fra i provider accesi ─────────────────────────────────────────
# fetta "la pagina di configurazione": esce CHAT_POLICY/chat_policy. Il router
# riceve sempre `model_chain` (`reconcile_chain` non torna mai vuota quando il
# router viene costruito), e `LLMRouter.__init__` scarta `chat_policy` quando
# `model_chain` c'e': il ramo che leggeva questa variabile era irraggiungibile
# in produzione. Prova per esteso in `config.yaml`, blocco 2.
export LLM_STRATEGY=$(bashio::config 'llm_strategy' 'balanced')

# ── 3. Ponte: la chat sul piano Claude Max ──────────────────────────────────
# 2.4.0: le quattro opzioni del ponte sono annidate sotto `ponte:` (e' l'unico
# raggruppamento che il Supervisor rende a schermo). Cambia SOLO il percorso
# dell'opzione: i nomi delle variabili d'ambiente restano identici, quindi
# nessun file Python e' toccato dall'annidamento.
# Nessun ripiego sulla vecchia chiave piatta: il Supervisor scarta le chiavi
# fuori schema prima di scrivere /data/options.json (verificato su
# `supervisor/apps/options.py`), quindi `bashio::config 'bridge_enabled'`
# tornerebbe vuoto comunque -- un ripiego darebbe l'illusione di una migrazione
# che non puo' avvenire.
# Un interruttore solo: `ponte.attivo` sostituisce la coppia
# `bridge_enabled` + `chat_via_subscription`, che erano una decisione con due
# leve. Sopravvive la variabile d'ambiente BRIDGE_ENABLED, che gia' nominava il
# concetto giusto ("il ponte e' acceso"); CHAT_VIA_SUBSCRIPTION esce del tutto,
# ed e' il segnale onesto che la seconda leva non c'e' piu'.
export BRIDGE_ENABLED=$(bashio::config 'ponte.attivo' 'false')
export BRIDGE_DEADLINE_MIN=$(bashio::config 'ponte.bridge_deadline_min' '5')
export CHAT_DAILY_CAP=$(bashio::config 'ponte.chat_daily_cap' '50')

# fetta E3 Task 7: escono SENTINEL_DAILY_CAP/sentinel_daily_cap e
# SENTINEL_COOLDOWN_SEC/sentinel_cooldown_min -- la Sentinella che li leggeva
# e' uscita per intero (SENTINEL_RONDA_MINUTES/sentinel_ronda_min era gia'
# uscito con la ronda, Task 4).
# fetta E3 Task 6: esce BRAIN_NOTIFY_HIGH/brain_notify_high -- la scansione di
# salute che leggeva questa opzione e' uscita col Brain che parlava.
# fetta E3 Task 13: esce APPRISE_URLS/apprise_urls -- notifiche.py, il suo
# unico lettore, e' uscito per intero. HA_NOTIFY_SERVICE/RETROPANEL_URL non
# erano mai stati esportati qui (letti dal codice via os.environ.get, mai
# un'opzione add-on): escono anche loro, dal codice.

# ── 4. Aspetto e conservazione ──────────────────────────────────────────────
export THEME=$(bashio::config 'theme' 'auto')
export HISTORY_RETENTION_DAYS=$(bashio::config 'history_retention_days' '90')

# ── 5. Embedding (oggi inattivi) ────────────────────────────────────────────
# Fetta "esce il documentale": i due export qui sotto restano ma sono
# DICHIARATI INERTI -- server.py li legge per costruire il provider, e la
# pagina Modelli li mostra, ma dopo questa fetta nessun percorso chiama piu'
# `embed()`. Esce invece MEMORY_RAG_K/memory.rag_k: era il k del richiamo per
# somiglianza sull'archivio di conoscenza, uscito con la fetta.
export MEMORY_EMBEDDING_PROVIDER=$(bashio::config 'memory.embedding_provider' '')
export MEMORY_EMBEDDING_MODEL=$(bashio::config 'memory.embedding_model' '')

# fetta "esce il documentale" (decisione del proprietario, 12 agosto 2026):
# escono MAYAN_URL/MAYAN_TOKEN/MAYAN_TAG_ID/MAYAN_SENSITIVITY/
# MAYAN_POLL_MINUTES e il blocco `mayan.*` di config.yaml. Il connettore
# Mayan, l'archivio di conoscenza in cui ingeriva e la cattura dello storico
# sono usciti insieme: nessun lettore di produzione leggeva piu' quell'archivio.

# HuggingFace model cache → persistent HA config directory. Resta esportata:
# la useranno i provider locali (model2vec/fastembed) se e quando i vettori
# verranno accesi. Nota: e' una cartella DENTRO la configurazione dell'utente
# (/config/hiris/models), fuori dall'add-on -- se un'installazione precedente
# ci ha scaricato un modello, quel file NON viene toccato da questa fetta.
export HF_HOME=/config/hiris/models/huggingface

# ── 6. Avanzate: registro, sicurezza, diagnostica ───────────────────────────
export LOG_LEVEL=$(bashio::config 'log_level' 'info')
export INTERNAL_TOKEN=$(bashio::config 'internal_token' '')
export SUPERVISOR_INGRESS_CIDR=$(bashio::config 'supervisor_ingress_cidr' '172.30.32.0/23')

# v0.10.11: debug expose port — logging only. Il port mapping effettivo è
# controllato dalla sezione Network in HA Settings → Add-ons → HIRIS.
# L'opzione qui sotto serve a ricordare all'utente di impostare e ripulire
# il port mapping, e a loggare un warning chiaro se attivo in produzione.
export HIRIS_DEBUG_EXPOSE_PORT=$(bashio::config 'debug_expose_port' 'false')
if [[ "$HIRIS_DEBUG_EXPOSE_PORT" == "true" ]]; then
  bashio::log.warning "============================================================"
  bashio::log.warning "🚨 DEBUG MODE ACTIVE — debug_expose_port=true"
  bashio::log.warning "Per esporre la porta sulla LAN: HA → Add-ons → HIRIS →"
  bashio::log.warning "Configuration → Network → '8099/tcp' = 8099 → Save → Restart"
  bashio::log.warning "ATTENZIONE: chiunque sulla LAN può chiamare /api/*"
  bashio::log.warning "(protetto solo da internal_token se settato). Solo HTTP, no HTTPS."
  bashio::log.warning "Disattiva debug_expose_port + svuota Network port quando finito."
  bashio::log.warning "============================================================"
fi

bashio::log.info "Starting HIRIS"
bashio::log.info "Log level: ${LOG_LEVEL}"
bashio::log.info "Theme: ${THEME}"
bashio::log.info "LLM strategy: ${LLM_STRATEGY}"

# Pre-flight sanity checks (review mediums): warn early instead of surfacing a
# cryptic runtime error later. Sono WARNING soltanto — l'add-on parte lo stesso.
if ! echo "${SUPERVISOR_INGRESS_CIDR}" | grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}([[:space:]]*,[[:space:]]*([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2})*$'; then
  bashio::log.warning "supervisor_ingress_cidr non sembra un CIDR valido (${SUPERVISOR_INGRESS_CIDR}); l'app ignora le voci non parsabili e usa il default."
fi

# «Il piano Claude Max e' davvero utilizzabile?» — stessa condizione che
# `server.py::should_start_agent_worker` usa per far partire il worker che
# risponde: un interruttore dell'abbonamento acceso E il token OAuth presente.
# Prima questo file usava la sola CHAT_VIA_SUBSCRIPTION, e il risultato era
# che accendere quell'interruttore SENZA token faceva TACERE l'avviso «non hai
# nessun provider»: l'utente restava senza chat e senza una riga che glielo
# dicesse. Un booleano solo, calcolato una volta, tiene i due avvisi coerenti.
PIANO_UTILIZZABILE="false"
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN}" ] \
   && { [ "${PROVIDER_SUBSCRIPTION}" = "true" ] || [ "${BRIDGE_ENABLED}" = "true" ]; }; then
  PIANO_UTILIZZABILE="true"
fi

# Il ponte acceso senza token e' il guasto silenzioso peggiore della pagina:
# la chat viene instradata a un runner che non parte mai, i messaggi restano
# in coda e scadono dopo bridge_deadline_min minuti, e l'utente vede solo
# errori di attesa senza nessun indizio sulla causa.
if [ -z "${CLAUDE_CODE_OAUTH_TOKEN}" ] \
   && { [ "${PROVIDER_SUBSCRIPTION}" = "true" ] || [ "${BRIDGE_ENABLED}" = "true" ]; }; then
  bashio::log.warning "Il piano Claude Max e' acceso ma «Provider · Piano Claude Max — token» e' vuoto: nessuno rispondera' ai messaggi instradati sul ponte, che scadranno dopo ${BRIDGE_DEADLINE_MIN} minuti. Incolla il token, oppure spegni il piano e il ponte."
fi

# Il complemento dell'avviso qui sopra, e la rete dell'annidamento della 2.4.0:
# il token del piano c'e', ma il ponte e' spento. E' esattamente lo stato in cui
# si ritrova chi aggiorna avendo usato il ponte SENZA `provider_subscription`:
# le sue opzioni hanno cambiato nome (annidate sotto `ponte:`, e i due
# interruttori fusi in uno) e il Supervisor ha scartato i valori, che non sa
# migrare. Senza questa riga la chat tornerebbe sul provider a consumo senza
# dirlo -- cioe' a pagare.
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN}" ] \
   && [ "${PROVIDER_SUBSCRIPTION}" != "true" ] && [ "${BRIDGE_ENABLED}" != "true" ]; then
  bashio::log.warning "Hai il token del piano Claude Max, ma il ponte e' spento: le risposte passano dal provider a consumo. Se aggiorni da una 2.x precedente, il ponte e' adesso un interruttore solo -- sezione «Ponte», «Accendi il ponte» -- e va riacceso una volta."
fi

if [ -z "${CLAUDE_API_KEY}" ] && [ -z "${OPENAI_API_KEY}" ] && [ -z "${OPENROUTER_API_KEY}" ] \
   && [ -z "${LOCAL_MODEL_URL}" ] && [ "${PIANO_UTILIZZABILE}" != "true" ]; then
  bashio::log.warning "Nessuna API key LLM, nessun modello locale e nessun piano Claude Max utilizzabile: la chat non potra' rispondere finche' non configuri un provider."
fi

cd /usr/lib/hiris
exec python3 -m app.main
