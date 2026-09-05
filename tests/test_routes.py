from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import (
    get_browser_service,
    get_apm_adapter,
    get_vision_extractor,
    router,
)
from app.core.config import Settings, get_settings
from app.models.schemas import ContainerStatusResponse


class FakeBrowser:
    def __init__(self):
        self.calls = []

    async def capture_portal_state(self, url, container_id):
        self.calls.append((url, container_id))
        return "base64-screenshot"


class FakeExtractor:
    def __init__(self):
        self.calls = []

    async def extract(self, screenshot, terminal_code):
        self.calls.append((screenshot, terminal_code))
        return ContainerStatusResponse(
            container_id="MSCU1234567",
            terminal_name="La Pier 400",
            status="AVAILABLE",
            fees_due=0.0,
            customs_hold=False,
            last_free_day="2026-09-04",
            location="YARD-A1",
        )


class FakeAPMAdapter:
    def __init__(self):
        self.calls = []

    async def lookup(self, container_id):
        self.calls.append(container_id)
        return ContainerStatusResponse(
            container_id=container_id,
            terminal_name="APM Terminals - Pier 400 (Los Angeles)",
            status="AVAILABLE",
            fees_due=0.0,
            customs_hold=False,
            last_free_day="2026-09-04",
            location="YARD-A1",
        )


def build_test_client():
    app = FastAPI()
    app.include_router(router)
    browser = FakeBrowser()
    extractor = FakeExtractor()
    apm_adapter = FakeAPMAdapter()
    app.dependency_overrides[get_settings] = lambda: Settings(api_key="secret")
    app.dependency_overrides[get_browser_service] = lambda: browser
    app.dependency_overrides[get_vision_extractor] = lambda: extractor
    app.dependency_overrides[get_apm_adapter] = lambda: apm_adapter
    return TestClient(app), browser, extractor, apm_adapter


def test_lookup_route_authenticates_and_coordinates_services():
    client, browser, extractor, apm_adapter = build_test_client()

    response = client.post(
        "/v1/container/lookup",
        headers={"X-API-Key": "secret"},
        json={"terminal_code": " la_pier_400 ", "container_id": "mscu1234567"},
    )

    assert response.status_code == 200
    assert response.json()["container_id"] == "MSCU1234567"
    assert apm_adapter.calls == ["MSCU1234567"]


def test_lookup_route_rejects_invalid_api_key():
    client, _, _, _ = build_test_client()

    response = client.post(
        "/v1/container/lookup",
        headers={"X-API-Key": "wrong"},
        json={"terminal_code": "ny_red_hook", "container_id": "MSCU1234567"},
    )

    assert response.status_code == 403


def test_tracking_aliases_resolve_under_api_and_root_prefixes():
    client, _, _, _ = build_test_client()
    payload = {"terminal_code": "la_pier_400", "container_id": "MSCU1234567"}

    api_response = client.post("/api/v1/track", headers={"X-API-Key": "secret"}, json=payload)
    root_response = client.post("/track", headers={"X-API-Key": "secret"}, json=payload)
    batch_response = client.post(
        "/track/batch",
        json={"containers": ["MSCU1234567"], "terminal": "la_pier_400"},
    )

    assert api_response.status_code == 200
    assert root_response.status_code == 200
    assert batch_response.status_code == 200
