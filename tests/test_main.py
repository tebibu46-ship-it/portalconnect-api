from fastapi.testclient import TestClient

from app.api.routes import get_browser_service, get_vision_extractor
from app.core.config import Settings, get_settings
from app.main import app
from app.services.browser import CaptchaDetectedError, PortalTimeoutError


class RaisingBrowser:
    def __init__(self, exception):
        self.exception = exception

    async def capture_portal_state(self, url, container_id):
        raise self.exception


class UnusedExtractor:
    async def extract(self, screenshot, terminal_code):
        raise AssertionError("extractor should not be called")


def request_with_browser(browser):
    app.dependency_overrides[get_settings] = lambda: Settings(api_key="test-key")
    app.dependency_overrides[get_browser_service] = lambda: browser
    app.dependency_overrides[get_vision_extractor] = UnusedExtractor
    client = TestClient(app, raise_server_exceptions=False)
    client.headers.update({"X-API-Key": "test-key"})
    return client


def teardown_overrides():
    app.dependency_overrides.clear()


def test_portal_timeout_returns_structured_408():
    client = request_with_browser(RaisingBrowser(PortalTimeoutError("upstream timed out")))
    try:
        response = client.post(
            "/v1/container/lookup",
            json={"terminal_code": "la_pier_400", "container_id": "MSCU1234567"},
        )
    finally:
        teardown_overrides()

    assert response.status_code == 408
    assert response.json() == {
        "status_code": 408,
        "error_code": "PORTAL_TIMEOUT",
        "message": "upstream timed out",
    }


def test_captcha_returns_structured_422():
    client = request_with_browser(RaisingBrowser(CaptchaDetectedError("challenge found")))
    try:
        response = client.post(
            "/v1/container/lookup",
            json={"terminal_code": "la_pier_400", "container_id": "MSCU1234567"},
        )
    finally:
        teardown_overrides()

    assert response.status_code == 422
    assert response.json() == {
        "status_code": 422,
        "error_code": "CAPTCHA_DETECTED",
        "message": "challenge found",
    }


def test_unhandled_exception_returns_structured_500():
    client = request_with_browser(RaisingBrowser(RuntimeError("secret internal detail")))
    try:
        response = client.post(
            "/v1/container/lookup",
            json={"terminal_code": "la_pier_400", "container_id": "MSCU1234567"},
        )
    finally:
        teardown_overrides()

    assert response.status_code == 500
    assert response.json() == {
        "status_code": 500,
        "error_code": "INTERNAL_ERROR",
        "message": "An unexpected error occurred",
    }


def test_cors_middleware_allows_preflight_requests():
    response = TestClient(app).options(
        "/v1/container/lookup",
        headers={
            "Origin": "https://client.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


def test_root_redirects_to_api_docs():
    response = TestClient(app).get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"
