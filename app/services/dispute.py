"""Carrier demurrage dispute dossier generation."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


def build_dossier(container_id: str, row: dict[str, Any] | None = None) -> dict[str, Any]:
    row = row or {}
    normalized = container_id.strip().upper()
    lfd = str(row.get("last_free_day", "UNKNOWN"))
    try:
        overdue_days = max(0, (date.today() - date.fromisoformat(lfd)).days)
    except ValueError:
        overdue_days = 0
    tier_one_days = min(overdue_days, 4)
    tier_two_days = max(0, overdue_days - 4)
    tariff = {
        "days_1_4": {"days": tier_one_days, "rate_per_day": 150.0, "amount": tier_one_days * 150.0},
        "days_5_plus": {"days": tier_two_days, "rate_per_day": 300.0, "amount": tier_two_days * 300.0},
    }
    contested = float(row.get("fees_due", 0) or 0)
    terminal = str(row.get("terminal_id", "UNKNOWN"))
    carrier = normalized[:4] or "UNKNOWN"
    discharged = row.get("last_polled_at") or datetime.now(timezone.utc).isoformat()
    statement = "Audit telemetry captured via PortalConnect Engine. Demurrage contested under FMC OSRA-22 demurrage rules."
    return {
        "container_id": normalized,
        "carrier": carrier,
        "terminal": terminal,
        "vessel_discharge_timestamp": discharged,
        "last_free_day": lfd,
        "terminal_hold_history": [{"status": row.get("status", "UNKNOWN"), "resolved_at": row.get("last_polled_at")}],
        "tariff_tier_breakdown": tariff,
        "contested_amount": contested,
        "statement": statement,
        "report": f"# PortalConnect Demurrage Dispute Dossier\n\nContainer: {normalized}\nCarrier: {carrier}\nTerminal: {terminal}\nVessel discharge: {discharged}\nLast free day: {lfd}\n\n## Tariff\n- Days 1-4: {tier_one_days} × $150 = ${tariff['days_1_4']['amount']:.2f}\n- Days 5+: {tier_two_days} × $300 = ${tariff['days_5_plus']['amount']:.2f}\n- Contested amount: ${contested:.2f}\n\n{statement}\n",
    }
