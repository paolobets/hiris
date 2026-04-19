#!/usr/bin/with-contenv bashio

export LOG_LEVEL=$(bashio::config 'log_level' 'info')
export CLAUDE_API_KEY=$(bashio::config 'claude_api_key')
export RESTRICT_CHAT_TO_HOME=$(bashio::config 'restrict_chat_to_home' 'false')

bashio::log.info "Starting HIRIS v0.0.3"
bashio::log.info "Log level: ${LOG_LEVEL}"
bashio::log.info "Restrict chat to home: ${RESTRICT_CHAT_TO_HOME}"

cd /usr/lib/hiris
exec python3 -m app.main
