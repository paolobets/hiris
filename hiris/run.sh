#!/usr/bin/with-contenv bashio

export LOG_LEVEL=$(bashio::config 'log_level' 'info')
export CLAUDE_API_KEY=$(bashio::config 'claude_api_key')
export OPENAI_API_KEY=$(bashio::config 'openai_api_key' '')
export PRIMARY_MODEL=$(bashio::config 'primary_model' 'claude-sonnet-4-6')
export LLM_STRATEGY=$(bashio::config 'llm_strategy' 'balanced')
export THEME=$(bashio::config 'theme' 'auto')
export INTERNAL_TOKEN=$(bashio::config 'internal_token' '')
export APPRISE_URLS=$(bashio::config --raw 'apprise_urls' '[]')
export HISTORY_RETENTION_DAYS=$(bashio::config 'history_retention_days' '90')

export LOCAL_MODEL_URL=$(bashio::config 'local_model.url' '')
export LOCAL_MODEL_NAME=$(bashio::config 'local_model.model' '')

export MQTT_HOST=$(bashio::config 'mqtt.host' '')
export MQTT_PORT=$(bashio::config 'mqtt.port' '1883')
export MQTT_USER=$(bashio::config 'mqtt.user' '')
export MQTT_PASSWORD=$(bashio::config 'mqtt.password' '')

export MEMORY_EMBEDDING_PROVIDER=$(bashio::config 'memory.embedding_provider' '')
export MEMORY_EMBEDDING_MODEL=$(bashio::config 'memory.embedding_model' '')
export MEMORY_RAG_K=$(bashio::config 'memory.rag_k' '5')
export MEMORY_RETENTION_DAYS=$(bashio::config 'memory.retention_days' '90')

bashio::log.info "Starting HIRIS"
bashio::log.info "Log level: ${LOG_LEVEL}"
bashio::log.info "Theme: ${THEME}"
bashio::log.info "Primary model: ${PRIMARY_MODEL}"
bashio::log.info "LLM strategy: ${LLM_STRATEGY}"

cd /usr/lib/hiris
exec python3 -m app.main
