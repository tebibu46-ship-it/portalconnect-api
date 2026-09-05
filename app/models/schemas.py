"""Pydantic v2 request, response, and error contracts."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LookupRequest(BaseModel):
    """Validated input for a container lookup."""

    model_config = ConfigDict(extra="forbid", strict=True)

    terminal_code: str = Field(min_length=1)
    container_id: str = Field(
        min_length=11,
        max_length=11,
        pattern=r"^[A-Z]{4}[0-9]{7}$",
    )

    @model_validator(mode="before")
    @classmethod
    def accept_tracking_aliases(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        if "container_id" not in payload and "container_number" in payload:
            payload["container_id"] = payload["container_number"]
        if "terminal_code" not in payload:
            payload["terminal_code"] = payload.get("terminal", payload.get("terminal_id"))
        payload.pop("container_number", None)
        payload.pop("terminal", None)
        payload.pop("terminal_id", None)
        return payload

    @field_validator("terminal_code", "container_id", mode="before")
    @classmethod
    def normalize_identifier(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("must be a string")

        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class WatchlistCreateRequest(BaseModel):
    """Input contract for adding a monitored container."""

    model_config = ConfigDict(extra="forbid", strict=True)

    container_id: str = Field(min_length=11, max_length=11, pattern=r"^[A-Z]{4}[0-9]{7}$")
    terminal_id: str = Field(min_length=1)

    @field_validator("container_id", "terminal_id", mode="before")
    @classmethod
    def normalize_identifier(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class BatchTrackRequest(BaseModel):
    """JSON input for bounded multi-container ingestion."""

    model_config = ConfigDict(extra="forbid", strict=True)

    containers: list[str] = Field(min_length=1, max_length=100)
    terminal: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def accept_terminal_alias(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        if "terminal" not in payload and "terminal_id" in payload:
            payload["terminal"] = payload["terminal_id"]
        payload.pop("terminal_id", None)
        return payload

    @field_validator("terminal", mode="before")
    @classmethod
    def normalize_terminal(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("terminal must be a non-empty string")
        return value.strip().lower()

    @field_validator("containers", mode="before")
    @classmethod
    def normalize_containers(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("containers must be a list")
        normalized = [item.strip().upper() if isinstance(item, str) else item for item in value]
        if any(not isinstance(item, str) for item in normalized):
            raise ValueError("container IDs must be strings")
        return normalized


class ContainerStatusResponse(BaseModel):
    """Stable response contract for container status lookups."""

    model_config = ConfigDict(extra="forbid", strict=True)

    container_id: str
    terminal_name: str
    status: str
    fees_due: float
    customs_hold: bool
    last_free_day: str
    location: str
    notes: str | None = Field(default=None, exclude=True)


class ErrorResponse(BaseModel):
    """Controlled API error response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    status_code: int
    error_code: str
    message: str


class WebhookTestRequest(BaseModel):
    """Optional target and watchlist item used by webhook test-fire calls."""

    model_config = ConfigDict(extra="forbid", strict=True)

    target_url: str | None = None
    item: dict[str, Any] | None = None
    container_id: str | None = None
    terminal_id: str | None = None
    fees_due: float = 0.0
    last_free_day: str | None = None
    status: str = "HOLD"

    @model_validator(mode="before")
    @classmethod
    def accept_webhook_aliases(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        if "target_url" not in payload:
            payload["target_url"] = payload.get("url", payload.get("webhook_url"))
        if "container_id" not in payload and "container_number" in payload:
            payload["container_id"] = payload["container_number"]
        payload.pop("url", None)
        payload.pop("webhook_url", None)
        payload.pop("container_number", None)
        return payload


class DriverSmsRequest(BaseModel):
    """Public driver dispatch contract with friendly field aliases."""

    model_config = ConfigDict(extra="forbid", strict=True)

    container_id: str = Field(min_length=1)
    phone_number: str = "+12135550199"
    driver_name: str = "Fleet Driver"
    terminal_id: str = "la_pier_400"
    target_url: str | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_driver_aliases(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        if "phone_number" not in payload and "phone" in payload:
            payload["phone_number"] = payload["phone"]
        payload.pop("phone", None)
        return payload

    @field_validator("container_id", "phone_number", "driver_name", "terminal_id", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-empty string")
        return value.strip()


class BatchContainerResult(BaseModel):
    """One resilient result in a batch manifest."""

    model_config = ConfigDict(extra="forbid", strict=True)

    container_id: str
    status: str
    customs_hold: bool
    fees_due: float
    last_free_day: str
    urgency_level: str
    terminal_name: str
    location: str
    error: str | None = None
