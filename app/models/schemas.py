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
