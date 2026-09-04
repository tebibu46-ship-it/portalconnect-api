from fastapi.testclient import TestClient

from app.api.routes import get_browser_service, get_vision_extractor
from app.core.config import Settings, get_settings
from app.main import app
from app.services.parser import VisionExtractor


class MockBrowser:
    async def capture_portal_state(self, url, container_id):
        return "offline-screenshot"


def build_mock_client():
    app.dependency_overrides[get_settings] = lambda: Settings(
        api_key="integration-key",
        openai_api_key="",
        test_mode=True,
    )
    app.dependency_overrides[get_browser_service] = MockBrowser
    app.dependency_overrides[get_vision_extractor] = lambda: VisionExtractor(
        settings=Settings(openai_api_key="", test_mode=True),
    )
    client = TestClient(app)
    client.headers.update({"X-API-Key": "integration-key"})
    return client


def teardown_overrides():
    app.dependency_overrides.clear()


def test_successful_lookup_uses_mock_mode_with_valid_api_key():
    client = build_mock_client()
    try:
        response = client.post(
            "/v1/container/lookup",
            json={"terminal_code": "ny_red_hook", "container_id": "MSCU1234567"},
        )
    finally:
        teardown_overrides()

    assert response.status_code == 200
    assert response.json() == VisionExtractor.MOCK_RESPONSE


def test_lookup_forbids_missing_or_invalid_api_key():
    client = build_mock_client()
    try:
        missing = client.post(
            "/v1/container/lookup",
            json={"terminal_code": "ny_red_hook", "container_id": "MSCU1234567"},
            headers={"X-API-Key": ""},
        )
        invalid = client.post(
            "/v1/container/lookup",
            json={"terminal_code": "ny_red_hook", "container_id": "MSCU1234567"},
            headers={"X-API-Key": "wrong-key"},
        )
    finally:
        teardown_overrides()

    assert missing.status_code == 403
    assert invalid.status_code == 403


def test_lookup_rejects_malformed_container_id():
    client = build_mock_client()
    try:
        response = client.post(
            "/v1/container/lookup",
            json={"terminal_code": "ny_red_hook", "container_id": "bad-id"},
        )
    finally:
        teardown_overrides()

    assert response.status_code == 422


def test_terminals_returns_supported_registry():
    response = TestClient(app).get("/v1/terminals")

    assert response.status_code == 200
    assert response.json() == {
        "la_pier_400": "https://portal.example.com/la-pier-400",
        "ny_red_hook": "https://portal.example.com/ny-red-hook",
    }


def test_healthz_returns_ok():
    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
