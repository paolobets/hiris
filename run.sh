#!/usr/bin/with-contenv bashio

export LOG_LEVEL=$(bashio::config 'log_level' 'info')
export CLAUDE_API_KEY=$(bashio::config 'claude_api_key')

bashio::log.info "Starting HIRIS v0.1.0"
bashio::log.info "Log level: ${LOG_LEVEL}"

cd /usr/lib/hiris
exec python3 -m app.main
