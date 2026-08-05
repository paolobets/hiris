#!/usr/bin/with-contenv bashio

export LOG_LEVEL=$(bashio::config 'log_level' 'info')
export CLAUDE_API_KEY=$(bashio::config 'claude_api_key')
export OPENAI_API_KEY=$(bashio::config 'openai_api_key' '')
export OPENROUTER_API_KEY=$(bashio::config 'openrouter_api_key' '')
export LLM_STRATEGY=$(bashio::config 'llm_strategy' 'balanced')
export AUTOMATIC_POLICY=$(bashio::config 'automatic_policy' '')
# SP-2: attivazione provider esplicita. Default false su tutti => l'app
# migra derivando gli attivi dalle credenziali presenti (retro-compat).
export PROVIDER_SUBSCRIPTION=$(bashio::config 'provider_subscription' 'false')
export PROVIDER_CLAUDE=$(bashio::config 'provider_claude' 'false')
export PROVIDER_OPENAI=$(bashio::config 'provider_openai' 'false')
export PROVIDER_OPENROUTER=$(bashio::config 'provider_openrouter' 'false')
export PROVIDER_OLLAMA=$(bashio::config 'provider_ollama' 'false')
export CHAT_POLICY=$(bashio::config 'chat_policy' '')
# Hide :free OpenRouter models from the model dropdown. Useful for users
# with paid credit who want to avoid the low daily quota / upstream
# rate-limits that come with the free tier.
export HIRIS_HIDE_FREE_MODELS=$(bashio::config 'hide_free_models' 'false')
export THEME=$(bashio::config 'theme' 'auto')
export INTERNAL_TOKEN=$(bashio::config 'internal_token' '')
export AGENT_OWNER=$(bashio::config 'agent_owner' '')
export EXECUTE_API_TOOLS=$(bashio::config 'execute_api_tools' '')
export EXECUTE_API_ENTITIES=$(bashio::config 'execute_api_entities' '')
export EXECUTE_API_SERVICES=$(bashio::config 'execute_api_services' '')
# Denylist di lettura del gateway. Qui serve distinguere due casi che
# bashio::config confonde (restituisce '' per entrambi):
#   - opzione ASSENTE  -> la variabile resta non esportata e l'app applica il
#                         default protettivo (lock/allarme/telecamere/presenze);
#   - opzione SVUOTATA -> si esporta '' e la denylist e' vuota, cioe' il
#                         comportamento precedente, che deve restare esprimibile.
# Stesso accesso diretto a options.json gia' usato qui sotto per apprise_urls.
if jq -e 'has("execute_api_read_denylist")' /data/options.json >/dev/null 2>&1; then
  export EXECUTE_API_READ_DENYLIST=$(bashio::config 'execute_api_read_denylist' '')
fi
export SUPERVISOR_INGRESS_CIDR=$(bashio::config 'supervisor_ingress_cidr' '172.30.32.0/23')
export INTERNAL_MCP_PORT=$(bashio::config 'internal_mcp_port' '8199')
# Guard the jq parse (review medium): a malformed options.json used to silently
# blank APPRISE_URLS with no hint. Warn and fall back to an empty list.
export APPRISE_URLS=$(jq -c '.apprise_urls // []' /data/options.json 2>/dev/null)
if [ -z "${APPRISE_URLS}" ]; then
  bashio::log.warning "Impossibile leggere apprise_urls da options.json — notifiche Apprise disattivate."
  export APPRISE_URLS="[]"
fi
export HISTORY_RETENTION_DAYS=$(bashio::config 'history_retention_days' '90')

export SENTINEL_DAILY_CAP=$(bashio::config 'sentinel_daily_cap' '20')
export SENTINEL_COOLDOWN_SEC=$(( $(bashio::config 'sentinel_cooldown_min' '30') * 60 ))
export SENTINEL_ALLOW_GREEN_AUTO=$(bashio::config 'sentinel_allow_green_auto' 'false')
export SENTINEL_RONDA_MINUTES=$(bashio::config 'sentinel_ronda_min' '15')

# Notifica push per le segnalazioni gravi nuove o riaperte della scansione di
# salute (Brain). Attiva per impostazione predefinita.
export BRAIN_NOTIFY_HIGH=$(bashio::config 'brain_notify_high' 'true')

export BRIDGE_ENABLED=$(bashio::config 'bridge_enabled' 'false')
export BRIDGE_DEADLINE_MIN=$(bashio::config 'bridge_deadline_min' '5')
export BRIDGE_FALLBACK=$(bashio::config 'bridge_fallback' 'true')
export CHAT_DAILY_CAP=$(bashio::config 'chat_daily_cap' '50')
export CHAT_VIA_SUBSCRIPTION=$(bashio::config 'chat_via_subscription' 'false')
export CLAUDE_CODE_OAUTH_TOKEN=$(bashio::config 'claude_code_oauth_token' '')
export CLAUDE_CONFIG_DIR=/data/claude

export LOCAL_MODEL_URL=$(bashio::config 'local_model.url' '')
export LOCAL_MODEL_NAME=$(bashio::config 'local_model.model' '')
# Per-request HTTP timeout for the Ollama backend, in seconds. Default 120.
# Bump for slow hardware running large local models (gemma4:e4b on Pi5 may
# need 240–300s before completion).
export OLLAMA_REQUEST_TIMEOUT=$(bashio::config 'local_model.request_timeout' '120')

export MQTT_HOST=$(bashio::config 'mqtt.host' '')
export MQTT_PORT=$(bashio::config 'mqtt.port' '1883')
export MQTT_USER=$(bashio::config 'mqtt.user' '')
export MQTT_PASSWORD=$(bashio::config 'mqtt.password' '')

export MEMORY_EMBEDDING_PROVIDER=$(bashio::config 'memory.embedding_provider' '')
export MEMORY_EMBEDDING_MODEL=$(bashio::config 'memory.embedding_model' '')
export MEMORY_RAG_K=$(bashio::config 'memory.rag_k' '5')

export MAYAN_URL=$(bashio::config 'mayan.url' '')
export MAYAN_TOKEN=$(bashio::config 'mayan.token' '')
export MAYAN_TAG_ID=$(bashio::config 'mayan.tag_id' '0')
export MAYAN_SENSITIVITY=$(bashio::config 'mayan.sensitivity' 'sensitive')
export MAYAN_POLL_MINUTES=$(bashio::config 'mayan.poll_minutes' '60')

# HuggingFace model cache → persistent HA config directory
export HF_HOME=/config/hiris/models/huggingface

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
# cryptic runtime error later. Both are WARNINGS only — the addon still boots.
if ! echo "${SUPERVISOR_INGRESS_CIDR}" | grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}([[:space:]]*,[[:space:]]*([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2})*$'; then
  bashio::log.warning "supervisor_ingress_cidr non sembra un CIDR valido (${SUPERVISOR_INGRESS_CIDR}); l'app ignora le voci non parsabili e usa il default."
fi
if [ -z "${CLAUDE_API_KEY}" ] && [ -z "${OPENAI_API_KEY}" ] && [ -z "${OPENROUTER_API_KEY}" ] \
   && [ -z "${LOCAL_MODEL_URL}" ] && [ "${CHAT_VIA_SUBSCRIPTION}" != "true" ]; then
  bashio::log.warning "Nessuna API key LLM, nessun modello locale e chat-via-abbonamento non attiva: la chat non potra' rispondere finche' non configuri un provider."
fi

cd /usr/lib/hiris
exec python3 -m app.main
