#!/usr/bin/with-contenv bashio

export LOG_LEVEL=$(bashio::config 'log_level' 'info')
export CLAUDE_API_KEY=$(bashio::config 'claude_api_key')
export THEME=$(bashio::config 'theme' 'auto')

bashio::log.info "Starting HIRIS"
bashio::log.info "Log level: ${LOG_LEVEL}"
bashio::log.info "Theme: ${THEME}"

cd /usr/lib/hiris
exec python3 -m app.main
