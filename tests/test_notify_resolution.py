"""Tests for notify service resolution (person -> device_trackers -> notify.mobile_app_*).

Exercises _resolve_member_notify_services, _build_member_sync_payload, and
_dispatch_notifications without a full Home Assistant installation.
HA modules are stubbed at import time.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path so custom_components is importable
# ---------------------------------------------------------------------------
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ---------------------------------------------------------------------------
# Stub out homeassistant, voluptuous, aiohttp before importing integration
# ---------------------------------------------------------------------------
_stubs: dict[str, ModuleType] = {}


def _stub(name: str, parent: str | None = None, **attrs: Any) -> ModuleType:
    mod = ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    _stubs[name] = mod
    sys.modules[name] = mod
    if parent and parent in _stubs:
        setattr(_stubs[parent], name.rsplit(".", 1)[-1], mod)
    return mod


class _FakeDataUpdateCoordinator:
    """Minimal base so HassFlatmateCoordinator can inherit."""

    def __init__(self, *a: Any, **kw: Any) -> None:
        pass

    def __class_getitem__(cls, item: Any) -> type:
        return cls


# -- homeassistant hierarchy --
_stub("homeassistant")
_stub("homeassistant.const", parent="homeassistant",
      CONF_API_TOKEN="api_token", CONF_TYPE="type", CONF_URL="url",
      EVENT_HOMEASSISTANT_STARTED="ha_started", Platform=MagicMock())
_stub("homeassistant.core", parent="homeassistant",
      Event=MagicMock, HomeAssistant=MagicMock, ServiceCall=MagicMock,
      callback=lambda f: f)
_stub("homeassistant.config_entries", parent="homeassistant",
      ConfigEntry=MagicMock,
      ConfigEntryNotReady=type("ConfigEntryNotReady", (Exception,), {}))
_stub("homeassistant.exceptions", parent="homeassistant",
      HomeAssistantError=type("HomeAssistantError", (Exception,), {}))
_stub("homeassistant.components", parent="homeassistant")
_stub("homeassistant.components.http", parent="homeassistant.components",
      StaticPathConfig=MagicMock)
_stub("homeassistant.helpers", parent="homeassistant")
_stub("homeassistant.helpers.config_validation",
      parent="homeassistant.helpers",
      string=str, positive_int=int, boolean=bool)
_stub("homeassistant.helpers.aiohttp_client",
      parent="homeassistant.helpers",
      async_get_clientsession=MagicMock())
_stub("homeassistant.helpers.entity_registry",
      parent="homeassistant.helpers",
      async_get=MagicMock(),
      async_entries_for_config_entry=MagicMock(return_value=[]))
_stub("homeassistant.helpers.event", parent="homeassistant.helpers",
      async_track_time_change=MagicMock())
_stub("homeassistant.helpers.typing", parent="homeassistant.helpers",
      ConfigType=dict)
_stub("homeassistant.helpers.update_coordinator",
      parent="homeassistant.helpers",
      DataUpdateCoordinator=_FakeDataUpdateCoordinator,
      UpdateFailed=type("UpdateFailed", (Exception,), {}))
_stub("homeassistant.util", parent="homeassistant")
_dt = _stub("homeassistant.util.dt", parent="homeassistant.util")
_dt.utcnow = MagicMock(return_value=MagicMock(
    isoformat=MagicMock(return_value="2025-01-01T00:00:00")))
_dt.now = MagicMock()
_dt.parse_datetime = MagicMock()
_dt.as_utc = MagicMock()
_dt.as_local = MagicMock()

# -- voluptuous --
_vol = _stub("voluptuous")
_vol.Schema = lambda *a, **k: MagicMock()
_vol.Required = lambda *a, **k: a[0] if a else MagicMock()
_vol.Optional = lambda *a, **k: a[0] if a else MagicMock()

# -- aiohttp --
_stub("aiohttp",
      ClientError=type("ClientError", (Exception,), {}),
      ClientSession=MagicMock)

# ---------------------------------------------------------------------------
# NOW import from the integration
# ---------------------------------------------------------------------------
from custom_components.hass_flatmate import (  # noqa: E402
    HassFlatmateRuntime,
    _build_member_sync_payload,
    _dispatch_notifications,
    _resolve_member_notify_services,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class MockState:
    """Minimal HA State stand-in."""

    def __init__(self, entity_id: str, attributes: dict[str, Any] | None = None) -> None:
        self.entity_id = entity_id
        self.attributes = attributes or {}


class MockUser:
    """Minimal HA User stand-in."""

    def __init__(
        self,
        name: str,
        user_id: str,
        *,
        is_active: bool = True,
        system_generated: bool = False,
    ) -> None:
        self.name = name
        self.id = user_id
        self.is_active = is_active
        self.system_generated = system_generated


class MockHass:
    """Lightweight hass mock providing states, services, and auth."""

    def __init__(
        self,
        *,
        states: list[MockState] | None = None,
        notify_services: dict[str, Any] | None = None,
        users: list[MockUser] | None = None,
    ) -> None:
        self._all_states = states or []
        self._notify = notify_services or {}
        self._users = users or []
        self.service_calls: list[tuple[str, str, dict]] = []

        # hass.states
        self.states = MagicMock()
        self.states.async_all = self._async_all_states
        self.states.get = self._get_state

        # hass.services
        self.services = MagicMock()
        self.services.async_services.return_value = {"notify": self._notify}
        self.services.async_call = AsyncMock(side_effect=self._async_call)

        # hass.auth
        self.auth = MagicMock()
        self.auth.async_get_users = AsyncMock(return_value=self._users)

        # extras needed by the module
        self.data = {}
        self.bus = MagicMock()
        self.async_create_task = MagicMock()

    def _async_all_states(self, domain: str) -> list[MockState]:
        prefix = f"{domain}."
        return [s for s in self._all_states if s.entity_id.startswith(prefix)]

    def _get_state(self, entity_id: str) -> MockState | None:
        return next((s for s in self._all_states if s.entity_id == entity_id), None)

    async def _async_call(
        self, domain: str, service: str, payload: dict, *, blocking: bool = False
    ) -> None:
        self.service_calls.append((domain, service, payload))


def make_runtime(
    members: list[dict[str, Any]] | None = None,
    runtime_state: dict[str, Any] | None = None,
) -> HassFlatmateRuntime:
    rt = MagicMock(spec=HassFlatmateRuntime)
    rt.coordinator = MagicMock()
    rt.coordinator.data = {"members": members or []}
    rt.runtime_state = runtime_state or {}
    rt.api = MagicMock()
    rt.api.record_cleaning_notification_dispatch = AsyncMock()
    return rt


# ---------------------------------------------------------------------------
# Tests: _resolve_member_notify_services
# ---------------------------------------------------------------------------


class TestResolveNotifyServices:
    def test_single_device(self) -> None:
        hass = MockHass(
            states=[
                MockState("person.jo", {
                    "user_id": "uid_jo",
                    "device_trackers": ["device_tracker.jo_iphone"],
                }),
            ],
            notify_services={"mobile_app_jo_iphone": {}},
        )
        runtime = make_runtime(members=[
            {"id": 1, "ha_user_id": "uid_jo", "display_name": "Jo"},
        ])

        result = _resolve_member_notify_services(hass, runtime, 1)
        assert result == ["notify.mobile_app_jo_iphone"]

    def test_multiple_devices(self) -> None:
        hass = MockHass(
            states=[
                MockState("person.jo", {
                    "user_id": "uid_jo",
                    "device_trackers": [
                        "device_tracker.jo_iphone",
                        "device_tracker.jo_ipad",
                    ],
                }),
            ],
            notify_services={"mobile_app_jo_iphone": {}, "mobile_app_jo_ipad": {}},
        )
        runtime = make_runtime(members=[
            {"id": 1, "ha_user_id": "uid_jo", "display_name": "Jo"},
        ])

        result = _resolve_member_notify_services(hass, runtime, 1)
        assert result == [
            "notify.mobile_app_jo_iphone",
            "notify.mobile_app_jo_ipad",
        ]

    def test_none_member_id(self) -> None:
        hass = MockHass()
        runtime = make_runtime()
        assert _resolve_member_notify_services(hass, runtime, None) == []

    def test_member_not_found(self) -> None:
        hass = MockHass()
        runtime = make_runtime(members=[
            {"id": 1, "ha_user_id": "uid_jo", "display_name": "Jo"},
        ])
        assert _resolve_member_notify_services(hass, runtime, 999) == []

    def test_no_ha_user_id(self) -> None:
        hass = MockHass()
        runtime = make_runtime(members=[
            {"id": 1, "display_name": "Jo"},
        ])
        assert _resolve_member_notify_services(hass, runtime, 1) == []

    def test_resolves_via_member_person_entity_id_without_user_link(self) -> None:
        hass = MockHass(
            states=[
                MockState("person.jo", {
                    "device_trackers": ["device_tracker.jo_iphone"],
                }),
            ],
            notify_services={"mobile_app_jo_iphone": {}},
        )
        runtime = make_runtime(members=[
            {"id": 1, "ha_person_entity_id": "person.jo", "display_name": "Jo"},
        ])
        assert _resolve_member_notify_services(hass, runtime, 1) == ["notify.mobile_app_jo_iphone"]

    def test_no_person_entity(self) -> None:
        hass = MockHass(states=[], notify_services={"mobile_app_jo_iphone": {}})
        runtime = make_runtime(members=[
            {"id": 1, "ha_user_id": "uid_jo", "display_name": "Jo"},
        ])
        assert _resolve_member_notify_services(hass, runtime, 1) == []

    def test_tracker_without_matching_service(self) -> None:
        hass = MockHass(
            states=[
                MockState("person.jo", {
                    "user_id": "uid_jo",
                    "device_trackers": ["device_tracker.jo_iphone"],
                }),
            ],
            notify_services={},  # no matching service
        )
        runtime = make_runtime(members=[
            {"id": 1, "ha_user_id": "uid_jo", "display_name": "Jo"},
        ])
        assert _resolve_member_notify_services(hass, runtime, 1) == []

    def test_ignores_non_device_tracker_entries(self) -> None:
        hass = MockHass(
            states=[
                MockState("person.jo", {
                    "user_id": "uid_jo",
                    "device_trackers": [
                        "sensor.jo_battery",  # not a device_tracker
                        "device_tracker.jo_iphone",
                    ],
                }),
            ],
            notify_services={"mobile_app_jo_iphone": {}},
        )
        runtime = make_runtime(members=[
            {"id": 1, "ha_user_id": "uid_jo", "display_name": "Jo"},
        ])
        result = _resolve_member_notify_services(hass, runtime, 1)
        assert result == ["notify.mobile_app_jo_iphone"]


# ---------------------------------------------------------------------------
# Tests: _build_member_sync_payload
# ---------------------------------------------------------------------------


class TestBuildMemberSyncPayload:
    def test_resolves_via_device_trackers(self) -> None:
        hass = MockHass(
            states=[
                MockState("person.jo", {
                    "user_id": "uid_jo",
                    "device_trackers": ["device_tracker.jo_iphone"],
                }),
            ],
            notify_services={"mobile_app_jo_iphone": {}},
            users=[MockUser("Jo", "uid_jo")],
        )
        result = asyncio.get_event_loop().run_until_complete(
            _build_member_sync_payload(hass)
        )
        assert len(result) == 1
        assert result[0]["notify_service"] == "notify.mobile_app_jo_iphone"
        assert result[0]["notify_services"] == ["notify.mobile_app_jo_iphone"]
        assert result[0]["device_trackers"] == ["device_tracker.jo_iphone"]

    def test_no_cross_wire_substring_names(self) -> None:
        """The original bug: 'Jo' is a substring of 'Johan's service name.

        Old code: norm_name in service → 'jo' in 'mobile_app_johan_phone' → True.
        New code: looks up person → device_trackers, so each user only gets
        their own devices.
        """
        hass = MockHass(
            states=[
                MockState("person.jo", {
                    "user_id": "uid_jo",
                    "device_trackers": ["device_tracker.jo_iphone"],
                }),
                MockState("person.johan", {
                    "user_id": "uid_johan",
                    "device_trackers": ["device_tracker.johan_phone"],
                }),
            ],
            notify_services={
                "mobile_app_jo_iphone": {},
                "mobile_app_johan_phone": {},
            },
            users=[
                MockUser("Jo", "uid_jo"),
                MockUser("Johan", "uid_johan"),
            ],
        )
        result = asyncio.get_event_loop().run_until_complete(
            _build_member_sync_payload(hass)
        )
        by_name = {r["display_name"]: r for r in result}
        assert by_name["Jo"]["notify_service"] == "notify.mobile_app_jo_iphone"
        assert by_name["Johan"]["notify_service"] == "notify.mobile_app_johan_phone"

    def test_no_person_entity_gives_none(self) -> None:
        hass = MockHass(
            states=[],  # no person entities
            notify_services={"mobile_app_jo_iphone": {}},
            users=[MockUser("Jo", "uid_jo")],
        )
        result = asyncio.get_event_loop().run_until_complete(
            _build_member_sync_payload(hass)
        )
        assert len(result) == 1
        assert result[0]["notify_service"] is None

    def test_no_device_trackers_gives_none(self) -> None:
        hass = MockHass(
            states=[
                MockState("person.jo", {
                    "user_id": "uid_jo",
                    "device_trackers": [],
                }),
            ],
            notify_services={"mobile_app_jo_iphone": {}},
            users=[MockUser("Jo", "uid_jo")],
        )
        result = asyncio.get_event_loop().run_until_complete(
            _build_member_sync_payload(hass)
        )
        assert result[0]["notify_service"] is None
        assert result[0]["notify_services"] == []
        assert result[0]["device_trackers"] == []

    def test_skips_inactive_and_system_users(self) -> None:
        hass = MockHass(
            states=[],
            notify_services={},
            users=[
                MockUser("Bot", "uid_bot", system_generated=True),
                MockUser("Disabled", "uid_disabled", is_active=False),
                MockUser("Jo", "uid_jo"),
            ],
        )
        result = asyncio.get_event_loop().run_until_complete(
            _build_member_sync_payload(hass)
        )
        assert len(result) == 1
        assert result[0]["display_name"] == "Jo"


# ---------------------------------------------------------------------------
# Tests: _dispatch_notifications (multi-device)
# ---------------------------------------------------------------------------


class TestDispatchNotifications:
    def test_sends_to_all_resolved_devices(self) -> None:
        hass = MockHass(
            states=[
                MockState("person.jo", {
                    "user_id": "uid_jo",
                    "device_trackers": [
                        "device_tracker.jo_iphone",
                        "device_tracker.jo_ipad",
                    ],
                }),
            ],
            notify_services={"mobile_app_jo_iphone": {}, "mobile_app_jo_ipad": {}},
        )
        runtime = make_runtime(members=[
            {"id": 1, "ha_user_id": "uid_jo", "display_name": "Jo",
             "notify_service": "notify.mobile_app_jo_iphone"},
        ])
        notifications = [
            {
                "member_id": 1,
                "notify_service": "notify.mobile_app_jo_iphone",
                "title": "Cleaning Reminder",
                "message": "Your turn!",
                "category": "cleaning",
                "week_start": "2025-01-06",
            }
        ]

        asyncio.get_event_loop().run_until_complete(
            _dispatch_notifications(hass, runtime, notifications, default_category="cleaning")
        )

        services_called = [(d, s) for d, s, _ in hass.service_calls]
        assert ("notify", "mobile_app_jo_iphone") in services_called
        assert ("notify", "mobile_app_jo_ipad") in services_called
        assert len(services_called) == 2

    def test_does_not_fall_back_for_known_member(self) -> None:
        """Known members must resolve via person/device_trackers, not stale fallback service."""
        hass = MockHass(
            states=[],  # no person entities → resolution returns []
            notify_services={"mobile_app_jo_iphone": {}},
        )
        runtime = make_runtime(members=[
            {"id": 1, "ha_user_id": "uid_jo", "display_name": "Jo",
             "notify_service": "notify.mobile_app_jo_iphone"},
        ])
        notifications = [
            {
                "member_id": 1,
                "notify_service": "notify.mobile_app_jo_iphone",
                "title": "Cleaning",
                "message": "Go clean!",
            }
        ]

        asyncio.get_event_loop().run_until_complete(
            _dispatch_notifications(hass, runtime, notifications)
        )

        assert len(hass.service_calls) == 0

    def test_falls_back_to_stored_service_without_member_id(self) -> None:
        """Legacy notifications without member_id can still use explicit notify_service."""
        hass = MockHass(states=[], notify_services={"mobile_app_legacy_phone": {}})
        runtime = make_runtime(members=[])
        notifications = [
            {
                "notify_service": "notify.mobile_app_legacy_phone",
                "title": "Cleaning",
                "message": "Go clean!",
            }
        ]

        asyncio.get_event_loop().run_until_complete(
            _dispatch_notifications(hass, runtime, notifications)
        )

        assert len(hass.service_calls) == 1
        assert hass.service_calls[0][:2] == ("notify", "mobile_app_legacy_phone")

    def test_test_mode_redirects_to_single_target(self) -> None:
        hass = MockHass(
            states=[
                MockState("person.jo", {
                    "user_id": "uid_jo",
                    "device_trackers": [
                        "device_tracker.jo_iphone",
                        "device_tracker.jo_ipad",
                    ],
                }),
                MockState("person.admin", {
                    "user_id": "uid_admin",
                    "device_trackers": ["device_tracker.admin_phone"],
                }),
            ],
            notify_services={
                "mobile_app_jo_iphone": {},
                "mobile_app_jo_ipad": {},
                "mobile_app_admin_phone": {},
            },
        )
        runtime = make_runtime(
            members=[
                {"id": 1, "ha_user_id": "uid_jo", "display_name": "Jo",
                 "notify_service": "notify.mobile_app_jo_iphone"},
                {"id": 2, "ha_user_id": "uid_admin", "display_name": "Admin",
                 "notify_service": "notify.mobile_app_admin_phone", "active": True},
            ],
            runtime_state={
                "notification_test_mode": True,
                "notification_test_target_member_id": 2,
            },
        )
        notifications = [
            {
                "member_id": 1,
                "notify_service": "notify.mobile_app_jo_iphone",
                "title": "Cleaning",
                "message": "Go clean!",
                "category": "cleaning",
                "week_start": "2025-01-06",
            }
        ]

        asyncio.get_event_loop().run_until_complete(
            _dispatch_notifications(hass, runtime, notifications, default_category="cleaning")
        )

        # Should send to admin's single service, not Jo's devices
        assert len(hass.service_calls) == 1
        assert hass.service_calls[0][:2] == ("notify", "mobile_app_admin_phone")
        # Title should be prefixed with [TEST]
        assert hass.service_calls[0][2]["title"].startswith("[TEST]")
        # Message should indicate intended recipient
        assert "Jo" in hass.service_calls[0][2]["message"]

    def test_skips_when_no_services_resolved(self) -> None:
        hass = MockHass(states=[], notify_services={})
        runtime = make_runtime(members=[
            {"id": 1, "ha_user_id": "uid_jo", "display_name": "Jo"},
        ])
        notifications = [
            {
                "member_id": 1,
                # no notify_service stored either
                "title": "Cleaning",
                "message": "Go clean!",
                "category": "cleaning",
                "week_start": "2025-01-06",
            }
        ]

        asyncio.get_event_loop().run_until_complete(
            _dispatch_notifications(hass, runtime, notifications, default_category="cleaning")
        )

        assert len(hass.service_calls) == 0
        # Should have recorded a dispatch as skipped
        runtime.api.record_cleaning_notification_dispatch.assert_called_once()
        records = runtime.api.record_cleaning_notification_dispatch.call_args[1]["records"]
        assert records[0]["status"] == "skipped"
        assert records[0]["reason"] == "missing_notify_service"

    def test_records_dispatch_per_device(self) -> None:
        """Each device send should produce its own dispatch record."""
        hass = MockHass(
            states=[
                MockState("person.jo", {
                    "user_id": "uid_jo",
                    "device_trackers": [
                        "device_tracker.jo_iphone",
                        "device_tracker.jo_ipad",
                    ],
                }),
            ],
            notify_services={"mobile_app_jo_iphone": {}, "mobile_app_jo_ipad": {}},
        )
        runtime = make_runtime(members=[
            {"id": 1, "ha_user_id": "uid_jo", "display_name": "Jo",
             "notify_service": "notify.mobile_app_jo_iphone"},
        ])
        notifications = [
            {
                "member_id": 1,
                "notify_service": "notify.mobile_app_jo_iphone",
                "title": "Cleaning",
                "message": "Go clean!",
                "category": "cleaning",
                "week_start": "2025-01-06",
            }
        ]

        asyncio.get_event_loop().run_until_complete(
            _dispatch_notifications(hass, runtime, notifications, default_category="cleaning")
        )

        runtime.api.record_cleaning_notification_dispatch.assert_called_once()
        records = runtime.api.record_cleaning_notification_dispatch.call_args[1]["records"]
        assert len(records) == 2
        services_logged = {r["notify_service"] for r in records}
        assert services_logged == {
            "notify.mobile_app_jo_iphone",
            "notify.mobile_app_jo_ipad",
        }
        assert all(r["status"] == "sent" for r in records)
