# Hass Flatmate Service App Changelog

## [Unreleased]

## [0.1.21] - 2026-02-12

### Changed
- `POST /v1/cleaning/overrides/swap` now applies a true two-week shift exchange by adding a linked return-week override automatically.
- Swap cancel now removes both linked weeks in the exchange and restores baseline assignment for both.

### Fixed
- `GET /v1/cleaning/schedule` now includes `source_week_start` for linked compensation rows so clients can show clear swap-return timing context.

## [0.1.20] - 2026-02-12

### Changed
- Swap and make-up-shift push notifications now include actor-aware context and clearer one-time action wording.

## [0.1.19] - 2026-02-12

### Changed
- Compensation notification text now uses clearer "make-up shift" wording.

## [0.1.15] - 2026-02-11

### Fixed
- Member sync cleanup now cancels planned overrides using the full inactive-member set, preventing stale future overrides from lingering.
- `POST /v1/cleaning/overrides/swap` now rejects inactive members.
- Added regression tests for inactive-member swap validation and future schedule cleanup after sync.

## [0.1.14] - 2026-02-11

### Changed
- Version alignment release for integration-side notification deep links and automation event trigger enhancements.

## [0.1.13] - 2026-02-11

### Changed
- Version alignment release to match integration editor UX fixes (no backend API behavior changes).

## [0.1.12] - 2026-02-11

### Changed
- Shopping recents ranking now prioritizes historically bought items by purchase count, includes active favorites, and excludes names currently open on the shopping list.
- `POST /v1/cleaning/mark_done` now supports assignee confirmation by another actor via `completed_by_member_id` and returns assignee notification payloads.
- `POST /v1/cleaning/mark_done` now rejects non-assignee `completed_by_member_id` values and directs callers to `mark_takeover_done`.

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
- `POST /v1/import/flatastic` migration endpoint for pasted CSV-style rotation + optional cleaning/shopping history imports.

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
