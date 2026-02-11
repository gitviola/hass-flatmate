# Testing

## Local backend tests

```bash
cd addon/hass_flatmate_service
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest
```

Current suite covers:
- Shopping lifecycle + stats + unknown actor exclusion
- Recents/favorites behavior
- SVG rendering endpoint
- Cleaning rotation, manual swaps, takeover completion
- Compensation override auto-planning and conflict handling
- Monday/Sunday notification schedule behavior

CI additionally runs a Home Assistant app test build using `home-assistant/builder@2025.11.0` for `amd64` and `aarch64`.
CI also validates custom shopping card JavaScript syntax.

## Fast feedback workflow

1. Implement/change backend code in `addon/hass_flatmate_service`.
2. Run local tests.
3. Sync app build mirror:
   - `./scripts/sync_app_service_src.sh`
4. Build/deploy app in Home Assistant only after tests pass.
