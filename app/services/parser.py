"""Vision-based structured extraction for portal screenshots."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup
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

    @staticmethod
    def _table_values(html: str) -> dict[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        values: dict[str, str] = {}
        for row in soup.select("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.select("th, td")]
            if len(cells) >= 2:
                label = re.sub(r"[^a-z0-9]+", "_", cells[0].lower()).strip("_")
                values[label] = cells[1]
        return values

    @staticmethod
    def _first_value(values: dict[str, str], *names: str) -> str | None:
        for name in names:
            if name in values:
                return values[name]
        return None

    def extract_dom(self, html: str, terminal_code: str) -> ContainerStatusResponse:
        """Extract container status fields directly from portal table HTML."""

        values = self._table_values(html)
        container_id = self._first_value(
            values,
            "container_id",
            "container_number",
            "container",
            "tracking_id",
        )
        status = self._first_value(values, "status", "container_status")
        if not container_id or not status:
            raise ValueError("Portal HTML is missing container ID or status")

        fees_text = self._first_value(values, "fees_due", "fees", "amount_due") or "0"
        fee_match = re.search(r"-?\d+(?:,\d{3})*(?:\.\d+)?", fees_text)
        fees_due = float(fee_match.group(0).replace(",", "")) if fee_match else 0.0

        customs_text = (
            self._first_value(values, "customs_hold", "customs", "customs_status") or "no"
        ).lower()
        customs_hold = customs_text in {"true", "yes", "y", "1", "hold", "held"}
        terminal_name = terminal_code.replace("_", " ").title()

        return ContainerStatusResponse(
            container_id=container_id.strip().upper(),
            terminal_name=terminal_name,
            status=status.strip(),
            fees_due=fees_due,
            customs_hold=customs_hold,
            last_free_day=self._first_value(values, "last_free_day", "free_day") or "UNKNOWN",
            location=self._first_value(values, "location", "yard_location") or "UNKNOWN",
        )

    async def extract(
        self,
        screenshot_base64: str,
        terminal_code: str,
    ) -> ContainerStatusResponse:
        """Extract and validate structured container status from a screenshot."""

        if self.settings.test_mode:
            return ContainerStatusResponse.model_validate(self.MOCK_RESPONSE)
        if not self.settings.openai_api_key:
            return self.extract_dom(screenshot_base64, terminal_code)

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
