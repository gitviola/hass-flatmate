# Hass Flatmate Service App Changelog

## [0.3.0] - 2026-09-28

### Added
- `POST /v1/cleaning/notifications/resend`: rebuilds a previously dispatched cleaning notification (same recipient, title, message, week and slot) so the integration can send it again, and logs who requested it. Rejects unknown events and recipients who are no longer active. Used by the integration's admin-only resend button.

## [0.2.1] - 2026-09-28

### Changed
- Version alignment release for the integration-side fix of history/activity times being shown 2 hours early.

## [0.2.0] - 2026-09-28

### Added
- Cleaning rotation order editor on the app's web page. Reorder flatmates with up/down arrows (shown as this week, next week, …) and commit with "Save order". The first person cleans the current week. Saving sends no notifications and has the same effect as the manual import service with `rotation_rows`: completed/missed weeks keep their history and planned swaps stay on their weeks.
- Backend endpoints `GET /v1/cleaning/rotation` and `PUT /v1/cleaning/rotation`.

## [0.1.52] - 2026-09-28

### Changed
- Version alignment release for the integration-side member sync fix: only Home Assistant users linked to a `person` entity are synced, so service accounts (e.g. an "HA-MCP Server" user) are deactivated and drop out of the shopping distribution and cleaning rotation.

## [0.1.51] - 2026-05-01

### Changed
- Version alignment release for integration-side fixes (no blocking file reads on the event loop, cleaning schedule sensor within the recorder attribute limit).

## [0.1.50] - 2026-05-01

### Fixed
- App failed to start cleanly on existing installs after 0.1.49 because of the new SQLite engine tuning (StaticPool + WAL pragmas). Reverted those engine changes; database setup is back to the 0.1.48 behavior.
- Restored uvicorn `log_level="info"` so startup is visible in the supervisor log again. Access logs stay disabled.

## [0.1.49] - 2026-05-01

### Performance
- Lower steady-state CPU and RAM use.
- The cleaning schedule now batch-fetches assignments and overrides for the whole window instead of running several queries per week, and only commits when something changed.
- Idle polls no longer write to the database every cycle.
- Uvicorn access logs disabled to drop per-request logging overhead.
- (The SQLite engine tuning from this release was reverted in 0.1.50.)

## [0.1.48] - 2026-04-18

### Fixed
- Cleaning rotation no longer reshuffles the past schedule when a flatmate is removed.
- The person who just cleaned is no longer auto-assigned to next week after another flatmate moves out; the rotation re-anchors to the next active person from the old cycle.
- Past locked weeks (DONE/MISSED) report baseline and effective assignee from the stored assignment, so historical attribution is stable across rotation changes.
- "Originally X's shift" attribution survives marking a swap week as done.

## [0.1.47] - 2026-03-03

### Changed
- Version alignment release for integration-side notification delivery reliability updates (grouped notifications without replacement and resilient member notify resolution fallback).

## [0.1.46] - 2026-02-26

### Changed
- Version alignment release for integration-side shopping bought notification toggle and dispatch behavior.

## [0.1.45] - 2026-02-21

### Fixed
- Migration panel UI now uses ingress-safe relative API paths, fixing `Failed to load members: 404: Not Found` when accessed via Home Assistant Ingress.

## [0.1.44] - 2026-02-21

### Changed
- Version alignment release for integration-side cleaning history UX improvements in complex chained swap-return cases.

## [0.1.43] - 2026-02-21

### Fixed
- Migration ingress UI now uses the configured backend token automatically (no manual token paste required).
- Robust API error parsing in UI to avoid browser `body stream already read` failures when requests fail.

## [0.1.42] - 2026-02-20

### Added
- New migration snapshot endpoints:
  - `GET /v1/admin/export`
  - `POST /v1/admin/import`
- New ingress-ready migration web UI at `/` for secure export/import of full JSON snapshots.

### Changed
- Swap endpoint now accepts optional `return_week_start` and supports explicit return-week placement.
- Automatic swap return-week resolution now uses effective future assignments (planned swaps/compensations included), enabling chained-swap scenarios.
- App panel ingress is enabled in app config for direct access to migration UI.

### Fixed
- Swap return planning now correctly handles reused future compensation slots without breaking ownership of existing planned assignments.

## [0.1.22] - 2026-02-12

### Added
- `POST /v1/cleaning/notifications/dispatch` endpoint to record notification delivery outcomes per week and slot.
- All cleaning notifications now include structured metadata (`category`, `week_start`, `notification_kind`, `notification_slot`, `source_action`).
- Schedule rows now include `completed_at` timestamp.
- Tests for notification dispatch logging and validation.

### Changed
- Service DB-path fallback now defaults to `/config/hass_flatmate_service/hass_flatmate.db` whenever the Home Assistant `/config` mount is available, making persistence the safe default.

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
