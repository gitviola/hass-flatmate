# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Fixed
- Shopping interactions are now much faster in the dashboard by decoupling post-action coordinator/calendar sync from service call completion.
- Duplicate shopping complete/delete clicks are now idempotent instead of returning HTTP 400 for already-updated items.
- Shopping distribution SVG now always renders all active flatmates, including zero-count members, even when one member has all completions.

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
