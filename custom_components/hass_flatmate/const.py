"""Constants for hass_flatmate integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "hass_flatmate"

CONF_BASE_URL = "base_url"
CONF_API_TOKEN = "api_token"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_BASE_URL = "http://127.0.0.1:8099"
DEFAULT_SCAN_INTERVAL = 30

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.CALENDAR,
]

SERVICE_ADD_SHOPPING_ITEM = "add_shopping_item"
SERVICE_COMPLETE_SHOPPING_ITEM = "complete_shopping_item"
SERVICE_DELETE_SHOPPING_ITEM = "delete_shopping_item"
SERVICE_ADD_FAVORITE_ITEM = "add_favorite_item"
SERVICE_DELETE_FAVORITE_ITEM = "delete_favorite_item"
SERVICE_MARK_CLEANING_DONE = "mark_cleaning_done"
SERVICE_MARK_CLEANING_TAKEOVER_DONE = "mark_cleaning_takeover_done"
SERVICE_SWAP_CLEANING_WEEK = "swap_cleaning_week"
SERVICE_SYNC_MEMBERS = "sync_members"

SERVICE_ATTR_NAME = "name"
SERVICE_ATTR_ITEM_ID = "item_id"
SERVICE_ATTR_FAVORITE_ID = "favorite_id"
SERVICE_ATTR_WEEK_START = "week_start"
SERVICE_ATTR_ORIGINAL_ASSIGNEE_MEMBER_ID = "original_assignee_member_id"
SERVICE_ATTR_CLEANER_MEMBER_ID = "cleaner_member_id"
SERVICE_ATTR_MEMBER_A_ID = "member_a_id"
SERVICE_ATTR_MEMBER_B_ID = "member_b_id"
SERVICE_ATTR_CANCEL = "cancel"

COORDINATOR_NAME = "hass_flatmate_coordinator"
NOTIFICATION_DEDUPE_KEY = "last_notification_minute"
