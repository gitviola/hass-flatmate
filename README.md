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
- Safe notification test mode (redirect all notifications to one selected user)

## One-Click Install

### Home Assistant App (backend)

[![Add app repository to your Home Assistant instance.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fgitviola%2Fhass-flatmate)
[![Show app on your Home Assistant instance.](https://my.home-assistant.io/badges/supervisor_addon.svg)](https://my.home-assistant.io/redirect/supervisor_addon/?addon=hass_flatmate_service&repository_url=https%3A%2F%2Fgithub.com%2Fgitviola%2Fhass-flatmate)

### HACS integration

[![Open HACS repository on your Home Assistant instance.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gitviola&repository=hass-flatmate&category=integration)

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
   - `base_url`: service URL (default `http://ebc95cb1-hass-flatmate-service:8099`)
   - `api_token`: same value from app config
5. In Lovelace storage mode, the shopping card resource is auto-registered.
6. Add cards/entities from `examples/lovelace-flatmate-dashboard.yaml` (Sections dashboard format).

## Shopping UI Card

Use the custom card in any dashboard:

```yaml
type: custom:hass-flatmate-shopping-card
entity: sensor.hass_flatmate_shopping_data
title: Shared Shopping
```

You can also add it from the dashboard UI card picker (no manual YAML required).

Features:
- Add shopping items fast
- Mark item done / delete item
- Quick add from favorites and recents
- Add/remove favorites

The card uses integration services, so actor attribution stays correct.
In Lovelace YAML resource mode, add this resource manually: `/hass_flatmate/static/hass-flatmate-shopping-card.js` as `module`.

## Notification Test Mode

Use these entities to test all flows without notifying everyone:
- `switch.hass_flatmate_notification_test_mode`
- `select.hass_flatmate_notification_test_target`
- `select.hass_flatmate_shopping_calendar_target`
- `select.hass_flatmate_cleaning_calendar_target`

When test mode is enabled, all notifications are redirected to the selected target and prefixed with `[TEST]`.

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
- Shopping custom card JavaScript syntax check
- Home Assistant app test build (via `home-assistant/builder`)
- Sync guard for `apps/hass_flatmate_service/service_src`

## Image Publishing (GHCR)

App images are published automatically to GHCR by GitHub Actions:
- Workflow: `.github/workflows/publish-app.yml`
- Trigger: git tag push like `v0.1.1` (also supports Release `published` and manual `workflow_dispatch`)
- Registry image: `ghcr.io/gitviola/hass-flatmate-service-{arch}`
- Architectures: `amd64`, `aarch64`

Release/tag version must match `apps/hass_flatmate_service/config.yaml` `version`.

## Changelogs

- Repo changelog: `/CHANGELOG.md`
- Integration changelog: `/custom_components/hass_flatmate/CHANGELOG.md`
- App changelog: `/apps/hass_flatmate_service/CHANGELOG.md`

## Syncing App Build Source

When backend code changes in `addon/hass_flatmate_service`, sync mirror source used by app Docker build:

```bash
./scripts/sync_app_service_src.sh
```
