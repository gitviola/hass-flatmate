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

Prebuilt images are pulled from:
- `ghcr.io/gitviola/hass-flatmate-service-amd64`
- `ghcr.io/gitviola/hass-flatmate-service-aarch64`

If install fails with GHCR `403 denied`, ensure package visibility is `public` in GitHub Packages for both architecture images.

## Install HACS Integration

1. Add this repository to HACS custom repositories.
2. Install integration `Hass Flatmate`.
3. Restart Home Assistant.
4. Add integration via UI and configure:
- Base URL of backend (default `http://ebc95cb1-hass-flatmate-service:8099`)
- Same `api_token` used in app.

## Custom Card Resources

Lovelace storage mode:
- Resources are auto-registered by the integration.

Lovelace YAML resources mode:
1. Open dashboard resources.
2. Add resources:
- URL: `/hass_flatmate/static/hass-flatmate-shopping-card.js` | Type: `module`
- URL: `/hass_flatmate/static/hass-flatmate-cleaning-card.js` | Type: `module`
- URL: `/hass_flatmate/static/hass-flatmate-distribution-card.js` | Type: `module`
3. Save.

## Dashboard Layout

Use the example Sections dashboard for modern HA layout:
- `examples/lovelace-flatmate-dashboard.yaml`

Custom cards available in the dashboard card picker:
- `custom:hass-flatmate-shopping-card`
- `custom:hass-flatmate-cleaning-card`
- `custom:hass-flatmate-distribution-card`

## Validate

1. Call service `hass_flatmate.hass_flatmate_sync_members`.
2. Confirm entities appear:
- `sensor.hass_flatmate_shopping_open_count`
- `sensor.hass_flatmate_shopping_data`
- `sensor.hass_flatmate_shopping_distribution_90d`
- `image.hass_flatmate_shopping_distribution_90d`
- `sensor.hass_flatmate_cleaning_current_assignee`
- `sensor.hass_flatmate_cleaning_schedule`
- `calendar.hass_flatmate_activity`

## Safe Notification Testing

1. Set `select.hass_flatmate_notification_test_target` to your member.
2. Turn on `switch.hass_flatmate_notification_test_mode`.
3. Run manual tests (swap/takeover/reminders).
4. Turn off test mode before house rollout.

Optional calendar mirroring targets:
- `select.hass_flatmate_shopping_calendar_target`
- `select.hass_flatmate_cleaning_calendar_target`
