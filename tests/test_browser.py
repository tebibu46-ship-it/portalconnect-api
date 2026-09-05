import base64
import asyncio

import pytest

from app.services.browser import (
    BrowserService,
    CaptchaDetectedError,
    PortalTimeoutError,
    PortalUnavailableError,
)


class FakePage:
    def __init__(self):
        self.goto_args = None
        self.selector = None
        self.filled_value = None
        self.wait_for_args = None

    async def goto(self, url, wait_until, timeout):
        self.goto_args = (url, wait_until, timeout)

    def locator(self, selector):
        self.selector = selector
        return self

    @property
    def first(self):
        return self

    async def wait_for(self, state, timeout):
        self.wait_for_args = (state, timeout)

    async def fill(self, value, timeout):
        self.filled_value = value

    async def content(self):
        return "<html><body>portal</body></html>"

    async def screenshot(self, *, full_page, type):
        assert full_page is True
        assert type == "png"
        return b"fake-png"


class FakeContext:
    def __init__(self):
        self.init_script = None
        self.page = FakePage()
        self.route_args = None
        self.closed = False

    async def add_init_script(self, script):
        self.init_script = script

    async def new_page(self):
        return self.page

    async def route(self, pattern, handler):
        self.route_args = (pattern, handler)

    async def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self):
        self.context = FakeContext()
        self.new_context_args = None
        self.closed = False

    async def new_context(self, **kwargs):
        self.new_context_args = kwargs
        return self.context

    async def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self):
        self.browser = FakeBrowser()
        self.launch_args = None

    async def launch(self, **kwargs):
        self.launch_args = kwargs
        return self.browser


class FakePlaywright:
    def __init__(self):
        self.chromium = FakeChromium()


class AsyncPlaywrightFactory:
    def __init__(self):
        self.playwright = FakePlaywright()

    async def __aenter__(self):
        return self.playwright

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def test_capture_portal_state_configures_browser_and_returns_base64():
    factory = AsyncPlaywrightFactory()
    service = BrowserService(lambda: factory)

    result = asyncio.run(
        service.capture_portal_state("https://portal.test", "MSCU1234567")
    )

    chromium = factory.playwright.chromium
    browser = chromium.browser
    context = browser.context
    page = context.page

    assert chromium.launch_args == {
        "headless": True,
        "args": BrowserService.LAUNCH_ARGS,
    }
    assert browser.new_context_args["viewport"] == {"width": 1280, "height": 800}
    assert browser.new_context_args["user_agent"] == BrowserService.DESKTOP_USER_AGENT
    assert "navigator" in context.init_script and "webdriver" in context.init_script
    assert context.route_args[0] == "**/*"
    assert page.goto_args == ("https://portal.test", "domcontentloaded", 15_000)
    assert page.wait_for_args == ("visible", 15_000)
    assert page.selector == BrowserService.GENERIC_FORM_SELECTOR
    assert page.filled_value == "MSCU1234567"
    assert base64.b64decode(result) == b"fake-png"
    assert context.closed is True
    assert browser.closed is True


def test_browser_exposes_typed_portal_exceptions():
    assert issubclass(PortalTimeoutError, Exception)
    assert issubclass(PortalUnavailableError, Exception)
    assert issubclass(CaptchaDetectedError, Exception)


class FakeRequest:
    def __init__(self, resource_type):
        self.resource_type = resource_type


class FakeRoute:
    def __init__(self, resource_type):
        self.request = FakeRequest(resource_type)
        self.aborted = False
        self.continued = False

    async def abort(self):
        self.aborted = True

    async def continue_(self):
        self.continued = True


def test_resource_filter_blocks_heavy_assets_and_allows_page_resources():
    image_route = FakeRoute("image")
    asyncio.run(BrowserService._filter_resources(image_route))
    assert image_route.aborted is True

    script_route = FakeRoute("script")
    asyncio.run(BrowserService._filter_resources(script_route))
    assert script_route.continued is True


def test_capture_closes_context_and_browser_when_capture_fails():
    factory = AsyncPlaywrightFactory()

    async def fail_wait_for(*, state, timeout):
        raise RuntimeError("portal interaction failed")

    factory.playwright.chromium.browser.context.page.wait_for = fail_wait_for
    service = BrowserService(lambda: factory)

    with pytest.raises(RuntimeError, match="portal interaction failed"):
        asyncio.run(service.capture_portal_state("https://portal.test", "MSCU1234567"))

    assert factory.playwright.chromium.browser.context.closed is True
    assert factory.playwright.chromium.browser.closed is True


@pytest.mark.parametrize("operation", ["goto", "wait_for", "fill"])
def test_playwright_timeouts_raise_portal_timeout_and_cleanup(operation):
    factory = AsyncPlaywrightFactory()
    page = factory.playwright.chromium.browser.context.page

    class TimeoutError(Exception):
        pass

    if operation == "goto":
        async def timeout_goto(url, wait_until, timeout):
            raise TimeoutError

        page.goto = timeout_goto
    elif operation == "wait_for":
        async def timeout_wait_for(*, state, timeout):
            raise TimeoutError

        page.wait_for = timeout_wait_for
    else:
        async def timeout_fill(value, timeout):
            raise TimeoutError

        page.fill = timeout_fill

    service = BrowserService(lambda: factory)

    with pytest.raises(PortalTimeoutError, match="timed out"):
        asyncio.run(service.capture_portal_state("https://portal.test", "MSCU1234567"))

    assert factory.playwright.chromium.browser.context.closed is True
    assert factory.playwright.chromium.browser.closed is True
