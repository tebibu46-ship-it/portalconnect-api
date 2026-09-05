"""Demurrage alert construction and optional webhook dispatch."""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx


class WebhookService:
    """Build operational alerts and deliver them to a registered endpoint."""

    def __init__(self, client_factory: Any = httpx.AsyncClient) -> None:
        self._client_factory = client_factory
        self._targets: set[str] = set()

    @staticmethod
    def is_urgent(item: dict[str, Any]) -> bool:
        if float(item.get("fees_due", 0) or 0) > 0:
            return True
        try:
            return (date.fromisoformat(str(item["last_free_day"])) - date.today()).days * 24 < 24
        except (KeyError, TypeError, ValueError):
            return False

    @classmethod
    def build_alert(cls, item: dict[str, Any]) -> dict[str, Any] | None:
        if not cls.is_urgent(item):
            return None
        return {
            "event": "demurrage_risk",
            "container_id": item.get("container_id"),
            "terminal_id": item.get("terminal_id"),
            "status": item.get("status"),
            "fees_due": float(item.get("fees_due", 0) or 0),
            "last_free_day": item.get("last_free_day"),
            "urgency_level": "CRITICAL" if float(item.get("fees_due", 0) or 0) > 0 else "CAUTION",
        }

    @staticmethod
    def format_driver_sms(item: dict[str, Any], appointment_url: str) -> str:
        """Format a concise driver-facing alert for SMS or dispatch gateways."""
        container = item.get("container_id", "UNKNOWN")
        terminal = item.get("terminal_name") or item.get("terminal_id", "UNKNOWN")
        countdown = item.get("countdown") or item.get("urgency_level", "immediate")
        return (f"[PORTALCONNECT ALERT] CRITICAL: Container {container} at {terminal} free-time "
                f"expires in {countdown}! Book gate appointment immediately to avoid tiered demurrage: {appointment_url}")

    def register(self, target_url: str) -> str:
        target_url = target_url.strip()
        if not target_url.startswith(("http://", "https://")):
            raise ValueError("target_url must use http:// or https://")
        self._targets.add(target_url)
        return target_url

    async def dispatch(self, payload: dict[str, Any], target_url: str | None = None) -> dict[str, Any]:
        target = self.register(target_url) if target_url else next(iter(self._targets), None)
        if not target:
            return {"delivered": False, "payload": payload, "reason": "No webhook target registered"}
        try:
            async with self._client_factory(timeout=5.0) as client:
                response = await client.post(target, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            return {"delivered": False, "target_url": target, "payload": payload, "reason": str(exc)}
        return {"delivered": True, "target_url": target, "payload": payload}

    async def poll_and_dispatch(self, watchlist: Any, target_url: str | None = None) -> list[dict[str, Any]]:
        """Inspect persisted rows and dispatch alerts for urgent units."""

        alerts: list[dict[str, Any]] = []
        for item in await watchlist.list_all():
            payload = self.build_alert(item)
            if payload is not None:
                alerts.append(await self.dispatch(payload, target_url))
        return alerts
