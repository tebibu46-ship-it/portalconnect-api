import asyncio
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.models.schemas import ContainerStatusResponse
from app.services.parser import VisionExtractor


class FakeCompletions:
    def __init__(self, parsed):
        self.parsed = parsed
        self.kwargs = None
        self.calls = 0

    async def parse(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=self.parsed))]
        )


class FakeClient:
    def __init__(self, parsed):
        self.completions = FakeCompletions(parsed)
        self.beta = SimpleNamespace(chat=SimpleNamespace(completions=self.completions))


def test_vision_extractor_calls_structured_output_and_returns_model():
    expected = ContainerStatusResponse(
        container_id="MSCU1234567",
        terminal_name="Example Terminal",
        status="AVAILABLE",
        fees_due=12.5,
        customs_hold=False,
        last_free_day="2026-09-04",
        location="YARD-A1",
    )
    client = FakeClient(expected)
    extractor = VisionExtractor(
        client=client,
        settings=Settings(openai_api_key="test-key", openai_model="vision-model"),
    )

    result = asyncio.run(extractor.extract("c2NyZWVuc2hvdA==", "TML-01"))

    request = client.completions.kwargs
    assert result is expected
    assert request["model"] == "vision-model"
    assert request["response_format"] is ContainerStatusResponse
    content = request["messages"][0]["content"]
    assert "TML-01" in content[0]["text"]
    assert content[1]["image_url"]["url"] == "data:image/png;base64,c2NyZWVuc2hvdA=="


def test_vision_extractor_uses_deterministic_mock_without_api_key():
    client = FakeClient(None)
    extractor = VisionExtractor(
        client=client,
        settings=Settings(openai_api_key="", test_mode=False),
    )

    result = asyncio.run(
        extractor.extract(
            "<table><tr><th>Container ID</th><td>MSCU1234567</td></tr>"
            "<tr><th>Status</th><td>AVAILABLE</td></tr></table>",
            "TML-01",
        )
    )

    assert result.container_id == "MSCU1234567"
    assert result.status == "AVAILABLE"
    assert result.fees_due == 0.0
    assert client.completions.calls == 0


def test_vision_extractor_uses_deterministic_mock_in_test_mode():
    client = FakeClient(None)
    extractor = VisionExtractor(
        client=client,
        settings=Settings(openai_api_key="test-key", test_mode=True),
    )

    result = asyncio.run(extractor.extract("ignored", "TML-01"))

    assert result.model_dump() == VisionExtractor.MOCK_RESPONSE
    assert client.completions.calls == 0


def test_vision_extractor_propagates_bad_structured_data():
    client = FakeClient(None)
    extractor = VisionExtractor(
        client=client,
        settings=Settings(openai_api_key="test-key", test_mode=False),
    )

    with pytest.raises(ValueError, match="no parsed container status"):
        asyncio.run(extractor.extract("not-a-real-screenshot", "TML-01"))

    assert client.completions.calls == 1


def test_extract_dom_maps_table_rows_to_container_status_response():
    extractor = VisionExtractor(settings=Settings(openai_api_key=""))
    html = """
    <table>
      <tr><th>Container Number</th><td>mscu1234567</td></tr>
      <tr><th>Status</th><td>AVAILABLE</td></tr>
      <tr><th>Customs Hold</th><td>YES</td></tr>
      <tr><th>Fees Due</th><td>$1,234.50</td></tr>
      <tr><th>Last Free Day</th><td>2026-09-10</td></tr>
      <tr><th>Location</th><td>YARD-A1</td></tr>
    </table>
    """

    result = extractor.extract_dom(html, "ny_red_hook")

    assert result.model_dump() == {
        "container_id": "MSCU1234567",
        "terminal_name": "Ny Red Hook",
        "status": "AVAILABLE",
        "fees_due": 1234.50,
        "customs_hold": True,
        "last_free_day": "2026-09-10",
        "location": "YARD-A1",
    }
