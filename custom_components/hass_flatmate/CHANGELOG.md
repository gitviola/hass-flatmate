# Hass Flatmate Integration Changelog

## [Unreleased]

### Changed
- Distribution card now supports `layout: compact` for a single-row boxed style and keeps `layout: bars` as default.
- Distribution card wording updated to purchases (`N purchases`) with subtitle `Based on data of the last 90 days`.
- Removed percentage labels and `Window: 90d` chip from distribution card UI.

## [0.1.11] - 2026-02-11

### Fixed
- Shopping service actions now return faster by running refresh/activity-calendar sync in a background coalesced task.
- Shopping card now optimistically hides pending completed/deleted items to avoid repeated clicks during backend updates.
- Cleaning swap cancel no longer returns HTTP 500 when canceling after prior canceled swap history exists.
- Swap dialog close controls now work reliably.
- Cleaning card requests immediate entity refresh after done/undone and swap actions, removing the need for full dashboard reloads.
- Swap creation now rejects same-member swaps.

### Added
- New custom cleaning card (`custom:hass-flatmate-cleaning-card`) with:
  - Friendly schedule timeline
  - Done-state visuals
  - In-card mark-done action
  - Swap override modal UX
- New custom distribution card (`custom:hass-flatmate-distribution-card`) with native bar rendering from shopping distribution sensor attributes.
- Auto-registration of cleaning card frontend resource and card picker metadata.
- Auto-registration of distribution card frontend resource and card picker metadata.
- `sensor.hass_flatmate_cleaning_schedule` attributes extended with:
  - per-week `status`, `completed_by_*`, `completion_mode`
  - member list metadata for swap UI
  - cleaning service metadata for card actions
- New `hass_flatmate_mark_cleaning_undone` service and in-card Undo action for done current/previous weeks.
- Cleaning schedule API consumption now includes one previous week, plus `original_assignee_*` fields for clearer card labels and swap preview.

## [0.1.10] - 2026-02-11

### Added
- Integration branding icon asset (`icon.png`) for improved presentation in Home Assistant UI surfaces.

## [0.1.9] - 2026-02-11

### Fixed
- Calendar event timezone normalization to avoid `Expected all values to have a timezone` failures.
- Shopping card input behavior in dashboard mode to prevent accidental entity-picker style interactions.

### Added
- Select entities to choose target calendars for mirrored activity events:
  - `select.hass_flatmate_shopping_calendar_target`
  - `select.hass_flatmate_cleaning_calendar_target`
- Mirroring of new shopping/cleaning completion events to selected calendar targets.
- Human-readable activity summaries with actor names in `sensor.hass_flatmate_activity_recent` (`recent_human`).
- `sensor.hass_flatmate_cleaning_schedule` with concise upcoming weeks metadata for card/table rendering.

### Changed
- Shopping card redesigned as todo-style flow:
  - Open items first
  - Check-circle completion action
  - Delete with confirmation
  - Relative “added … ago” text
  - Add-item input moved below list with suggestions
  - “Recent items” quick-add chips (no favorites UI actions)

## [0.1.8] - 2026-02-11

### Added
- Automatic Lovelace resource registration for `/hass_flatmate/static/hass-flatmate-shopping-card.js` in storage mode.
- Card editor support so `custom:hass-flatmate-shopping-card` can be configured from the dashboard UI card picker.
- Improved custom card gallery metadata for easier discovery.

### Changed
- Dashboard example moved to modern Sections layout.

## [0.1.7] - 2026-02-11

### Fixed
- `ShoppingDistributionImage` now initializes `ImageEntity` correctly, fixing missing `access_tokens` errors.
- Shopping input field no longer triggers unintended picker behavior.

## [0.1.6] - 2026-02-11

### Added
- Migration of old unprefixed entity IDs to `hass_flatmate_*` IDs on setup.

## [0.1.5] - 2026-02-11

### Added
- Notification test mode entities:
  - `switch.hass_flatmate_notification_test_mode`
  - `select.hass_flatmate_notification_test_target`
- Shopping data sensor for frontend card use.
- Custom shopping card static asset serving endpoint.

## [0.1.0] - 2026-02-11

### Added
- Initial integration entities, services, coordinator, image and calendar platforms.
