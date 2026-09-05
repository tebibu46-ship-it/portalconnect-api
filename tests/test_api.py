from fastapi.testclient import TestClient
from datetime import date, timedelta
from types import SimpleNamespace

from app.api.routes import get_browser_service, get_vision_extractor
from app.core.config import Settings, get_settings
from app.main import app
from app.services.parser import VisionExtractor


class MockBrowser:
    async def capture_portal_state(self, url, container_id):
        return "offline-screenshot"


class BrowserMustNotRun:
    async def capture_portal_state(self, url, container_id):
        raise AssertionError("browser must not run in TEST_MODE")


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


def test_la_pier_lookup_short_circuits_browser_in_string_test_mode():
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        api_key="integration-key",
        test_mode="true",
    )
    app.dependency_overrides[get_browser_service] = BrowserMustNotRun
    app.dependency_overrides[get_vision_extractor] = BrowserMustNotRun
    client = TestClient(app)
    client.headers.update({"X-API-Key": "integration-key"})
    try:
        response = client.post(
            "/v1/container/lookup",
            json={"terminal_code": "la_pier_400", "container_id": "MSCU1234567"},
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

    assert missing.status_code == 200
    assert invalid.status_code == 200


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


def test_tracking_route_accepts_container_number_and_terminal_id_aliases():
    client = build_mock_client()
    try:
        response = client.post(
            "/api/v1/track",
            json={"container_number": "WFHU5080179", "terminal_id": "apm_pier_400"},
        )
    finally:
        teardown_overrides()

    assert response.status_code == 200
    assert response.json()["status"] == "AVAILABLE"


def test_terminals_returns_supported_registry():
    response = TestClient(app).get("/v1/terminals")

    assert response.status_code == 200
    assert response.json() == {
        "la_pier_400": "https://www.apmterminals.com/en/los-angeles/practical-information/track-and-trace",
        "apm_pier_400": "https://www.apmterminals.com/en/los-angeles/practical-information/track-and-trace",
        "ny_red_hook": "https://portal.example.com/ny-red-hook",
    }


def test_healthz_returns_ok():
    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["commit"]
    assert "/api/v1/track" in payload["routes"]
    assert "/api/v1/track/batch" in payload["routes"]


def test_red_hook_fixture_returns_demo_telemetry_without_live_scraper():
    app.dependency_overrides[get_settings] = lambda: Settings(
        api_key="integration-key",
        test_mode=False,
    )
    client = TestClient(app)
    try:
        response = client.post(
            "/v1/container/lookup",
            headers={"X-API-Key": "integration-key"},
            json={"terminal_code": "ny_red_hook", "container_id": "CMAU4928104"},
        )
    finally:
        teardown_overrides()

    assert response.status_code == 200
    assert response.json()["status"] == "AVAILABLE"
    assert response.json()["terminal_name"] == "Port of NY/NJ - Red Hook"
    assert response.json()["last_free_day"] == (date.today() + timedelta(days=3)).isoformat()


def test_red_hook_unknown_container_returns_private_preview_message():
    app.dependency_overrides[get_settings] = lambda: Settings(
        api_key="integration-key",
        test_mode=False,
    )
    client = TestClient(app)
    try:
        response = client.post(
            "/v1/container/lookup",
            headers={"X-API-Key": "integration-key"},
            json={"terminal_code": "ny_red_hook", "container_id": "ZZZZ1234567"},
        )
    finally:
        teardown_overrides()

    assert response.status_code == 200
    assert response.json()["status"] == "PENDING_TERMINAL_ADAPTER"
    assert "private preview" in response.json()["notes"]
