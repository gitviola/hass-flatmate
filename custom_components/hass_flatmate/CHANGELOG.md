# Hass Flatmate Integration Changelog

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
