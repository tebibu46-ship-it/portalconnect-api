"""Optional inbound-vessel feed adapter with deterministic offline fallback."""

from __future__ import annotations

from typing import Any

import httpx

DEFAULT_INBOUND_VESSELS = [
    {"vessel_name": "CMA CGM MARCO POLO", "voyage_number": "0AR82W1MA", "terminal": "LA_PIER_400", "eta": "2026-09-07T08:00:00Z", "projected_lfd_window": "2026-09-12", "congestion_index": "MODERATE"},
    {"vessel_name": "MAERSK MC-KINNEY MOLLER", "voyage_number": "2412E", "terminal": "NY_RED_HOOK", "eta": "2026-09-08T14:30:00Z", "projected_lfd_window": "2026-09-14", "congestion_index": "NORMAL"},
]


async def get_inbound_vessels(feed_url: str | None = None) -> list[dict[str, str]]:
    if not feed_url:
        return DEFAULT_INBOUND_VESSELS
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(feed_url)
            response.raise_for_status()
            payload: Any = response.json()
        records = payload.get("vessels", payload) if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise ValueError("AIS feed must return a list or vessels list")
        required = ("vessel_name", "voyage_number", "terminal", "eta", "projected_lfd_window", "congestion_index")
        normalized = [{key: str(record[key]) for key in required} for record in records if isinstance(record, dict) and all(key in record for key in required)]
        return normalized or DEFAULT_INBOUND_VESSELS
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return DEFAULT_INBOUND_VESSELS
