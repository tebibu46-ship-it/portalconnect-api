"""FastAPI application entrypoint."""

import logging
from pathlib import Path
import traceback
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import get_watchlist_service, get_webhook_service, poll_watchlist_alerts, router
from app.models.schemas import ErrorResponse
from app.services.browser import CaptchaDetectedError, PortalTimeoutError, PortalUnavailableError

logger = logging.getLogger(__name__)

async def _alert_poll_worker() -> None:
    while True:
        await poll_watchlist_alerts(get_watchlist_service(), get_webhook_service())
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_watchlist_service().seed_demo_units()
    task = asyncio.create_task(_alert_poll_worker())
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="PortalConnect API", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    """Serve the interactive container tracking dashboard."""

    return FileResponse(
        Path(__file__).parent / "templates" / "index.html",
        media_type="text/html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache", "Expires": "0"},
    )


def _error_response(status_code: int, error_code: str, message: str) -> JSONResponse:
    payload = ErrorResponse(
        status_code=status_code,
        error_code=error_code,
        message=message,
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


@app.exception_handler(PortalTimeoutError)
async def portal_timeout_handler(request: Request, exc: PortalTimeoutError) -> JSONResponse:
    return _error_response(408, "PORTAL_TIMEOUT", str(exc) or "Portal request timed out")


@app.exception_handler(CaptchaDetectedError)
async def captcha_detected_handler(
    request: Request,
    exc: CaptchaDetectedError,
) -> JSONResponse:
    return _error_response(422, "CAPTCHA_DETECTED", str(exc) or "CAPTCHA detected")


@app.exception_handler(PortalUnavailableError)
async def portal_unavailable_handler(
    request: Request,
    exc: PortalUnavailableError,
) -> JSONResponse:
    return _error_response(503, "PORTAL_UNAVAILABLE", str(exc) or "Portal unavailable")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(traceback.format_exc())
    return _error_response(500, "INTERNAL_ERROR", "An unexpected error occurred")


app.include_router(router)
