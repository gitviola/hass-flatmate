# Hass Flatmate Service

Backend API for the `hass_flatmate` custom integration.

## What it does
- Persists shopping list, favorites, and activity events
- Computes shopping fairness distribution + SVG chart
- Manages cleaning rotation, swaps, takeover completion, and compensation overrides
- Generates due cleaning notifications

## Configuration
- `api_token` (required): Shared token used by the integration via `x-flatmate-token` header.

## Network
- Exposes `8099/tcp` for internal Home Assistant usage.

## Storage
- SQLite DB at `/config/hass_flatmate_service/hass_flatmate.db`
- Stored on Supervisor persistent app/add-on config mount (`addon_config`), so it survives container restarts and image upgrades.

## Images
- `ghcr.io/gitviola/hass-flatmate-service-amd64`
- `ghcr.io/gitviola/hass-flatmate-service-aarch64`
