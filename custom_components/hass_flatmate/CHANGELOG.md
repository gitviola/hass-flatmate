# Hass Flatmate Integration Changelog

## [Unreleased]

## [0.1.21] - 2026-02-12

### Changed
- Cleaning card swap UX now describes and previews a two-week shift exchange (selected week + return week) rather than a single-week replacement.
- Cleaning done/swap modal week labels now include relative timing hints (for example `in 2 weeks`) for clearer consequence previews.

### Fixed
- Cleaning schedule sensor now exposes `override_source` and labels manual compensation rows as swap-return weeks for clearer UI wording.
- Cleaning schedule sensor now exposes `source_week_start`, enabling concise swap-return notes like `Swapped with Martina 3 weeks ago`.

## [0.1.20] - 2026-02-12

### Changed
- Compact cleaning card layout now shows assignee name first and in stronger bold to improve glanceability on e-ink displays.
- Cleaning swap modal title/choices now explicitly say "one-time swap" to avoid recurring-swap ambiguity.

### Fixed
- Compact cleaning card week-context labels (`this week`, `previous week`, `next week`) now render in italic styling.
- Compact cleaning card note lines (for example `Done by ...`) now render in italic styling.
- Cleaning modal preview now details per-person notification outcomes with actor-aware wording.
- Shopping add-item input now remains stable while typing during frequent state updates (focus no longer drops unexpectedly).

## [0.1.19] - 2026-02-12

### Changed
- Cleaning completion and swap service handlers now schedule refresh/activity sync in the background for faster action response in the UI.

### Fixed
- Cleaning card now applies optimistic updates for done/undone/swap actions so rows update immediately without requiring manual page refresh.
- Cleaning override wording in card and sensor metadata is now user-friendly ("make-up shift") instead of technical compensation language.
- Compact cleaning card now marks the current week with a strong left border rather than the previous arrow marker.

## [0.1.18] - 2026-02-12

### Changed
- Manual import service now accepts `cleaning_override_rows` for planned compensation/swap migration entries.

### Fixed
- Manual import action now returns explicit backend error details instead of generic unknown-action errors.
- Added compatibility fallback to legacy import API route for mixed-version app/integration rollouts.

## [0.1.17] - 2026-02-11

### Changed
- Renamed manual migration service to `hass_flatmate_import_manual_data` with generic wording.
- Activity summary now labels migration events as `Manual data import applied`.

## [0.1.15] - 2026-02-11

### Fixed
- Cleaning schedule sensor now exposes only active flatmates in `members` metadata, so inactive users no longer show up in cleaning card member selectors.

## [0.1.14] - 2026-02-11

### Added
- New optional shopping-added push setting:
  - `switch.hass_flatmate_notify_shopping_item_added`
- New notification deep-link text entities:
  - `text.hass_flatmate_shopping_notification_link`
  - `text.hass_flatmate_cleaning_notification_link`
- New automation-friendly Home Assistant event bus triggers for activity:
  - `hass_flatmate_activity`
  - `hass_flatmate_activity_<action>`

### Changed
- Notification dispatcher now adds companion-friendly deep-link payload keys (`url` + `clickAction`) and mobile Open action buttons when links are configured.
- Cleaning notifications are dispatched with category metadata for cleaner grouping/tagging in mobile apps.

## [0.1.13] - 2026-02-11

### Fixed
- Shopping, cleaning, and distribution card editors now avoid full DOM re-renders on every `hass` update.
- Editor title/layout/entity inputs keep stable focus/value while editing in dashboard edit mode (no flicker/reopen behavior).

## [0.1.12] - 2026-02-11

### Changed
- Distribution card now supports `layout: compact` for a single-row boxed style and keeps `layout: bars` as default.
- Distribution card wording updated to purchases (`N purchases`) with subtitle `Based on data of the last 90 days`.
- Removed percentage labels and `Window: 90d` chip from distribution card UI.
- Cleaning card now supports `layout: compact` read-only rendering for e-ink/non-touch dashboards.
- `hass_flatmate_sync_members` now dispatches notifications returned by member-sync cleanup (for auto-canceled overrides).
- Shopping card add-item flow now uses optimistic UI (pending rows shown instantly while save completes).
- Shopping suggestions now follow backend-ranked recents/favorites ordering (frequency-first) instead of local favorites-first merging.
- Shopping remove service wording now clarifies "remove from list" (historical trace kept).
- Cleaning card done flow now supports non-assignee confirmation via modal:
  - confirm assignee completed
  - record takeover completion with compensation behavior
- Cleaning card no longer exposes swap actions in the UI (swap still available via service calls/automations).
- Compact cleaning card now renders responsively with stacked rows, `Upcoming` status for future weeks, and reduced redundant header text.

### Added
- New HA service `hass_flatmate_import_manual_data` for pasted migration rows:
  - rotation seed rows (`date,member_name`)
  - optional cleaning history rows
  - optional shopping history rows

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
