# Hass Flatmate

Home Assistant-native flat-sharing toolkit with two parts:

- `custom_components/hass_flatmate`: HACS custom integration
- `apps/hass_flatmate_service`: Home Assistant App (formerly add-on) backend service

It replaces the flat-sharing features you use with:

- Shopping list actions (add, complete, delete)
- Fairness distribution (90-day) + SVG chart image
- Weekly cleaning rotation with temporary swaps
- Takeover completion with automatic compensation override
- Home Assistant calendar activity events
- Built-in notification scheduling (Monday + Sunday reminders)
- Optional shopping-added push notifications
- Notification deep links (iOS + Android)
- Automation-friendly activity events on HA event bus
- Safe notification test mode (redirect all notifications to one selected user)

## One-Click Install

### Home Assistant App (backend)

[![Add app repository to your Home Assistant instance.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fgitviola%2Fhass-flatmate)
[![Show app on your Home Assistant instance.](https://my.home-assistant.io/badges/supervisor_addon.svg)](https://my.home-assistant.io/redirect/supervisor_addon/?addon=hass_flatmate_service&repository_url=https%3A%2F%2Fgithub.com%2Fgitviola%2Fhass-flatmate)

### HACS integration

[![Open HACS repository on your Home Assistant instance.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gitviola&repository=hass-flatmate&category=integration)

## Repository Layout

- `/custom_components/hass_flatmate`: install via HACS (custom repository)
- `/apps/hass_flatmate_service`: install via Home Assistant App repository
- `/addon/hass_flatmate_service`: canonical backend source + tests
- `/apps/hass_flatmate_service/service_src`: app build source mirror (synced from `addon/`)

## Quick Start

1. Install app from this repository (`apps/hass_flatmate_service`) in Home Assistant.
2. Set app option `api_token`.
   - Persistent DB path: `/config/hass_flatmate_service/hass_flatmate.db` (Supervisor `addon_config` mount).
   - Data survives container restarts/image updates; include app/add-on data in HA backups for disaster recovery.
3. Install custom integration via HACS from this repository.
4. Configure integration with:
   - `base_url`: service URL (default `http://ebc95cb1-hass-flatmate-service:8099`)
   - `api_token`: same value from app config
5. In Lovelace storage mode, shopping and cleaning card resources are auto-registered with cache-busting version query params.
6. Add cards/entities from `examples/lovelace-flatmate-dashboard.yaml` (Sections dashboard format).

## Shopping UI Card

Use the custom card in any dashboard:

```yaml
type: custom:hass-flatmate-shopping-card
entity: sensor.hass_flatmate_shopping_data
title: Shared Shopping
```

You can also add it from the dashboard UI card picker (no manual YAML required).

Features:
- Add shopping items fast
- Mark item done / delete item
- Quick add from favorites and recents
- Add/remove favorites

The card uses integration services, so actor attribution stays correct.

## Shopping Compact UI Card

Use the dedicated read-only compact card for e-ink/non-touch displays:

```yaml
type: custom:hass-flatmate-shopping-compact-card
entity: sensor.hass_flatmate_shopping_data
title: Shopping List
```

Features:
- Dense, bullet-free list layout
- Relative age labels like `added 5 hours ago` / `added 2 weeks ago`
- Read-only rendering optimized for passive displays
- Available in the card picker (no manual YAML required)

## Cleaning UI Card

Use the dedicated cleaning card in any dashboard:

```yaml
type: custom:hass-flatmate-cleaning-card
entity: sensor.hass_flatmate_cleaning_schedule
title: Weekly Cleaning
weeks: 5
layout: interactive
```

Features:
- Human-friendly week list (`This week`, `Next week`, etc.)
- Clear done/pending/missed status
- Strike-through visual once completed
- Mark-done action in-card
- Non-assignee completion modal (confirm for assignee vs takeover)
- Optional `layout: compact` read-only mode for e-ink/non-touch dashboards
- Compact mode still shows swap/compensation annotations and who is assigned

Manual swap override remains available via service:
- `hass_flatmate.hass_flatmate_swap_cleaning_week`

In Lovelace YAML resource mode, add both resources manually as `module` (recommended with `?v=<integration_version>`):
- `/hass_flatmate/static/hass-flatmate-shopping-card.js?v=<integration_version>`
- `/hass_flatmate/static/hass-flatmate-shopping-compact-card.js?v=<integration_version>`
- `/hass_flatmate/static/hass-flatmate-cleaning-card.js?v=<integration_version>`

Compact e-ink example:

```yaml
type: custom:hass-flatmate-cleaning-card
entity: sensor.hass_flatmate_cleaning_schedule
title: Cleaning (E-Ink)
weeks: 5
layout: compact
```

## Distribution UI Card

Use the dedicated distribution card instead of the SVG image entity card:

```yaml
type: custom:hass-flatmate-distribution-card
entity: sensor.hass_flatmate_shopping_distribution_90d
title: Shopping Distribution (90d)
layout: bars
```

Features:
- Stable native rendering in two styles:
  - `layout: bars` (default)
  - `layout: compact` (single-row boxes, e-ink friendly)
- Shows all flatmates from distribution payload (including zero-count members)
- Uses purchase wording (`N purchases`) and last-90-days context text

In Lovelace YAML resource mode, also add:
- `/hass_flatmate/static/hass-flatmate-distribution-card.js?v=<integration_version>`

Compact example:

```yaml
type: custom:hass-flatmate-distribution-card
entity: sensor.hass_flatmate_shopping_distribution_90d
title: Shopping Distribution (Compact)
layout: compact
```

## Notification Test Mode

Use these entities to test all flows without notifying everyone:
- `switch.hass_flatmate_notification_test_mode`
- `select.hass_flatmate_notification_test_target`
- `switch.hass_flatmate_notify_shopping_item_added`
- `text.hass_flatmate_shopping_notification_link`
- `text.hass_flatmate_cleaning_notification_link`
- `select.hass_flatmate_shopping_calendar_target`
- `select.hass_flatmate_cleaning_calendar_target`

When test mode is enabled, all notifications are redirected to the selected target and prefixed with `[TEST]`.

`*_notification_link` accepts:
- Relative dashboard/view path like `/dashboard-flatmate/shopping`
- Full URL like `https://...`
- Companion deep link like `homeassistant://navigate/dashboard-flatmate/shopping`

The integration attaches this link to mobile notifications using both iOS `url` and Android `clickAction`.

## Automation Event Triggers

The integration emits Home Assistant bus events for every new activity row:
- Generic: `hass_flatmate_activity`
- Action-specific: `hass_flatmate_activity_<action>`
  - Example: `hass_flatmate_activity_shopping_item_added`
  - Example: `hass_flatmate_activity_cleaning_done`

Event payload includes:
- `activity_id`, `domain`, `action`, `created_at`
- `actor_member_id`, `actor_name`, `actor_user_id_raw`
- `payload` (raw activity payload JSON), `summary`

This enables per-user custom automations/notifications without changing integration code.

## Manual Data Import

Use service `hass_flatmate_import_manual_data` from Developer Tools to paste CSV-like rows:

- `rotation_rows` format:
  - `date,member_name`
  - date can be any date inside that week (`YYYY-MM-DD` or ISO datetime)
  - rows can be newline or `;` separated
- `cleaning_history_rows` format:
  - `date,member_name[,status][,completed_by_name]`
  - status: `done` (default), `missed`, `pending`
- `shopping_history_rows` format:
  - `date,item_name,buyer_name`
- `cleaning_override_rows` format:
  - `date,member_from_name,member_to_name[,override_type]`
  - `override_type`: `compensation` (default) or `manual_swap`
  - For compensation, `member_from_name` is the person whose baseline turn is being covered.

Example:

```yaml
service: hass_flatmate.hass_flatmate_import_manual_data
data:
  rotation_rows: |
    2026-02-14,Martin
    2026-02-21,Gianmarco
    2026-02-28,María
  cleaning_history_rows: |
    2026-02-01,Martin,done
    2026-02-08,Gianmarco,done
  shopping_history_rows: |
    2026-01-30,Milk,Martin
    2026-01-31,Toilet Paper,Gianmarco
  cleaning_override_rows: |
    2026-03-07,Martin,Martina,compensation
```

Notes:
- Dates can be any day in the target week. Import normalizes to Monday-week internally.
- Member names must match active hass-flatmate display names exactly (including accents).

## Automated Tests

Backend tests run locally without Home Assistant:

```bash
cd addon/hass_flatmate_service
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest
```

CI also runs on every push/PR:
- Backend test suite
- Integration compile check
- Shopping/cleaning custom card JavaScript syntax check
- Home Assistant app test build (via `home-assistant/builder`)
- Sync guard for `apps/hass_flatmate_service/service_src`

## Image Publishing (GHCR)

App images are published automatically to GHCR by GitHub Actions:
- Workflow: `.github/workflows/publish-app.yml`
- Trigger: git tag push like `v0.1.1` (also supports Release `published` and manual `workflow_dispatch`)
- Registry image: `ghcr.io/gitviola/hass-flatmate-service-{arch}`
- Architectures: `amd64`, `aarch64`

Release/tag version must match `apps/hass_flatmate_service/config.yaml` `version`.

## Changelogs

- Repo changelog: `/CHANGELOG.md`
- Integration changelog: `/custom_components/hass_flatmate/CHANGELOG.md`
- App changelog: `/apps/hass_flatmate_service/CHANGELOG.md`

## Syncing App Build Source

When backend code changes in `addon/hass_flatmate_service`, sync mirror source used by app Docker build:

```bash
./scripts/sync_app_service_src.sh
```
