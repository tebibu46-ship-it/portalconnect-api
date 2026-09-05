from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import get_apm_adapter, get_browser_service, get_vision_extractor, router
from app.core.config import Settings, get_settings
from app.models.schemas import ContainerStatusResponse


class FakeAdapter:
    async def lookup(self, container_id: str) -> ContainerStatusResponse:
        if container_id == "MSKU9018201":
            raise RuntimeError("terminal temporarily unavailable")
        return ContainerStatusResponse(
            container_id=container_id,
            terminal_name="APM Terminals - Pier 400 (Los Angeles)",
            status="AVAILABLE",
            fees_due=0.0,
            customs_hold=False,
            last_free_day="2099-12-31",
            location="PIER 400 / TEST YARD",
        )


def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: Settings(api_key="secret", test_mode=False)
    app.dependency_overrides[get_apm_adapter] = FakeAdapter
    app.dependency_overrides[get_browser_service] = lambda: object()
    app.dependency_overrides[get_vision_extractor] = lambda: object()
    return TestClient(app)


def test_batch_json_resolves_multiple_containers():
    response = client().post(
        "/api/v1/track/batch",
        headers={"X-API-Key": "secret"},
        json={"containers": ["wfhu5080179", "MSKU9018201"], "terminal": "la_pier_400"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["succeeded"] == 1
    assert payload["results"][0]["container_id"] == "WFHU5080179"
    assert payload["results"][1]["status"] == "LOOKUP_FAILED"


def test_batch_json_allows_unauthenticated_post():
    response = client().post(
        "/api/v1/track/batch",
        json={"containers": ["WFHU5080179"], "terminal": "la_pier_400"},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["container_id"] == "WFHU5080179"


def test_batch_route_accepts_terminal_id_alias():
    response = client().post(
        "/api/v1/track/batch",
        json={"containers": ["WFHU5080179"], "terminal_id": "apm_pier_400"},
    )

    assert response.status_code == 200


def test_batch_manifest_parses_messy_csv_whitespace():
    response = client().post(
        "/api/v1/track/batch",
        headers={"X-API-Key": "secret"},
        files={"file": ("manifest.csv", "  WFHU5080179, ignored\nMSKU9018201 ; extra", "text/csv")},
        data={"terminal": "la_pier_400"},
    )

    assert response.status_code == 200
    assert [row["container_id"] for row in response.json()["results"]] == [
        "WFHU5080179",
        "MSKU9018201",
    ]


def test_batch_rejects_manifest_without_iso_container_ids():
    response = client().post(
        "/api/v1/track/batch",
        headers={"X-API-Key": "secret"},
        files={"file": ("manifest.txt", "not-a-container", "text/plain")},
        data={"terminal": "la_pier_400"},
    )

    assert response.status_code == 422
