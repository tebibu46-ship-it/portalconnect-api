"""Browser smoke test for the root tracking dashboard."""

from __future__ import annotations

import re
import socket
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn

playwright = pytest.importorskip("playwright.async_api")
from playwright.sync_api import expect  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.main import app  # noqa: E402
from app.api.routes import get_apm_adapter, get_settings  # noqa: E402
from app.services.scrapers import APMPier400Adapter  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _FixtureAdapter:
    async def lookup(self, container_id: str):
        return APMPier400Adapter._fixture_response(container_id)


@pytest.fixture
def local_server() -> Iterator[str]:
    """Run the real FastAPI app on an ephemeral local HTTP port."""

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    app.dependency_overrides[get_settings] = lambda: Settings(
        api_key="test_secret_key", test_mode=False
    )
    app.dependency_overrides[get_apm_adapter] = lambda: _FixtureAdapter()
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("Local Uvicorn server did not start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        app.dependency_overrides.clear()


def test_tracking_dashboard_completes_lookup(local_server: str, capsys: pytest.CaptureFixture[str]) -> None:
    console_errors: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.on(
            "console",
            lambda msg: (
                print(f"[BROWSER CONSOLE] {msg.type}: {msg.text}"),
                console_errors.append(msg.text) if msg.type == "error" else None,
            ),
        )
        page.on(
            "pageerror",
            lambda error: (
                print(f"[BROWSER UNCAUGHT EXCEPTION] {error}"),
                page_errors.append(str(error)),
            ),
        )

        page.goto(f"{local_server}/", wait_until="domcontentloaded")
        standby = page.locator("#standby-view")
        telemetry = page.locator("#telemetry-view")
        expect(standby).to_be_visible()
        assert "hidden" in (telemetry.get_attribute("class") or "")

        chip = page.locator(".sample-chip", has_text="WFHU5080179").first
        chip.click()
        expect(telemetry).not_to_have_class(re.compile(r".*\bhidden\b.*"), timeout=5_000)
        expect(standby).to_have_class(re.compile(r".*\bhidden\b.*"))

        telemetry_text = telemetry.inner_text()
        assert "WFHU5080179" in telemetry_text
        assert "AVAILABLE" in telemetry_text
        assert not console_errors, f"Browser console errors: {console_errors}"
        assert not page_errors, f"Browser uncaught exceptions: {page_errors}"
        browser.close()

    output = capsys.readouterr().out
    assert "[BROWSER CONSOLE]" in output or output == ""
