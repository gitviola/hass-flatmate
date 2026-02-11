# Hass Flatmate Service App Changelog

## [Unreleased]

## [0.1.11] - 2026-02-11

### Fixed
- Shopping complete/delete actions are idempotent for already-updated items.
- Shopping distribution SVG always includes all active flatmates in the rendered chart, including zero-count members.
- Cleaning schedule API rows now include assignment `status`, `completed_by_member_id`, and `completion_mode`.
- Cleaning swap cancel no longer fails with HTTP 500 when canceled swap history for the same week already exists.
- Swap validation now rejects `member_a_id == member_b_id`.

### Added
- `POST /v1/cleaning/mark_undone` to revert week completion state to pending.
- `GET /v1/cleaning/schedule` support for `include_previous_weeks`.
- Swap notification messages now include original assignee context for the week.
- `PUT /v1/members/sync` now auto-cancels planned cleaning overrides that involve deactivated members and returns notifications for remaining affected flatmates.

## [0.1.10] - 2026-02-11

### Added
- App branding assets for Home Assistant app store rendering:
  - `icon.png`
  - `logo.png`
- App version bump to align with repository release tag and publish workflow validation.

## [0.1.5] - 2026-02-11

### Changed
- Current stable app package release.
- Compatible with integration updates through `0.1.8`.

## [0.1.4] - 2026-02-11

### Changed
- App package version bump for release alignment.

## [0.1.3] - 2026-02-11

### Fixed
- GHCR image naming for Home Assistant app pulls.

## [0.1.2] - 2026-02-11

### Fixed
- App image path and GHCR publish validation.

## [0.1.1] - 2026-02-11

### Added
- Initial public GHCR publishing flow for app images.
