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

bashio::log.info "Starting HIRIS"
bashio::log.info "Log level: ${LOG_LEVEL}"
bashio::log.info "Theme: ${THEME}"
bashio::log.info "Primary model: ${PRIMARY_MODEL}"

cd /usr/lib/hiris
exec python3 -m app.main
