"""Demurrage exposure calculations."""

from __future__ import annotations

from datetime import date
from typing import Any


def calculate_exposure(rows: list[dict[str, Any]], pickup_date: date) -> float:
    total = 0.0
    for row in rows:
        try:
            overdue_days = max(0, (pickup_date - date.fromisoformat(str(row["last_free_day"]))).days)
        except (KeyError, TypeError, ValueError):
            continue
        total += min(overdue_days, 4) * 150 + max(0, overdue_days - 4) * 300
    return total
