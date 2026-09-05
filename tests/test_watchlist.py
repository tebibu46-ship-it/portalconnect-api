from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.api.routes import get_settings, get_watchlist_service
from app.core.config import Settings
from app.main import app
from app.services.watchlist import WatchlistService


def test_watchlist_service_crud_and_date_sorting(tmp_path):
    service = WatchlistService(tmp_path / "watchlist.db")

    import asyncio

    async def scenario():
        from app.models.schemas import ContainerStatusResponse

        early = ContainerStatusResponse(
            container_id="AAAA1234567", terminal_name="Pier 400", status="HOLD",
            fees_due=12.5, customs_hold=True, last_free_day=(date.today() + timedelta(days=1)).isoformat(), location="Y1",
        )
        late = early.model_copy(update={"container_id": "BBBB1234567", "last_free_day": "2099-12-31"})
        await service.upsert("BBBB1234567", "la_pier_400", late)
        await service.upsert("AAAA1234567", "la_pier_400", early)
        rows = await service.list_all()
        assert [row["container_id"] for row in rows] == ["AAAA1234567", "BBBB1234567"]
        assert await service.remove("AAAA1234567") is True
        assert await service.remove("AAAA1234567") is False

    asyncio.run(scenario())


def test_watchlist_api_add_list_delete(tmp_path):
    service = WatchlistService(tmp_path / "api.db")
    app.dependency_overrides[get_settings] = lambda: Settings(api_key="watch-key", test_mode=True)
    app.dependency_overrides[get_watchlist_service] = lambda: service
    client = TestClient(app)
    try:
        headers = {"X-API-Key": "watch-key"}
        added = client.post(
            "/api/v1/watchlist",
            headers=headers,
            json={"container_id": "WFHU5080179", "terminal_id": "la_pier_400"},
        )
        assert added.status_code == 200
        assert added.json()["container_id"] == "WFHU5080179"
        listed = client.get("/api/v1/watchlist", headers=headers)
        assert listed.status_code == 200
        assert listed.json()[0]["container_id"] == "WFHU5080179"
        removed = client.delete("/api/v1/watchlist/WFHU5080179", headers=headers)
        assert removed.status_code == 200
        assert removed.json() == {"deleted": True}
    finally:
        app.dependency_overrides.clear()
