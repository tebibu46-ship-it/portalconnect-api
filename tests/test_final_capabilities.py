import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import get_fenix_adapter, get_settings, get_watchlist_service, router
from app.core.config import Settings
from app.services.terminal_adapters import FenixPier300Adapter
from app.services.webhook_service import WebhookService


def test_fenix_adapter_returns_active_milestones():
    result = asyncio.run(FenixPier300Adapter().lookup("WFHU5080179"))

    assert result.status == "AVAILABLE"
    assert result.terminal_name == "Fenix Marine Services - Pier 300 (Los Angeles)"
    assert result.location == "FENIX / PIER 300 / BLOCK B12"
    assert result.customs_hold is False


def test_fenix_batch_tracking_uses_registered_adapter():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: Settings(test_mode=False)
    app.dependency_overrides[get_fenix_adapter] = FenixPier300Adapter
    try:
        response = TestClient(app).post(
            "/api/v1/track/batch",
            json={"containers": ["WFHU5080179", "ZZZZ1234567"], "terminal": "fenix_pier_300"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["results"][0]["terminal_name"].startswith("Fenix Marine")


class FakeWatchlist:
    async def list_all(self):
        return [{
            "container_id": "WFHU5080179", "terminal_id": "fenix_pier_300",
            "status": "AVAILABLE", "fees_due": 12.5, "last_free_day": "2099-12-31",
            "last_polled_at": "2026-09-05T00:00:00+00:00",
        }]


def test_ledger_export_returns_rfc4180_csv():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: Settings(api_key="secret")
    app.dependency_overrides[get_watchlist_service] = FakeWatchlist
    try:
        response = TestClient(app).get("/api/v1/ledger/export")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == "attachment; filename=demurrage_ledger.csv"
    assert response.text.splitlines()[0] == "Container ID,Terminal,Status,Holds,Fees Due,Last Free Day,Urgency Level,Timestamp"
    assert "WFHU5080179,fenix_pier_300,AVAILABLE,,12.5,2099-12-31,CRITICAL," in response.text


def test_empty_ledger_export_contains_demo_seed_rows():
    class EmptyWatchlist:
        async def list_all(self):
            return []

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_watchlist_service] = EmptyWatchlist
    try:
        response = TestClient(app).get("/api/v1/ledger/export")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "WFHU5080179" in response.text
    assert "CMAU4928104" in response.text
    assert "FMSU1092834" in response.text


def test_webhook_builds_alert_for_fees_or_urgent_free_time():
    urgent = {"container_id": "WFHU5080179", "terminal_id": "fenix_pier_300", "status": "HOLD", "fees_due": 1.0, "last_free_day": "2099-12-31"}
    payload = WebhookService.build_alert(urgent)

    assert payload is not None
    assert payload["event"] == "demurrage_risk"
    assert payload["urgency_level"] == "CRITICAL"
    assert WebhookService.build_alert({"fees_due": 0, "last_free_day": "2099-12-31"}) is None


def test_webhook_test_accepts_url_and_container_number_aliases():
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post(
        "/api/v1/webhooks/test",
        json={"url": "https://hooks.example.test/portal", "container_number": "WFHU5080179"},
    )

    assert response.status_code == 200
    assert response.json()["payload"]["container_id"] == "WFHU5080179"
