#!/usr/bin/with-contenv bashio

export LOG_LEVEL=$(bashio::config 'log_level' 'info')
export CLAUDE_API_KEY=$(bashio::config 'claude_api_key')
export THEME=$(bashio::config 'theme' 'auto')
export PRIMARY_MODEL=$(bashio::config 'primary_model' 'claude-sonnet-4-6')
export LOCAL_MODEL_URL=$(bashio::config 'local_model_url' '')
export LOCAL_MODEL_NAME=$(bashio::config 'local_model_name' '')
export INTERNAL_TOKEN=$(bashio::config 'internal_token' '')
export MQTT_HOST=$(bashio::config 'mqtt_host' '')
export MQTT_PORT=$(bashio::config 'mqtt_port' '1883')
export MQTT_USER=$(bashio::config 'mqtt_user' '')
export MQTT_PASSWORD=$(bashio::config 'mqtt_password' '')
export APPRISE_URLS=$(bashio::config --raw 'apprise_urls' '[]')
export OPENAI_API_KEY=$(bashio::config 'openai_api_key' '')
export MEMORY_EMBEDDING_PROVIDER=$(bashio::config 'memory_embedding_provider' '')
export MEMORY_EMBEDDING_MODEL=$(bashio::config 'memory_embedding_model' '')
export MEMORY_RAG_K=$(bashio::config 'memory_rag_k' '5')
export MEMORY_RETENTION_DAYS=$(bashio::config 'memory_retention_days' '90')
export HISTORY_RETENTION_DAYS=$(bashio::config 'history_retention_days' '90')

bashio::log.info "Starting HIRIS"
bashio::log.info "Log level: ${LOG_LEVEL}"
bashio::log.info "Theme: ${THEME}"
bashio::log.info "Primary model: ${PRIMARY_MODEL}"

cd /usr/lib/hiris
exec python3 -m app.main
