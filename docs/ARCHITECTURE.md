# Architecture

## Components

1. Home Assistant App (`apps/hass_flatmate_service`)
- Runs FastAPI + SQLite service on port `8099`.
- Stores all domain state.
- Published for `amd64` and `aarch64` only.

2. Custom Integration (`custom_components/hass_flatmate`)
- Exposes HA services/entities/image/calendar.
- Syncs HA users/persons into service members.
- Dispatches notifications through HA notify services.

## Data Ownership

Service owns:
- members
- shopping_items
- shopping_favorites
- activity_events
- rotation_config
- cleaning_assignments
- cleaning_overrides

Integration owns:
- polling coordinator cache
- HA entity representations
- HA service endpoints and call context mapping

## Notification Flow

1. Integration triggers due-check every minute.
2. Service returns notifications due for the exact minute.
3. Integration dispatches returned payloads via `notify.*` services.

## Calendar Flow

1. Service stores completion activity events.
2. Integration calendar entity maps activity events to 15-minute calendar entries.
