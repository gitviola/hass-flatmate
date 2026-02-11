#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

rsync -a --delete \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  "${ROOT_DIR}/addon/hass_flatmate_service/" \
  "${ROOT_DIR}/apps/hass_flatmate_service/service_src/"

echo "Synced addon/hass_flatmate_service -> apps/hass_flatmate_service/service_src"
