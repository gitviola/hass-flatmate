# Session Context

## User Prompts

### Prompt 1

Implement the following plan:

# Fix: Resolve notify services via person → device_trackers, send to all devices

## Context

`_build_member_sync_payload` uses substring matching (`norm_name in service`) to associate `notify.*` services with HA users. This causes cross-wiring when one name is a substring of another's service name. The user received a cleaning notification meant for another person.

Fix: resolve notify services through person entity → `device_trackers` → derive `notify.mobil...

### Prompt 2

yes commit

