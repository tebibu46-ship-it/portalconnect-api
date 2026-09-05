"""Low-memory live adapter for APM Terminals Pier 400 in Los Angeles."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Callable

from bs4 import BeautifulSoup

from app.models.schemas import ContainerStatusResponse
from app.services.browser import (
    BrowserService,
    CaptchaDetectedError,
    PortalTimeoutError,
    PortalUnavailableError,
)

_LIVE_SESSION_LOCK = asyncio.Semaphore(1)


class APMPier400Adapter:
    """Query and parse the APM Pier 400 tracking page in one short-lived session."""

    PORTAL_URL = (
        "https://www.apmterminals.com/en/los-angeles/practical-information/"
        "track-and-trace"
    )
    TERMINAL_NAME = "APM Terminals - Pier 400 (Los Angeles)"
    HARD_TIMEOUT_SECONDS = 20
    INPUT_SELECTOR = (
        "input[name*='container' i], input[id*='container' i], "
        "input[placeholder*='container' i], input[type='text']"
    )
    RESULT_SELECTOR = (
        "table, [class*='result' i], [class*='track' i], "
        "[data-testid*='result' i]"
    )
    BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}
    TRACKER_MARKERS = ("google-analytics.com", "googletagmanager.com", "adobe.io", "omtrdc.net")

    def __init__(self, playwright_factory: Callable[[], Any] | None = None) -> None:
        self._playwright_factory = playwright_factory or BrowserService._load_playwright

    @classmethod
    async def _route_resource(cls, route: Any) -> None:
        request = route.request
        if request.resource_type in cls.BLOCKED_RESOURCE_TYPES or any(
            marker in request.url.lower() for marker in cls.TRACKER_MARKERS
        ):
            await route.abort()
            return
        await route.continue_()

    @staticmethod
    def _text(value: str | None) -> str:
        return re.sub(r"\s+", " ", value or "").strip()

    @classmethod
    def _fields(cls, soup: BeautifulSoup) -> dict[str, str]:
        fields: dict[str, str] = {}
        for row in soup.select("tr, li, .field, [class*='detail' i]"):
            cells = [cls._text(cell.get_text(" ", strip=True)) for cell in row.select("th, td")]
            if len(cells) >= 2:
                key = re.sub(r"[^a-z0-9]+", "_", cells[0].lower()).strip("_")
                fields[key] = cells[1]
        return fields

    @staticmethod
    def _find(fields: dict[str, str], *keys: str) -> str | None:
        for key in keys:
            if key in fields:
                return fields[key]
        return None

    @classmethod
    def parse_html(cls, html: str, requested_container_id: str) -> ContainerStatusResponse:
        """Parse a bounded APM result fragment into the public response schema."""

        soup = BeautifulSoup(html, "html.parser")
        visible_text = cls._text(soup.get_text(" ", strip=True))
        if any(marker in visible_text.lower() for marker in ("captcha", "cloudflare", "verify you are human")):
            raise CaptchaDetectedError("APM portal presented a bot or CAPTCHA challenge")

        fields = cls._fields(soup)
        requested = requested_container_id.strip().upper()
        container_match = re.search(r"[A-Z]{4}\d{7}", visible_text.upper())
        container_id = cls._find(fields, "container_id", "container_number", "container") or (
            container_match.group(0) if container_match else requested
        )
        status = cls._find(fields, "status", "availability_status", "container_status")
        if not status:
            status_match = re.search(r"\b(AVAILABLE|RELEASED|READY|HOLD|UNAVAILABLE|NOT AVAILABLE)\b", visible_text, re.I)
            status = status_match.group(1) if status_match else None
        if not container_id or not status:
            raise ValueError("APM result is missing container ID or availability status")

        fees_text = cls._find(fields, "demurrage_fees_due", "fees_due", "demurrage", "fees") or "0"
        amount = re.search(r"-?\d+(?:,\d{3})*(?:\.\d+)?", fees_text)
        customs_text = (cls._find(fields, "customs_hold", "customs", "customs_status") or "no").lower()
        customs_hold = customs_text in {"true", "yes", "y", "1", "hold", "held"}
        return ContainerStatusResponse(
            container_id=container_id.strip().upper(),
            terminal_name=cls.TERMINAL_NAME,
            status=cls._text(status),
            fees_due=float(amount.group(0).replace(",", "")) if amount else 0.0,
            customs_hold=customs_hold,
            last_free_day=cls._find(fields, "last_free_day", "free_day", "last_free_date") or "UNKNOWN",
            location=cls._find(
                fields,
                "yard_stack",
                "yard_stack_area",
                "yard_area",
                "yard_location",
                "location",
            ) or "UNKNOWN",
        )

    async def lookup(self, container_id: str) -> ContainerStatusResponse:
        """Run one serialized, hard-bounded live lookup against APM."""

        async with _LIVE_SESSION_LOCK:
            try:
                return await asyncio.wait_for(
                    self._lookup_unlocked(container_id),
                    timeout=self.HARD_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError as exc:
                raise PortalTimeoutError("APM Pier 400 lookup exceeded 20 seconds") from exc

    async def _lookup_unlocked(self, container_id: str) -> ContainerStatusResponse:
        browser = None
        context = None
        try:
            async with self._playwright_factory() as playwright:
                try:
                    browser = await playwright.chromium.launch(
                        headless=True,
                        args=BrowserService.LOW_MEMORY_ARGS,
                    )
                    context = await browser.new_context(
                        user_agent=BrowserService.DESKTOP_USER_AGENT,
                        viewport=BrowserService.VIEWPORT,
                    )
                    await context.route("**/*", self._route_resource)
                    page = await context.new_page()
                    await page.goto(self.PORTAL_URL, wait_until="domcontentloaded", timeout=19_000)
                    tracking_input = page.locator(self.INPUT_SELECTOR).first
                    await tracking_input.wait_for(state="visible", timeout=5_000)
                    await tracking_input.fill(container_id, timeout=5_000)
                    await tracking_input.press("Enter")
                    result = page.locator(self.RESULT_SELECTOR).first
                    await result.wait_for(state="visible", timeout=8_000)
                    html = await page.content()
                    return self.parse_html(html, container_id)
                except CaptchaDetectedError:
                    raise
                except Exception as exc:
                    if exc.__class__.__name__ == "TimeoutError":
                        raise PortalTimeoutError("APM portal navigation or result timed out") from exc
                    if isinstance(exc, (PortalTimeoutError, PortalUnavailableError, ValueError)):
                        raise
                    raise PortalUnavailableError(f"APM Pier 400 portal unavailable: {exc}") from exc
        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass
            if browser is not None:
                try:
                    await browser.close()
                except Exception:
                    pass
