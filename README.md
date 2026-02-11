# Hass Flatmate

Home Assistant-native flat-sharing toolkit with two parts:

- `custom_components/hass_flatmate`: HACS custom integration
- `apps/hass_flatmate_service`: Home Assistant App (formerly add-on) backend service

It replaces the used Flatastic features with:

- Shopping list actions (add, complete, delete)
- Fairness distribution (90-day) + SVG chart image
- Weekly cleaning rotation with temporary swaps
- Takeover completion with automatic compensation override
- Home Assistant calendar activity events
- Built-in notification scheduling (Monday + Sunday reminders)

## Repository Layout

- `/custom_components/hass_flatmate`: install via HACS (custom repository)
- `/apps/hass_flatmate_service`: install via Home Assistant App repository
- `/addon/hass_flatmate_service`: canonical backend source + tests
- `/apps/hass_flatmate_service/service_src`: app build source mirror (synced from `addon/`)

## Quick Start

1. Install app from this repository (`apps/hass_flatmate_service`) in Home Assistant.
2. Set app option `api_token`.
3. Install custom integration via HACS from this repository.
4. Configure integration with:
   - `base_url`: service URL (typically `http://<home-assistant-host>:8099`)
   - `api_token`: same value from app config
5. Add entities/cards from `examples/lovelace-flatmate-dashboard.yaml`.

## Automated Tests

Backend tests run locally without Home Assistant:

```bash
cd addon/hass_flatmate_service
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest
```

CI also runs on every push/PR:
- Backend test suite
- Integration compile check
- Home Assistant app test build (via `home-assistant/builder`)
- Sync guard for `apps/hass_flatmate_service/service_src`

## Image Publishing (GHCR)

App images are published automatically to GHCR by GitHub Actions:
- Workflow: `.github/workflows/publish-app.yml`
- Trigger: GitHub Release `published` (or manual `workflow_dispatch`)
- Registry image: `ghcr.io/ms/hass-flatmate-service-{arch}`
- Architectures: `amd64`, `aarch64`

Release/tag version must match `apps/hass_flatmate_service/config.yaml` `version`.

## Syncing App Build Source

When backend code changes in `addon/hass_flatmate_service`, sync mirror source used by app Docker build:

```bash
./scripts/sync_app_service_src.sh
```
