"""Vision-based structured extraction for portal screenshots."""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from app.core.config import Settings, get_settings
from app.models.schemas import ContainerStatusResponse


class VisionExtractor:
    """Send a portal screenshot to OpenAI and parse the typed result."""

    MOCK_RESPONSE = {
        "container_id": "MOCK-CONTAINER",
        "terminal_name": "Mock Terminal",
        "status": "AVAILABLE",
        "fees_due": 0.0,
        "customs_hold": False,
        "last_free_day": "2099-12-31",
        "location": "MOCK-YARD",
    }

    def __init__(
        self,
        client: Any | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client

    @staticmethod
    def _build_prompt(terminal_code: str) -> str:
        return (
            "Extract the container status fields visible in this legacy terminal "
            f"portal screenshot for terminal code {terminal_code!r}. "
            "Return only the requested structured container status data."
        )

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        return self._client

    async def extract(
        self,
        screenshot_base64: str,
        terminal_code: str,
    ) -> ContainerStatusResponse:
        """Extract and validate structured container status from a screenshot."""

        if self.settings.test_mode or not self.settings.openai_api_key:
            return ContainerStatusResponse.model_validate(self.MOCK_RESPONSE)

        response = await self._get_client().beta.chat.completions.parse(
            model=self.settings.openai_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._build_prompt(terminal_code)},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{screenshot_base64}"
                            },
                        },
                    ],
                }
            ],
            response_format=ContainerStatusResponse,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError("OpenAI returned no parsed container status")
        return parsed
