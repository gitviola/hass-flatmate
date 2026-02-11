# Installation

## Install Home Assistant App Backend

1. Add this repository as an App/Add-on repository in Home Assistant.
2. Install `Hass Flatmate Service`.
3. Configure app option:
- `api_token`: shared token used by integration.
4. Start app.

Prebuilt images are pulled from:
- `ghcr.io/ms/hass-flatmate-service-amd64`
- `ghcr.io/ms/hass-flatmate-service-aarch64`

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
