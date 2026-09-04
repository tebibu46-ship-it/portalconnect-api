"""Async browser service for capturing legacy portal state."""

from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Any


class PortalTimeoutError(Exception):
    """Raised when portal navigation or element interaction exceeds its timeout."""


class PortalUnavailableError(Exception):
    """Raised when a portal cannot be reached or used."""


class CaptchaDetectedError(Exception):
    """Raised when a portal presents a CAPTCHA challenge."""


class BrowserService:
    """Owns a short-lived headless Chromium session for portal capture."""

    DESKTOP_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
    VIEWPORT = {"width": 1920, "height": 1080}
    GENERIC_FORM_SELECTOR = (
        "input[name='container_id'], input[name='container'], "
        "input[id*='container' i], input[id*='tracking' i], "
        "input[placeholder*='container' i], input[placeholder*='tracking' i], "
        "input[type='text']"
    )
    WEBDRIVER_MASK = """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """
    TIMEOUT_MS = 15_000

    def __init__(self, playwright_factory: Callable[[], Any] | None = None) -> None:
        self._playwright_factory = playwright_factory or self._load_playwright

    @staticmethod
    def _load_playwright() -> Any:
        from playwright.async_api import async_playwright

        return async_playwright()

    async def capture_portal_state(self, url: str, container_id: str) -> str:
        """Fill a portal tracking form and return a full-page PNG as base64."""

        async with self._playwright_factory() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = None
            try:
                context = await browser.new_context(
                    user_agent=self.DESKTOP_USER_AGENT,
                    viewport=self.VIEWPORT,
                )
                await context.add_init_script(self.WEBDRIVER_MASK)
                page = await context.new_page()
                try:
                    await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self.TIMEOUT_MS,
                    )
                    tracking_input = page.locator(self.GENERIC_FORM_SELECTOR).first
                    await tracking_input.wait_for(
                        state="visible",
                        timeout=self.TIMEOUT_MS,
                    )
                    await tracking_input.fill(container_id, timeout=self.TIMEOUT_MS)
                except Exception as exc:
                    if exc.__class__.__name__ == "TimeoutError":
                        raise PortalTimeoutError(
                            "Portal navigation or element interaction timed out"
                        ) from exc
                    raise
                screenshot = await page.screenshot(full_page=True, type="png")
                return base64.b64encode(screenshot).decode("ascii")
            finally:
                if context is not None:
                    try:
                        await context.close()
                    except Exception:
                        pass
                try:
                    await browser.close()
                except Exception:
                    pass
