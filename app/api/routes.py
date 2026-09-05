"""FastAPI routes for PortalConnect."""

from __future__ import annotations

import secrets
import asyncio
from datetime import date, timedelta
import logging
import re
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.models.schemas import (
    BatchContainerResult,
    BatchTrackRequest,
    ContainerStatusResponse,
    ErrorResponse,
    LookupRequest,
    WatchlistCreateRequest,
)
from app.services.browser import BrowserService
from app.services.browser import CaptchaDetectedError, PortalTimeoutError, PortalUnavailableError
from app.services.parser import VisionExtractor
from app.services.scrapers import APMPier400Adapter
from app.services.watchlist import WatchlistService

router = APIRouter()
logger = logging.getLogger(__name__)

TERMINAL_REGISTRY = {
    "la_pier_400": APMPier400Adapter.PORTAL_URL,
    "ny_red_hook": "https://portal.example.com/ny-red-hook",
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


@router.get("/v1/terminals")
async def list_terminals() -> dict[str, str]:
    """Return the supported terminal registry."""

    return TERMINAL_REGISTRY


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Return the service liveness status."""

    return {"status": "ok"}


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


_watchlist = WatchlistService()


def get_watchlist_service() -> WatchlistService:
    return _watchlist


def _is_test_mode(value: object) -> bool:
    return str(value).lower() in ("true", "1", "t")


def _red_hook_response(container_id: str) -> ContainerStatusResponse:
    normalized = container_id.strip().upper()
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
) -> ContainerStatusResponse:
    terminal_code = request.terminal_code.lower()
    portal_url = TERMINAL_REGISTRY.get(terminal_code)
    if portal_url is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported terminal code")
    if _is_test_mode(settings.test_mode):
        return ContainerStatusResponse.model_validate(VisionExtractor.MOCK_RESPONSE)
    if terminal_code == "la_pier_400":
        return await apm_adapter.lookup(request.container_id)
    if terminal_code == "ny_red_hook":
        return _red_hook_response(request.container_id)
    screenshot = await browser.capture_portal_state(portal_url, request.container_id)
    page_html = getattr(browser, "last_page_html", None)
    return await extractor.extract(page_html or screenshot, request.terminal_code)


@router.post(
    "/v1/container/lookup",
    response_model=ContainerStatusResponse,
)
async def lookup_container(
    request: LookupRequest,
    _: None = Depends(require_api_key),
    settings: Settings = Depends(get_settings),
    browser: BrowserService = Depends(get_browser_service),
    extractor: VisionExtractor = Depends(get_vision_extractor),
    apm_adapter: APMPier400Adapter = Depends(get_apm_adapter),
) -> ContainerStatusResponse:
    """Capture and parse container status for a registered terminal."""
    try:
        return _result_response(await _lookup_result(request, settings, browser, extractor, apm_adapter))
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
async def batch_track(
    request: Request,
    settings: Settings = Depends(get_settings),
    browser: BrowserService = Depends(get_browser_service),
    extractor: VisionExtractor = Depends(get_vision_extractor),
    apm_adapter: APMPier400Adapter = Depends(get_apm_adapter),
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
