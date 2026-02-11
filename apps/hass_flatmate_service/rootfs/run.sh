#!/usr/bin/with-contenv bashio
set -euo pipefail

API_TOKEN="$(bashio::config 'api_token')"
DB_PATH="/config/hass_flatmate_service/hass_flatmate.db"

export HASS_FLATMATE_API_TOKEN="${API_TOKEN}"
export HASS_FLATMATE_DB_PATH="${DB_PATH}"
export HASS_FLATMATE_HOST="0.0.0.0"
export HASS_FLATMATE_PORT="8099"

bashio::log.info "Starting hass-flatmate service"
python3 /opt/hass_flatmate/run.py
