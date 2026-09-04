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

    result = asyncio.run(extractor.extract("ignored", "TML-01"))

    assert result.model_dump() == VisionExtractor.MOCK_RESPONSE
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
