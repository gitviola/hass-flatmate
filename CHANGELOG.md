# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added
- Auto-registration of the shopping custom card Lovelace resource in storage mode.
- Shopping card editor support for dashboard UI card picker configuration.
- Sections-based dashboard example aligned with modern Home Assistant layout.
- Dedicated changelog files for the repository, integration, and app package.

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
