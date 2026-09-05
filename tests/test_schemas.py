import pytest
from pydantic import ValidationError

from app.models.schemas import ContainerStatusResponse, ErrorResponse, LookupRequest


def test_lookup_request_strips_and_uppercases_identifiers():
    request = LookupRequest(terminal_code="  tml-01 ", container_id=" mscu1234567 ")

    assert request.terminal_code == "TML-01"
    assert request.container_id == "MSCU1234567"


def test_lookup_request_accepts_tracking_aliases():
    request = LookupRequest(container_number="wfhu5080179", terminal_id="apm_pier_400")

    assert request.container_id == "WFHU5080179"
    assert request.terminal_code == "APM_PIER_400"


@pytest.mark.parametrize(
    "payload",
    [
        {"terminal_code": " ", "container_id": "MSCU1234567"},
        {"terminal_code": "TML-01", "container_id": ""},
        {"terminal_code": 1, "container_id": "MSCU1234567"},
    ],
)
def test_lookup_request_rejects_blank_or_non_string_identifiers(payload):
    with pytest.raises(ValidationError):
        LookupRequest.model_validate(payload)


def test_container_status_response_matches_spec_fields_and_types():
    response = ContainerStatusResponse(
        container_id="MSCU1234567",
        terminal_name="Example Terminal",
        status="AVAILABLE",
        fees_due=12.5,
        customs_hold=False,
        last_free_day="2026-09-04",
        location="YARD-A1",
    )

    assert set(response.model_dump()) == {
        "container_id",
        "terminal_name",
        "status",
        "fees_due",
        "customs_hold",
        "last_free_day",
        "location",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {
            "container_id": "MSCU1234567",
            "terminal_name": "Example Terminal",
            "status": "AVAILABLE",
            "fees_due": "12.5",
            "customs_hold": False,
            "last_free_day": "2026-09-04",
            "location": "YARD-A1",
        },
        {
            "container_id": "MSCU1234567",
            "terminal_name": "Example Terminal",
            "status": "AVAILABLE",
            "fees_due": 12.5,
            "customs_hold": "false",
            "last_free_day": "2026-09-04",
            "location": "YARD-A1",
        },
        {
            "container_id": "MSCU1234567",
            "terminal_name": "Example Terminal",
            "status": "AVAILABLE",
            "fees_due": 12.5,
            "customs_hold": False,
            "last_free_day": "2026-09-04",
            "location": "YARD-A1",
            "unexpected": "field",
        },
    ],
)
def test_container_status_response_rejects_invalid_payloads(payload):
    with pytest.raises(ValidationError):
        ContainerStatusResponse.model_validate(payload)


def test_error_response_is_typed():
    error = ErrorResponse(status_code=422, error_code="VALIDATION_ERROR", message="Invalid input")

    assert error.model_dump() == {
        "status_code": 422,
        "error_code": "VALIDATION_ERROR",
        "message": "Invalid input",
    }
