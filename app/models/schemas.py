"""Pydantic v2 request, response, and error contracts."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LookupRequest(BaseModel):
    """Validated input for a container lookup."""

    model_config = ConfigDict(extra="forbid", strict=True)

    terminal_code: str = Field(min_length=1)
    container_id: str = Field(
        min_length=11,
        max_length=11,
        pattern=r"^[A-Z]{4}[0-9]{7}$",
    )

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
