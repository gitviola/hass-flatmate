# Installation

## One-click links

### Home Assistant App (backend)
[![Add app repository to your Home Assistant instance.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fgitviola%2Fhass-flatmate)
[![Show app on your Home Assistant instance.](https://my.home-assistant.io/badges/supervisor_addon.svg)](https://my.home-assistant.io/redirect/supervisor_addon/?addon=hass_flatmate_service&repository_url=https%3A%2F%2Fgithub.com%2Fgitviola%2Fhass-flatmate)

### HACS integration
[![Open HACS repository on your Home Assistant instance.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gitviola&repository=hass-flatmate&category=integration)

## Install Home Assistant App Backend

1. Add this repository as an App/Add-on repository in Home Assistant.
2. Install `Hass Flatmate Service`.
3. Configure app option:
- `api_token`: shared token used by integration.
4. Start app.

The app is built locally from this repository Dockerfile during installation/update.

## Install HACS Integration

1. Add this repository to HACS custom repositories.
2. Install integration `Hass Flatmate`.
3. Restart Home Assistant.
4. Add integration via UI and configure:
- Base URL of backend (for example `http://homeassistant.local:8099`)
- Same `api_token` used in app.

## Validate

1. Call service `hass_flatmate.sync_members`.
2. Confirm entities appear:
- `sensor.hass_flatmate_shopping_open_count`
- `sensor.hass_flatmate_shopping_distribution_90d`
- `image.hass_flatmate_shopping_distribution_90d`
- `sensor.hass_flatmate_cleaning_current_assignee`
- `calendar.hass_flatmate_activity`
