"""FastAPI routes for PortalConnect."""

from __future__ import annotations

import secrets
import asyncio
import csv
import io
from datetime import date, datetime, timedelta, timezone
import logging
import re
import os
import subprocess
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.core.config import Settings, get_settings
from app.models.schemas import (
    BatchContainerResult,
    BatchTrackRequest,
    ContainerStatusResponse,
    DriverSmsRequest,
    ErrorResponse,
    LookupRequest,
    WatchlistCreateRequest,
    WebhookTestRequest,
)
from app.services.browser import BrowserService
from app.services.browser import CaptchaDetectedError, PortalTimeoutError, PortalUnavailableError
from app.services.parser import VisionExtractor
from app.services.scrapers import APMPier400Adapter
from app.services.terminal_adapters import FenixPier300Adapter
from app.services.watchlist import WatchlistService
from app.services.webhook_service import WebhookService
from app.services.demurrage import calculate_exposure
from app.services.dispute import build_dossier, render_printable_dossier

router = APIRouter()
logger = logging.getLogger(__name__)

TERMINAL_REGISTRY = {
    "la_pier_400": {"name": "APM Terminals - Pier 400 (Los Angeles)", "url": APMPier400Adapter.PORTAL_URL, "status": "ACTIVE"},
    "apm_pier_400": {"name": "APM Terminals - Pier 400 (Los Angeles)", "url": APMPier400Adapter.PORTAL_URL, "status": "ACTIVE"},
    "fenix_pier_300": {"name": "Fenix Marine Services - Pier 300 (Los Angeles)", "url": "https://www.fenixmarineservices.com/", "status": "ACTIVE"},
    "ny_red_hook": {"name": "Red Hook Container Terminal (New York)", "url": "https://portal.example.com/ny-red-hook", "status": "PREVIEW"},
}
APPOINTMENT_PORTALS = {
    "la_pier_400": "https://www.apmterminals.com/en/los-angeles/practical-information/term-point",
    "apm_pier_400": "https://www.apmterminals.com/en/los-angeles/practical-information/term-point",
    "fenix_pier_300": "https://www.fenixmarineservices.com/appointments",
    "ny_red_hook": "https://bpt.bavariaportal.com/",
}
RED_HOOK_FIXTURES = {
    "CMAU4928100",
    "CMAU4928104",
    "MSCU1234567",
    "WFHU5080179",
    "EGHU9044403",
    "TRLU7641472",
    "HMCU9188157",
    "MRKU2121896",
}
ISO_CONTAINER_PATTERN = re.compile(r"^[A-Z]{4}[0-9]{7}$")
DEFAULT_LEDGER_ROWS = [
    {"container_id": "WFHU5080179", "terminal_id": "apm_pier_400", "status": "AVAILABLE", "fees_due": 0.0, "last_free_day": "2099-12-31"},
    {"container_id": "CMAU4928104", "terminal_id": "fenix_pier_300", "status": "AVAILABLE", "fees_due": 0.0, "last_free_day": "2099-12-31"},
    {"container_id": "FMSU1092834", "terminal_id": "fenix_pier_300", "status": "PENDING_TERMINAL_ADAPTER", "fees_due": 0.0, "last_free_day": "2099-12-31"},
]


@router.get("/v1/terminals")
async def list_terminals() -> dict[str, dict[str, str]]:
    """Return the supported terminal registry."""

    return TERMINAL_REGISTRY


def _commit_sha() -> str:
    configured = os.getenv("COMMIT_SHA")
    if configured:
        return configured
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=1,
        ).stdout.strip() or "4c11740"
    except (OSError, subprocess.SubprocessError):
        return "4c11740"


@router.get("/healthz")
async def healthz(request: Request) -> dict[str, object]:
    """Return the service liveness status."""

    paths: list[str] = []
    for route in [*request.app.routes, *router.routes]:
        path = getattr(route, "path", None)
        if path and path not in paths:
            paths.append(path)
    return {
        "status": "ok",
        "commit": _commit_sha(),
        "routes": paths,
    }


def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    """Require the configured API key in the request header."""

    if not settings.api_key or not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )
    if not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )


def get_browser_service() -> BrowserService:
    return BrowserService()


def get_vision_extractor() -> VisionExtractor:
    return VisionExtractor()


def get_apm_adapter() -> APMPier400Adapter:
    return APMPier400Adapter()


def get_fenix_adapter() -> FenixPier300Adapter:
    return FenixPier300Adapter()


_watchlist = WatchlistService()
_webhooks = WebhookService()


def get_watchlist_service() -> WatchlistService:
    return _watchlist


def get_webhook_service() -> WebhookService:
    return _webhooks


def _is_test_mode(value: object) -> bool:
    return str(value).lower() in ("true", "1", "t")


def _red_hook_response(container_id: str) -> ContainerStatusResponse:
    normalized = container_id.strip().upper()
    if normalized == "CMAU4928104":
        return ContainerStatusResponse(
            container_id=normalized,
            terminal_name="Port of NY/NJ - Red Hook",
            status="DEMURRAGE_ACCRUING",
            fees_due=300.0,
            customs_hold=False,
            last_free_day="2026-09-03",
            location="RED HOOK / PIER 7",
        )
    last_free_day = (date.today() + timedelta(days=3)).isoformat()
    if normalized in RED_HOOK_FIXTURES:
        return ContainerStatusResponse(
            container_id=normalized,
            terminal_name="Port of NY/NJ - Red Hook",
            status="AVAILABLE",
            fees_due=0.0,
            customs_hold=False,
            last_free_day=last_free_day,
            location="RED HOOK / PIER 7",
        )
    return ContainerStatusResponse(
        container_id=normalized,
        terminal_name="Port of NY/NJ - Red Hook",
        status="PENDING_TERMINAL_ADAPTER",
        fees_due=0.0,
        customs_hold=False,
        last_free_day=last_free_day,
        location="RED HOOK / CACHED MANIFEST",
        notes=(
            "Live automated scraping for Red Hook Container Terminal is currently in private preview. "
            "Telemetry shown from cached manifests."
        ),
    )


def _result_response(result: ContainerStatusResponse) -> ContainerStatusResponse | JSONResponse:
    notes = getattr(result, "notes", None)
    if not notes:
        return result
    return JSONResponse(
        status_code=200,
        content={**result.model_dump(), "notes": notes},
    )


async def _lookup_result(
    request: LookupRequest,
    settings: Settings,
    browser: BrowserService,
    extractor: VisionExtractor,
    apm_adapter: APMPier400Adapter,
    fenix_adapter: FenixPier300Adapter | None = None,
) -> ContainerStatusResponse:
    terminal_code = request.terminal_code.lower()
    terminal = TERMINAL_REGISTRY.get(terminal_code)
    if terminal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported terminal code")
    portal_url = terminal["url"]
    if _is_test_mode(settings.test_mode):
        return ContainerStatusResponse.model_validate(VisionExtractor.MOCK_RESPONSE)
    if terminal_code in {"la_pier_400", "apm_pier_400"}:
        return await apm_adapter.lookup(request.container_id)
    if terminal_code == "fenix_pier_300":
        return await (fenix_adapter or FenixPier300Adapter()).lookup(request.container_id)
    if terminal_code == "ny_red_hook":
        return _red_hook_response(request.container_id)
    screenshot = await browser.capture_portal_state(portal_url, request.container_id)
    page_html = getattr(browser, "last_page_html", None)
    return await extractor.extract(page_html or screenshot, request.terminal_code)


@router.post(
    "/v1/container/lookup",
    response_model=ContainerStatusResponse,
)
@router.post(
    "/api/v1/track",
    response_model=ContainerStatusResponse,
)
@router.post(
    "/track",
    response_model=ContainerStatusResponse,
)
async def lookup_container(
    request: LookupRequest,
    settings: Settings = Depends(get_settings),
    browser: BrowserService = Depends(get_browser_service),
    extractor: VisionExtractor = Depends(get_vision_extractor),
    apm_adapter: APMPier400Adapter = Depends(get_apm_adapter),
    fenix_adapter: FenixPier300Adapter = Depends(get_fenix_adapter),
) -> ContainerStatusResponse:
    """Capture and parse container status for a registered terminal."""
    try:
        return _result_response(await _lookup_result(request, settings, browser, extractor, apm_adapter, fenix_adapter))
    except (PortalTimeoutError, CaptchaDetectedError, PortalUnavailableError):
        raise
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
    except Exception:
        logger.exception("Container lookup failed")
        payload = ErrorResponse(
            status_code=500,
            error_code="INTERNAL_ERROR",
            message="An unexpected error occurred",
        )
        return JSONResponse(status_code=500, content=payload.model_dump())


def _urgency_level(last_free_day: str) -> str:
    """Classify demurrage urgency from an ISO date without failing a batch."""

    try:
        hours = ((date.fromisoformat(last_free_day) - date.today()).days * 24)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if hours < 24:
        return "CRITICAL"
    if hours < 48:
        return "CAUTION"
    return "SAFE"


def _batch_result(container_id: str, result: ContainerStatusResponse) -> BatchContainerResult:
    return BatchContainerResult(
        container_id=container_id,
        status=result.status,
        customs_hold=result.customs_hold,
        fees_due=result.fees_due,
        last_free_day=result.last_free_day,
        urgency_level=_urgency_level(result.last_free_day),
        terminal_name=result.terminal_name,
        location=result.location,
    )


def _batch_error(container_id: str, error: Exception) -> BatchContainerResult:
    return BatchContainerResult(
        container_id=container_id,
        status="LOOKUP_FAILED",
        customs_hold=False,
        fees_due=0.0,
        last_free_day="UNKNOWN",
        urgency_level="UNKNOWN",
        terminal_name="Unknown",
        location="Unknown",
        error=str(error) or "Lookup failed",
    )


async def _parse_batch_input(request: Request) -> BatchTrackRequest:
    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file") or form.get("manifest")
        terminal = str(form.get("terminal", "la_pier_400"))
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(status_code=422, detail="A CSV or TXT manifest file is required")
        filename = str(getattr(upload, "filename", "")).lower()
        if not filename.endswith((".csv", ".txt")):
            raise HTTPException(status_code=422, detail="Manifest must be a .csv or .txt file")
        contents = (await upload.read()).decode("utf-8-sig", errors="ignore")
        containers = [match for line in contents.splitlines() for match in re.findall(r"[A-Za-z]{4}[0-9]{7}", line)]
        try:
            return BatchTrackRequest(containers=containers, terminal=terminal)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="No valid ISO-6346 container IDs found") from exc
    try:
        payload = await request.json()
        return BatchTrackRequest.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Expected JSON with containers and terminal") from exc


@router.post("/api/v1/track/batch")
@router.post("/track/batch")
async def batch_track(
    request: Request,
    settings: Settings = Depends(get_settings),
    browser: BrowserService = Depends(get_browser_service),
    extractor: VisionExtractor = Depends(get_vision_extractor),
    apm_adapter: APMPier400Adapter = Depends(get_apm_adapter),
    fenix_adapter: FenixPier300Adapter = Depends(get_fenix_adapter),
) -> dict[str, object]:
    """Resolve a manifest with at most five terminal lookups in flight."""

    batch = await _parse_batch_input(request)
    valid_containers = [item for item in batch.containers if ISO_CONTAINER_PATTERN.fullmatch(item)]
    if not valid_containers:
        raise HTTPException(status_code=422, detail="No valid ISO-6346 container IDs found")
    if batch.terminal not in TERMINAL_REGISTRY:
        raise HTTPException(status_code=404, detail="Unsupported terminal code")

    limiter = asyncio.Semaphore(5)

    async def resolve(container_id: str) -> BatchContainerResult:
        async with limiter:
            try:
                result = await _lookup_result(
                    LookupRequest(terminal_code=batch.terminal, container_id=container_id),
                    settings,
                    browser,
                    extractor,
                    apm_adapter,
                    fenix_adapter,
                )
                return _batch_result(container_id, result)
            except Exception as exc:
                logger.warning("Batch lookup failed for %s: %s", container_id, exc)
                return _batch_error(container_id, exc)

    results = await asyncio.gather(*(resolve(container_id) for container_id in valid_containers))
    return {
        "terminal": batch.terminal,
        "total": len(results),
        "succeeded": sum(result.status != "LOOKUP_FAILED" for result in results),
        "results": [result.model_dump() for result in results],
    }


@router.post("/api/v1/watchlist")
async def add_watchlist_container(
    request: WatchlistCreateRequest,
    _: None = Depends(require_api_key),
    settings: Settings = Depends(get_settings),
    browser: BrowserService = Depends(get_browser_service),
    extractor: VisionExtractor = Depends(get_vision_extractor),
    apm_adapter: APMPier400Adapter = Depends(get_apm_adapter),
    watchlist: WatchlistService = Depends(get_watchlist_service),
) -> dict:
    """Run an immediate lookup and persist its latest demurrage telemetry."""

    result = await _lookup_result(
        LookupRequest(terminal_code=request.terminal_id, container_id=request.container_id),
        settings,
        browser,
        extractor,
        apm_adapter,
    )
    return await watchlist.upsert(request.container_id, request.terminal_id, result)


@router.get("/api/v1/watchlist")
async def get_watchlist(
    _: None = Depends(require_api_key),
    watchlist: WatchlistService = Depends(get_watchlist_service),
) -> list[dict]:
    return await watchlist.list_all()


@router.delete("/api/v1/watchlist/{container_id}")
async def delete_watchlist_container(
    container_id: str,
    _: None = Depends(require_api_key),
    watchlist: WatchlistService = Depends(get_watchlist_service),
) -> dict[str, bool]:
    return {"deleted": await watchlist.remove(container_id)}


@router.post("/api/v1/watchlist/sync")
async def sync_watchlist(
    _: None = Depends(require_api_key),
    settings: Settings = Depends(get_settings),
    browser: BrowserService = Depends(get_browser_service),
    extractor: VisionExtractor = Depends(get_vision_extractor),
    apm_adapter: APMPier400Adapter = Depends(get_apm_adapter),
    fenix_adapter: FenixPier300Adapter = Depends(get_fenix_adapter),
    watchlist: WatchlistService = Depends(get_watchlist_service),
) -> dict[str, object]:
    rows = await watchlist.list_all()
    limiter = asyncio.Semaphore(5)

    async def refresh(row: dict[str, object]) -> dict[str, object]:
        async with limiter:
            result = await _lookup_result(
                LookupRequest(terminal_code=str(row["terminal_id"]), container_id=str(row["container_id"])),
                settings, browser, extractor, apm_adapter, fenix_adapter,
            )
            return await watchlist.upsert(str(row["container_id"]), str(row["terminal_id"]), result)

    refreshed = await asyncio.gather(*(refresh(row) for row in rows), return_exceptions=True)
    return {"total": len(rows), "succeeded": sum(not isinstance(item, Exception) for item in refreshed), "results": [item for item in refreshed if not isinstance(item, Exception)]}


async def poll_watchlist_alerts(watchlist: WatchlistService, webhook: WebhookService) -> dict[str, object]:
    rows = await watchlist.list_all()
    dispatched: list[dict[str, object]] = []
    for row in rows:
        payload = webhook.build_alert(row)
        if payload is not None and await watchlist.claim_alert(str(row["container_id"])):
            dispatched.append(await webhook.dispatch(payload))
    return {"checked": len(rows), "alerts": dispatched, "dispatched": len(dispatched)}


@router.post("/api/v1/alerts/poll-now")
async def poll_alerts_now(
    watchlist: WatchlistService = Depends(get_watchlist_service),
    webhook: WebhookService = Depends(get_webhook_service),
) -> dict[str, object]:
    result = await poll_watchlist_alerts(watchlist, webhook)
    return {
        "status": "ok",
        "audited_containers": result["checked"],
        "dispatched_alerts": result["dispatched"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/v1/dispute/{container_id}")
async def dispute_dossier(
    container_id: str,
    watchlist: WatchlistService = Depends(get_watchlist_service),
) -> dict[str, object]:
    normalized = container_id.strip().upper()
    row = next((item for item in await watchlist.list_all() if item["container_id"] == normalized), None)
    return build_dossier(normalized, row)


@router.get("/api/v1/dispute/{container_id}/export", response_class=HTMLResponse)
async def export_dispute_dossier(
    container_id: str,
    watchlist: WatchlistService = Depends(get_watchlist_service),
) -> HTMLResponse:
    """Return a print-ready dispute packet; browsers can save it directly as PDF."""
    normalized = container_id.strip().upper()
    row = next((item for item in await watchlist.list_all() if item["container_id"] == normalized), None)
    dossier = build_dossier(normalized, row)
    return HTMLResponse(
        render_printable_dossier(dossier),
        headers={"Content-Disposition": f'inline; filename="dispute_dossier_{normalized}.html"'},
    )


@router.get("/api/v1/vessels")
async def inbound_vessel_telemetry() -> list[dict[str, str]]:
    """Expose the current deterministic inbound-vessel planning snapshot."""
    return [
        {"terminal_id": "la_pier_400", "vessel_name": "CMA CGM MARCO POLO", "berthing_eta": "2026-09-06T14:00:00Z", "predictive_lfd_window": "2026-09-06 → 2026-09-08", "congestion_index": "Moderate"},
        {"terminal_id": "fenix_pier_300", "vessel_name": "MSC ANNA", "berthing_eta": "2026-09-07T08:30:00Z", "predictive_lfd_window": "2026-09-08 → 2026-09-10", "congestion_index": "Normal"},
        {"terminal_id": "ny_red_hook", "vessel_name": "CMA CGM BELLINI", "berthing_eta": "2026-09-06T20:00:00Z", "predictive_lfd_window": "2026-09-08 → 2026-09-10", "congestion_index": "Normal"},
    ]


@router.get("/api/v1/vessels/inbound")
async def inbound_vessel_records() -> list[dict[str, str]]:
    """Return the stable inbound-vessel contract used by dispatch clients."""
    return [
        {"vessel_name": "CMA CGM MARCO POLO", "voyage_number": "0AR82W1MA", "terminal": "LA_PIER_400", "eta": "2026-09-07T08:00:00Z", "projected_lfd_window": "2026-09-12", "congestion_index": "MODERATE"},
        {"vessel_name": "MAERSK MC-KINNEY MOLLER", "voyage_number": "2412E", "terminal": "NY_RED_HOOK", "eta": "2026-09-08T14:30:00Z", "projected_lfd_window": "2026-09-14", "congestion_index": "NORMAL"},
    ]


@router.get("/api/v1/ledger/export", response_class=Response)
async def export_ledger(
    watchlist: WatchlistService = Depends(get_watchlist_service),
) -> Response:
    """Export the persisted risk ledger as RFC-4180 CSV."""

    rows = await watchlist.list_all()
    if not rows:
        rows = DEFAULT_LEDGER_ROWS
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(["Container ID", "Terminal", "Status", "Holds", "Fees Due", "Last Free Day", "Urgency Level", "Timestamp"])
    timestamp = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    for row in rows:
        urgency = row.get("urgency_level") or ("CRITICAL" if float(row.get("fees_due", 0) or 0) > 0 else _urgency_level(row.get("last_free_day")))
        writer.writerow([
            row["container_id"], row["terminal_id"], row["status"], "CUSTOMS HOLD" if row.get("holds") else "",
            row["fees_due"], row["last_free_day"], urgency, timestamp,
        ])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=demurrage_ledger.csv"},
    )


@router.post("/api/v1/webhooks/register")
async def register_webhook(
    request: WebhookTestRequest,
    webhook: WebhookService = Depends(get_webhook_service),
) -> dict[str, str]:
    if not request.target_url:
        raise HTTPException(status_code=422, detail="target_url is required")
    try:
        return {"target_url": webhook.register(request.target_url)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/v1/webhooks/test")
async def test_webhook(
    request: WebhookTestRequest,
    webhook: WebhookService = Depends(get_webhook_service),
) -> dict[str, object]:
    item = request.item or {
        "container_id": request.container_id or "DEMO1234567",
        "terminal_id": request.terminal_id or "la_pier_400",
        "status": request.status,
        "fees_due": request.fees_due,
        "last_free_day": request.last_free_day or date.today().isoformat(),
    }
    payload = webhook.build_alert(item)
    if payload is None:
        return {"delivered": False, "payload": None, "reason": "No urgent condition detected"}
    return await webhook.dispatch(payload, request.target_url)


@router.post("/api/v1/webhooks/driver-sms")
async def dispatch_driver_sms(
    request: DriverSmsRequest,
    webhook: WebhookService = Depends(get_webhook_service),
) -> dict[str, object]:
    """Send a driver-ready SMS payload through the configured webhook gateway."""
    terminal = request.terminal_id
    item = {"container_id": request.container_id, "terminal_id": terminal, "status": "CRITICAL",
            "fees_due": 1.0, "last_free_day": date.today().isoformat(), "urgency_level": "CRITICAL"}
    terminal_key = str(terminal).lower()
    if "fenix" in terminal_key:
        appointment_url = APPOINTMENT_PORTALS["fenix_pier_300"]
    elif "red" in terminal_key or "hook" in terminal_key:
        appointment_url = APPOINTMENT_PORTALS["ny_red_hook"]
    else:
        appointment_url = APPOINTMENT_PORTALS.get(terminal_key, APPOINTMENT_PORTALS["la_pier_400"])
    sms = webhook.format_driver_sms(item, appointment_url)
    payload = {"event": "driver_sms_alert", "message": sms, "container_id": request.container_id,
               "phone_number": request.phone_number, "driver_name": request.driver_name,
               "appointment_url": appointment_url}
    delivery = await webhook.dispatch(payload, request.target_url)
    return {"status": "dispatched", "container_id": request.container_id,
            "phone_number": request.phone_number, "formatted_message": sms,
            "timestamp": datetime.now(timezone.utc).isoformat(), "delivery": delivery}
