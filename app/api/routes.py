"""FastAPI routes for PortalConnect."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings
from app.models.schemas import ContainerStatusResponse, LookupRequest
from app.services.browser import BrowserService
from app.services.parser import VisionExtractor

router = APIRouter()

TERMINAL_REGISTRY = {
    "la_pier_400": "https://portal.example.com/la-pier-400",
    "ny_red_hook": "https://portal.example.com/ny-red-hook",
}


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


def _is_test_mode(value: object) -> bool:
    return str(value).lower() in ("true", "1", "t")


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
) -> ContainerStatusResponse:
    """Capture and parse container status for a registered terminal."""

    portal_url = TERMINAL_REGISTRY.get(request.terminal_code.lower())
    if portal_url is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unsupported terminal code",
        )

    if _is_test_mode(settings.test_mode):
        return ContainerStatusResponse.model_validate(VisionExtractor.MOCK_RESPONSE)

    screenshot = await browser.capture_portal_state(portal_url, request.container_id)
    page_html = getattr(browser, "last_page_html", None)
    return await extractor.extract(page_html or screenshot, request.terminal_code)
