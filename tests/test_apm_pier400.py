import asyncio

import pytest

from app.services.scrapers.apm_pier400 import APMPier400Adapter


APM_HTML = """
<html><body><table class="track-result">
  <tr><th>Container ID</th><td>MSKU9018231</td></tr>
  <tr><th>Availability Status</th><td>AVAILABLE</td></tr>
  <tr><th>Yard Stack / Area</th><td>BLOCK B12 / ROW 04</td></tr>
  <tr><th>Customs Hold</th><td>No</td></tr>
  <tr><th>Last Free Day</th><td>2026-09-14</td></tr>
  <tr><th>Demurrage Fees Due</th><td>$125.50</td></tr>
</table></body></html>
"""


def test_apm_parser_maps_live_result_table_to_public_schema():
    result = APMPier400Adapter.parse_html(APM_HTML, "MSKU9018231")

    assert result.model_dump() == {
        "container_id": "MSKU9018231",
        "terminal_name": "APM Terminals - Pier 400 (Los Angeles)",
        "status": "AVAILABLE",
        "fees_due": 125.5,
        "customs_hold": False,
        "last_free_day": "2026-09-14",
        "location": "BLOCK B12 / ROW 04",
    }


class FakePage:
    def __init__(self):
        self.goto_args = None
        self.filled = None
        self.pressed = None

    async def goto(self, url, wait_until, timeout):
        self.goto_args = (url, wait_until, timeout)

    def locator(self, selector):
        return self

    @property
    def first(self):
        return self

    async def wait_for(self, state, timeout):
        return None

    async def fill(self, value, timeout):
        self.filled = value

    async def press(self, key):
        self.pressed = key

    async def content(self):
        return APM_HTML


class FakeContext:
    def __init__(self):
        self.page = FakePage()
        self.closed = False

    async def route(self, pattern, handler):
        self.route_args = (pattern, handler)

    async def new_page(self):
        return self.page

    async def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self):
        self.context = FakeContext()
        self.closed = False

    async def new_context(self, **kwargs):
        self.context_args = kwargs
        return self.context

    async def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self):
        self.browser = FakeBrowser()

    async def launch(self, **kwargs):
        self.launch_args = kwargs
        return self.browser


class FakePlaywright:
    def __init__(self):
        self.chromium = FakeChromium()


class Factory:
    def __init__(self):
        self.playwright = FakePlaywright()

    async def __aenter__(self):
        return self.playwright

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def test_apm_lookup_uses_mocked_dom_and_always_cleans_up():
    factory = Factory()
    result = asyncio.run(APMPier400Adapter(lambda: factory).lookup("MSKU9018231"))

    page = factory.playwright.chromium.browser.context.page
    assert result.container_id == "MSKU9018231"
    assert page.filled == "MSKU9018231"
    assert page.pressed == "Enter"
    assert page.goto_args[0] == APMPier400Adapter.PORTAL_URL
    assert factory.playwright.chromium.browser.context.closed is True
    assert factory.playwright.chromium.browser.closed is True


def test_apm_parser_rejects_missing_status():
    with pytest.raises(ValueError, match="availability status"):
        APMPier400Adapter.parse_html("<table><tr><th>Container ID</th><td>MSKU9018231</td></tr></table>", "MSKU9018231")


def test_apm_payload_parser_maps_internal_json_shape():
    result = APMPier400Adapter._parse_payload(
        {
            "data": {
                "container": {
                    "containerNumber": "MSKU9018231",
                    "availabilityStatus": "AVAILABLE",
                    "yardArea": "B12",
                    "customsHold": False,
                    "lastFreeDay": "2026-09-14",
                    "demurrageFeesDue": 12.5,
                }
            }
        },
        "MSKU9018231",
    )

    assert result.status == "AVAILABLE"
    assert result.location == "B12"
    assert result.fees_due == 12.5
