"""Carrier demurrage dispute dossier generation."""

from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
from html import escape
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
    verification_id = sha256(f"{normalized}|{terminal}|{discharged}|{lfd}|{contested:.2f}".encode()).hexdigest()[:24].upper()
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
        "verification_id": verification_id,
        "report": f"# PortalConnect Demurrage Dispute Dossier\n\nContainer: {normalized}\nCarrier: {carrier}\nTerminal: {terminal}\nVessel discharge: {discharged}\nLast free day: {lfd}\n\n## Tariff\n- Days 1-4: {tier_one_days} × $150 = ${tariff['days_1_4']['amount']:.2f}\n- Days 5+: {tier_two_days} × $300 = ${tariff['days_5_plus']['amount']:.2f}\n- Contested amount: ${contested:.2f}\n\n{statement}\n\nVerification ID: {verification_id}\n",
    }


def render_printable_dossier(dossier: dict[str, Any]) -> str:
    """Render a self-contained HTML packet suitable for browser PDF printing."""
    tariff = dossier["tariff_tier_breakdown"]
    tariff_rows = "".join(
        f"<tr><td>{label}</td><td>{entry['days']}</td><td>${entry['rate_per_day']:.2f}</td><td>${entry['amount']:.2f}</td></tr>"
        for label, entry in (("Days 1–4", tariff["days_1_4"]), ("Days 5+", tariff["days_5_plus"]))
    )
    hold_rows = "".join(
        f"<tr><td>{escape(str(item.get('status')))}</td><td>{escape(str(item.get('resolved_at')))}</td></tr>"
        for item in dossier["terminal_hold_history"]
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Dispute dossier — {escape(dossier['container_id'])}</title>
<style>body{{font:15px Arial,sans-serif;color:#18212b;margin:48px;line-height:1.5}}header{{border-bottom:4px solid #0b5cff;padding-bottom:18px}}h1{{font-size:26px;margin:0}}h2{{margin-top:30px;border-bottom:1px solid #ccd3dc;padding-bottom:6px}}.meta{{display:grid;grid-template-columns:1fr 1fr;gap:10px;background:#f3f6fa;padding:18px}}table{{width:100%;border-collapse:collapse}}th,td{{border:1px solid #ccd3dc;padding:9px;text-align:left}}th{{background:#e8eef5}}.hash{{font-family:monospace;word-break:break-all}}@media print{{body{{margin:24px}}.no-print{{display:none}}}}</style></head>
<body><header><div>OFFICIAL FMC OSRA-22 CONTESTED CHARGE</div><h1>PortalConnect Carrier Dispute Dossier</h1><p>Audit-grade terminal telemetry packet</p></header>
<h2>Shipment identity</h2><div class="meta"><div><b>Container ID</b><br>{escape(dossier['container_id'])}</div><div><b>Carrier</b><br>{escape(dossier['carrier'])}</div><div><b>Port / Terminal</b><br>{escape(dossier['terminal'])}</div><div><b>Vessel discharge</b><br>{escape(str(dossier['vessel_discharge_timestamp']))}</div><div><b>Last free day</b><br>{escape(dossier['last_free_day'])}</div><div><b>Contested amount</b><br>${dossier['contested_amount']:.2f}</div></div>
<h2>Terminal hold chronology &amp; wire telemetry</h2><table><thead><tr><th>Status</th><th>Resolution / telemetry timestamp</th></tr></thead><tbody>{hold_rows}</tbody></table>
<h2>Tariff tier breakdown</h2><table><thead><tr><th>Tier</th><th>Days</th><th>Rate / day</th><th>Amount</th></tr></thead><tbody>{tariff_rows}</tbody></table>
<h2>Formal declaration</h2><p>{escape(dossier['statement'])}</p><p class="hash"><b>Verification ID:</b> {escape(dossier['verification_id'])}</p><p class="no-print"><button onclick="window.print()">Print / Save as PDF</button></p></body></html>"""
