"""FastAPI application entrypoint."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.models.schemas import ErrorResponse
from app.services.browser import CaptchaDetectedError, PortalTimeoutError

app = FastAPI(title="PortalConnect API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return _error_response(500, "INTERNAL_ERROR", "An unexpected error occurred")


app.include_router(router)
