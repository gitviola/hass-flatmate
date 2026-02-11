"""API client for hass-flatmate add-on service."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from aiohttp import ClientError, ClientSession


class HassFlatmateApiError(Exception):
    """Raised when hass-flatmate API communication fails."""


class HassFlatmateApiClient:
    """Async client for communicating with hass-flatmate add-on service."""

    def __init__(self, session: ClientSession, base_url: str, api_token: str) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._headers = {"x-flatmate-token": api_token}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers,
                params=params,
                json=json,
                timeout=15,
            ) as response:
                if response.status >= 400:
                    text = await response.text()
                    raise HassFlatmateApiError(f"{method} {path} failed: {response.status} {text}")

                if response.content_type in {"image/svg+xml", "text/plain"}:
                    return await response.text()

                if response.content_type == "application/json":
                    return await response.json()

                return await response.read()
        except ClientError as exc:
            raise HassFlatmateApiError(f"{method} {path} failed: {exc}") from exc

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def get_members(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/v1/members")

    async def sync_members(self, members: list[dict[str, Any]]) -> dict[str, Any] | list[dict[str, Any]]:
        return await self._request("PUT", "/v1/members/sync", json={"members": members})

    async def get_shopping_items(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/v1/shopping/items")

    async def add_shopping_item(self, *, name: str, actor_user_id: str | None) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/shopping/items",
            json={"name": name, "actor_user_id": actor_user_id},
        )

    async def complete_shopping_item(self, *, item_id: int, actor_user_id: str | None) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/v1/shopping/items/{item_id}/complete",
            json={"actor_user_id": actor_user_id},
        )

    async def delete_shopping_item(self, *, item_id: int, actor_user_id: str | None) -> dict[str, Any]:
        return await self._request(
            "DELETE",
            f"/v1/shopping/items/{item_id}",
            json={"actor_user_id": actor_user_id},
        )

    async def get_recents(self, *, limit: int = 20) -> dict[str, Any]:
        return await self._request("GET", "/v1/shopping/recents", params={"limit": limit})

    async def get_favorites(self) -> dict[str, Any]:
        return await self._request("GET", "/v1/shopping/favorites")

    async def add_favorite_item(self, *, name: str, actor_user_id: str | None) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/shopping/favorites",
            json={"name": name, "actor_user_id": actor_user_id},
        )

    async def delete_favorite_item(self, *, favorite_id: int, actor_user_id: str | None) -> dict[str, Any]:
        return await self._request(
            "DELETE",
            f"/v1/shopping/favorites/{favorite_id}",
            json={"actor_user_id": actor_user_id},
        )

    async def get_buy_stats(self, *, window_days: int = 90) -> dict[str, Any]:
        return await self._request("GET", "/v1/stats/buys", params={"window_days": window_days})

    async def get_buy_stats_svg(self, *, window_days: int = 90) -> str:
        return await self._request("GET", "/v1/stats/buys.svg", params={"window_days": window_days})

    async def get_activity(self, *, limit: int = 200) -> list[dict[str, Any]]:
        return await self._request("GET", "/v1/activity", params={"limit": limit})

    async def import_manual_data(
        self,
        *,
        rotation_rows: str | None,
        cleaning_history_rows: str | None,
        shopping_history_rows: str | None,
        actor_user_id: str | None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/import/manual",
            json={
                "rotation_rows": rotation_rows,
                "cleaning_history_rows": cleaning_history_rows,
                "shopping_history_rows": shopping_history_rows,
                "actor_user_id": actor_user_id,
            },
        )

    async def import_flatastic_data(
        self,
        *,
        rotation_rows: str | None,
        cleaning_history_rows: str | None,
        shopping_history_rows: str | None,
        actor_user_id: str | None,
    ) -> dict[str, Any]:
        """Backward-compat shim; use import_manual_data."""
        return await self.import_manual_data(
            rotation_rows=rotation_rows,
            cleaning_history_rows=cleaning_history_rows,
            shopping_history_rows=shopping_history_rows,
            actor_user_id=actor_user_id,
        )

    async def get_cleaning_current(self) -> dict[str, Any]:
        return await self._request("GET", "/v1/cleaning/current")

    async def get_cleaning_schedule(
        self,
        *,
        weeks_ahead: int = 12,
        include_previous_weeks: int = 0,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v1/cleaning/schedule",
            params={
                "weeks_ahead": weeks_ahead,
                "include_previous_weeks": include_previous_weeks,
            },
        )

    async def mark_cleaning_done(
        self,
        *,
        week_start: date,
        actor_user_id: str | None,
        completed_by_member_id: int | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/cleaning/mark_done",
            json={
                "week_start": week_start.isoformat(),
                "actor_user_id": actor_user_id,
                "completed_by_member_id": completed_by_member_id,
            },
        )

    async def mark_cleaning_undone(self, *, week_start: date, actor_user_id: str | None) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/cleaning/mark_undone",
            json={"week_start": week_start.isoformat(), "actor_user_id": actor_user_id},
        )

    async def mark_cleaning_takeover_done(
        self,
        *,
        week_start: date,
        original_assignee_member_id: int,
        cleaner_member_id: int,
        actor_user_id: str | None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/cleaning/mark_takeover_done",
            json={
                "week_start": week_start.isoformat(),
                "original_assignee_member_id": original_assignee_member_id,
                "cleaner_member_id": cleaner_member_id,
                "actor_user_id": actor_user_id,
            },
        )

    async def swap_cleaning_week(
        self,
        *,
        week_start: date,
        member_a_id: int,
        member_b_id: int,
        actor_user_id: str | None,
        cancel: bool,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/cleaning/overrides/swap",
            json={
                "week_start": week_start.isoformat(),
                "member_a_id": member_a_id,
                "member_b_id": member_b_id,
                "actor_user_id": actor_user_id,
                "cancel": cancel,
            },
        )

    async def get_due_notifications(self, *, at: datetime) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v1/cleaning/notifications/due",
            params={"at": at.isoformat()},
        )
