# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Changed
- Distribution custom card now supports two layouts via config:
  - `layout: bars` (default app-style bars)
  - `layout: compact` (single-row boxed layout for compact/e-ink dashboards)
- Distribution card text updated to purchase-focused wording:
  - `N purchases` instead of `N done`
  - `Based on data of the last 90 days` subtitle
  - Removed explicit `Window: 90d` chip
- Bar layout no longer shows percentage labels.

## [0.1.11] - 2026-02-11

### Fixed
- Shopping interactions are now much faster in the dashboard by decoupling post-action coordinator/calendar sync from service call completion.
- Duplicate shopping complete/delete clicks are now idempotent instead of returning HTTP 400 for already-updated items.
- Shopping distribution SVG now always renders all active flatmates, including zero-count members, even when one member has all completions.
- Cleaning swap cancel no longer errors with HTTP 500 when a canceled swap already exists for the same week.
- Cleaning card swap dialog close controls now work reliably.
- Cleaning card refreshes immediately after done/undone and swap actions, so manual page refresh is no longer required.
- Swap validation now rejects selecting the same member on both sides.

### Added
- Dedicated cleaning dashboard card with:
  - Week-based schedule view (`This week`, `Next week`, etc.)
  - Done/pending/missed status visuals
  - In-card mark-done action
  - Week-specific swap override modal with member selectors and preview
- Automatic Lovelace resource registration for cleaning card JS (`/hass_flatmate/static/hass-flatmate-cleaning-card.js`) in storage mode.
- Dedicated shopping distribution dashboard card (`custom:hass-flatmate-distribution-card`) to replace SVG image card dependency.
- Automatic Lovelace resource registration for distribution card JS (`/hass_flatmate/static/hass-flatmate-distribution-card.js`) in storage mode.
- Cleaning schedule payload now includes per-week assignment status/completion metadata for richer UI rendering.
- Cleaning undo flow:
  - New API endpoint: `POST /v1/cleaning/mark_undone`
  - New HA service: `hass_flatmate_mark_cleaning_undone`
  - In-card Undo action for done current/previous weeks
- Cleaning schedule now includes previous-week context and `original_assignee_*` metadata for clearer swap UX.

## [0.1.10] - 2026-02-11

### Added
- Integration 0.1.9 updates:
- Calendar timezone normalization for event validation.
- Calendar target selectors and mirrored activity-event writes.
- Human-readable recent activity summaries with actor names.
- Todo-style shopping card refresh with relative added times and suggestions.
- Cleaning schedule sensor and improved Sections dashboard example cards.
- Repository branding assets for automatic HACS/app store display:
- `/icon.png`
- `/logo.png`
- `/custom_components/hass_flatmate/icon.png`
- `/apps/hass_flatmate_service/icon.png`
- `/apps/hass_flatmate_service/logo.png`

## [0.1.7] - 2026-02-11

### Fixed
- Correct `ImageEntity` initialization for shopping distribution image token handling.
- Shopping card input behavior to avoid unwanted picker UI while adding items.

## [0.1.6] - 2026-02-11

### Added
- Automatic migration from legacy unprefixed entity IDs to `hass_flatmate_*` IDs.

## [0.1.5] - 2026-02-11

### Added
- Notification test mode with switch/select entities to redirect notifications safely.
- Custom shopping card with add/complete/delete and quick-add workflows.
- Shopping data sensor for card-friendly attributes.
- Internal static hosting for custom card JavaScript.
- CI syntax check for shopping card JavaScript.

### Changed
- Default backend URL to `http://ebc95cb1-hass-flatmate-service:8099`.

## [0.1.4] - 2026-02-11

### Changed
- App package version bump to `0.1.4`.

## [0.1.3] - 2026-02-11

### Fixed
- GHCR image naming for Home Assistant app publishing.

## [0.1.2] - 2026-02-11

### Fixed
- Home Assistant app image path and GHCR publish checks.

## [0.1.1] - 2026-02-11

### Added
- Initial app publishing flow on version tags and install UX badges.
