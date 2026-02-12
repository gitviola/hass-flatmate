# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Changed
- Cleaning swap semantics now exchange two shifts (selected week plus the selected flatmate's next regular baseline week) instead of only replacing one week.
- Cleaning swap modal copy now explains the two-week exchange explicitly, including return-week preview.

### Fixed
- Cleaning schedule payload now includes `override_source` so UI can distinguish swap-return weeks from takeover make-up shifts.

## [0.1.20] - 2026-02-12

### Changed
- Compact cleaning card now prioritizes assignee-first readability for e-ink: assignee name is shown first in bold, with date/details on following lines.
- Cleaning confirmation/swap modals now use clearer one-time wording and expanded consequence previews.

### Fixed
- Compact cleaning card now renders week context markers (`this week`, `previous week`, `next week`) in italic styling.
- Compact cleaning card notes such as `Done by ...` are now italicized for clearer visual separation.
- Cleaning modal preview now explicitly lists per-person notifications and actor-aware messages so outcomes are unambiguous.
- Shopping add-item input now keeps focus and typing stability during Home Assistant state updates (no more input-lock/focus-loss behavior while typing).

## [0.1.19] - 2026-02-12

### Changed
- Cleaning completion/swap services now return faster by scheduling refresh/activity sync in the background instead of blocking service calls.

### Fixed
- Cleaning interactive card now applies optimistic week updates (done/undone/swap) so status changes are visible immediately without manual page refresh.
- Cleaning UI wording now uses user-friendly "make-up shift" labels/messages instead of technical "compensation override" phrasing.
- Compact cleaning card now highlights the current week with a stronger left-side marker instead of the previous arrow prefix.

## [0.1.18] - 2026-02-12

### Changed
- Manual import now supports `cleaning_override_rows` for one-time planned compensation/swap migration rows.

### Fixed
- `hass_flatmate_import_manual_data` now surfaces backend API errors with explicit messages in Home Assistant instead of generic unknown-action failures.
- Manual import service now falls back to legacy backend route compatibility when app/integration versions are temporarily mixed.

## [0.1.17] - 2026-02-11

### Added
- New e-ink focused custom card: `custom:hass-flatmate-shopping-compact-card`.
- Compact shopping card renders a dense read-only list from `sensor.hass_flatmate_shopping_data` with relative age labels such as `added 5 hours ago`.
- Frontend auto-registration now includes `/hass_flatmate/static/hass-flatmate-shopping-compact-card.js` in storage mode.

### Changed
- Renamed migration import interfaces to generic manual naming:
  - API: `POST /v1/import/manual`
  - HA service: `hass_flatmate_import_manual_data`
  - Activity action: `manual_import_applied`
- Removed product-specific wording from user-facing migration docs and service labels.

## [0.1.16] - 2026-02-11

### Changed
- Cleaning interactive card restored in-card swap controls for upcoming/current weeks, including `Swap` and `Edit swap` actions with optimistic save states.
- Cleaning completion modal wording is now user-focused and consequence-driven, with dynamic takeover preview text that explains compensation and notifications.
- Cleaning swap modal now includes dynamic "What this will do" previews, selectable target flatmate flow, and explicit cancel-swap guidance.
- Distribution compact layout now keeps member names on a single line with responsive truncation instead of multi-line wrapping.
- Distribution compact diagram now renders edge-to-edge across the card width for e-ink/compact dashboard usage.

### Fixed
- Interactive cleaning rows no longer lose swap capability behind a static `Pending` status for future weeks.
- Distribution card hides subtitle/total-purchases header chrome when title is intentionally empty, so compact embeds can render chart-only.

## [0.1.15] - 2026-02-11

### Fixed
- `hass_flatmate_sync_members` now cleans planned overrides using all currently inactive members (not only newly deactivated ones), so stale future swaps/compensations are removed reliably.
- Cleaning swap creation now rejects inactive members at backend validation time.
- Cleaning schedule card member metadata now includes only active flatmates, so inactive users no longer appear in in-card selection dropdowns.
- Added regression coverage for inactive-member swap rejection and post-sync future schedule cleanup.

## [0.1.14] - 2026-02-11

### Added
- Automation-ready Home Assistant bus events for every new activity entry:
  - `hass_flatmate_activity`
  - `hass_flatmate_activity_<action>`
- New configurable notification link entities:
  - `text.hass_flatmate_shopping_notification_link`
  - `text.hass_flatmate_cleaning_notification_link`
- New optional built-in shopping push switch:
  - `switch.hass_flatmate_notify_shopping_item_added`

### Changed
- Mobile notification payloads now include deep-link fields for both companion apps (`url` and `clickAction`) plus an Open action button when a notification link is configured.
- Cleaning notifications now use category-aware notification metadata (group/tag + optional deep link).
- README updated with deep-link usage and automation event trigger docs.

## [0.1.13] - 2026-02-11

### Fixed
- Home Assistant dashboard card editors no longer flicker while editing title/layout/entity fields.
- Card editors now follow render-once + value-sync behavior to avoid focus loss and repeated input re-mounts during live config updates.

## [0.1.12] - 2026-02-11

### Changed
- Distribution custom card now supports two layouts via config:
  - `layout: bars` (default app-style bars)
  - `layout: compact` (single-row boxed layout for compact/e-ink dashboards)
- Distribution card text updated to purchase-focused wording:
  - `N purchases` instead of `N done`
  - `Based on data of the last 90 days` subtitle
  - Removed explicit `Window: 90d` chip
- Bar layout no longer shows percentage labels.
- Cleaning card now supports `layout: compact` read-only mode for e-ink/non-touch displays.
- Member sync now deactivates departed members in rotation planning and auto-cancels impacted planned overrides.
- Auto-canceled overrides from member departures now emit notifications for remaining affected flatmates.
- Shopping card add-item UX is now optimistic/instant with temporary pending rows while backend save completes.
- Shopping quick suggestions now prioritize names by historical purchase frequency and include favorited items, excluding names currently open on the shopping list.
- Shopping remove action wording now explicitly reflects "remove from list" behavior rather than hard deletion semantics.
- Cleaning completion now supports assignee confirmation by another member using `completed_by_member_id`, with notification to the assignee.
- Cleaning completion now rejects non-assignee confirmation payloads and requires takeover flow for actual takeovers.
- Cleaning card interactive flow now opens a non-assignee completion modal with explicit options for "confirm for assignee" vs. "takeover with compensation".
- Cleaning card no longer exposes swap controls in-card; swap remains available via the existing service.
- Cleaning compact layout is now fully responsive with stacked row content, `Upcoming` labels for future weeks, and no redundant current-assignee/header status text.

### Added
- New manual migration import service flow:
  - API: `POST /v1/import/manual`
  - HA service: `hass_flatmate_import_manual_data`
  - Supports pasted CSV-style rows for rotation seed, cleaning history, and shopping history.
- Cleaning card now supports `layout: compact` for read-only e-ink dashboards.
- Added committed app icon/logo assets in mirrored app source for versioned packaging consistency.
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
