"""Constants for hass_flatmate integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "hass_flatmate"

CONF_BASE_URL = "base_url"
CONF_API_TOKEN = "api_token"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_NOTIFICATION_TEST_MODE = "notification_test_mode"
CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID = "notification_test_target_member_id"
CONF_SHOPPING_TARGET_CALENDAR_ENTITY_ID = "shopping_target_calendar_entity_id"
CONF_CLEANING_TARGET_CALENDAR_ENTITY_ID = "cleaning_target_calendar_entity_id"

DEFAULT_BASE_URL = "http://ebc95cb1-hass-flatmate-service:8099"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_NOTIFICATION_TEST_MODE = False
FRONTEND_STATIC_PATH = "/hass_flatmate/static"
FRONTEND_SHOPPING_CARD_FILENAME = "hass-flatmate-shopping-card.js"
FRONTEND_CLEANING_CARD_FILENAME = "hass-flatmate-cleaning-card.js"
FRONTEND_DISTRIBUTION_CARD_FILENAME = "hass-flatmate-distribution-card.js"
FRONTEND_SHOPPING_CARD_RESOURCE_URL = f"{FRONTEND_STATIC_PATH}/{FRONTEND_SHOPPING_CARD_FILENAME}"
FRONTEND_CLEANING_CARD_RESOURCE_URL = f"{FRONTEND_STATIC_PATH}/{FRONTEND_CLEANING_CARD_FILENAME}"
FRONTEND_DISTRIBUTION_CARD_RESOURCE_URL = f"{FRONTEND_STATIC_PATH}/{FRONTEND_DISTRIBUTION_CARD_FILENAME}"
FRONTEND_SHOPPING_CARD_RESOURCE_TYPE = "module"
FRONTEND_CLEANING_CARD_RESOURCE_TYPE = "module"
FRONTEND_DISTRIBUTION_CARD_RESOURCE_TYPE = "module"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.CALENDAR,
    Platform.SWITCH,
    Platform.SELECT,
]

SERVICE_ADD_SHOPPING_ITEM = "hass_flatmate_add_shopping_item"
SERVICE_COMPLETE_SHOPPING_ITEM = "hass_flatmate_complete_shopping_item"
SERVICE_DELETE_SHOPPING_ITEM = "hass_flatmate_delete_shopping_item"
SERVICE_ADD_FAVORITE_ITEM = "hass_flatmate_add_favorite_item"
SERVICE_DELETE_FAVORITE_ITEM = "hass_flatmate_delete_favorite_item"
SERVICE_MARK_CLEANING_DONE = "hass_flatmate_mark_cleaning_done"
SERVICE_MARK_CLEANING_UNDONE = "hass_flatmate_mark_cleaning_undone"
SERVICE_MARK_CLEANING_TAKEOVER_DONE = "hass_flatmate_mark_cleaning_takeover_done"
SERVICE_SWAP_CLEANING_WEEK = "hass_flatmate_swap_cleaning_week"
SERVICE_SYNC_MEMBERS = "hass_flatmate_sync_members"
SERVICE_IMPORT_FLATASTIC_DATA = "hass_flatmate_import_flatastic_data"

SERVICE_ATTR_NAME = "name"
SERVICE_ATTR_ITEM_ID = "item_id"
SERVICE_ATTR_FAVORITE_ID = "favorite_id"
SERVICE_ATTR_WEEK_START = "week_start"
SERVICE_ATTR_ORIGINAL_ASSIGNEE_MEMBER_ID = "original_assignee_member_id"
SERVICE_ATTR_CLEANER_MEMBER_ID = "cleaner_member_id"
SERVICE_ATTR_MEMBER_A_ID = "member_a_id"
SERVICE_ATTR_MEMBER_B_ID = "member_b_id"
SERVICE_ATTR_CANCEL = "cancel"
SERVICE_ATTR_ROTATION_ROWS = "rotation_rows"
SERVICE_ATTR_CLEANING_HISTORY_ROWS = "cleaning_history_rows"
SERVICE_ATTR_SHOPPING_HISTORY_ROWS = "shopping_history_rows"

COORDINATOR_NAME = "hass_flatmate_coordinator"
NOTIFICATION_DEDUPE_KEY = "last_notification_minute"
CALENDAR_CURSOR_SHOPPING_KEY = "last_synced_shopping_activity_id"
CALENDAR_CURSOR_CLEANING_KEY = "last_synced_cleaning_activity_id"
