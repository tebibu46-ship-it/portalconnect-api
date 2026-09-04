# PortalConnect API — Permanent Product Specification

## 1. Product Definition

PortalConnect API is the headless API layer for legacy web portals. It accepts a terminal and container identifier, obtains container status data through a supported portal integration, normalizes the result into a stable schema, and returns a predictable JSON response to clients.

The API is designed as a bounded anti-corruption layer: portal-specific navigation, browser behavior, extraction, and parsing remain internal implementation details; consumers depend only on the versioned API contract.

## 2. Goals and Non-Goals

### Goals

- Provide one stable, machine-readable lookup endpoint for legacy terminal portals.
- Isolate portal automation behind an adapter boundary.
- Normalize portal responses into strongly typed Pydantic models.
- Support live browser retrieval and deterministic mock fallback.
- Return controlled errors with no unhandled server crashes.

### Non-Goals

- Exposing browser sessions or portal credentials to API consumers.
- Persisting container data as a system of record.
- Supporting arbitrary portal websites without an explicit adapter.

## 3. Technology Baseline

- Python 3.11
- FastAPI for the HTTP gateway
- Playwright in asynchronous mode for browser automation
- Pydantic v2 for validation and serialization
- pytest for unit, integration, and contract tests

## 4. Core Architecture

The service is organized into the following logical layers:

1. **API Gateway** — FastAPI routes, request validation, response serialization, correlation IDs, authentication boundary, and exception handling.
2. **Application Service** — Coordinates lookup use cases, selects live or mock execution, applies timeouts, and maps domain failures to stable API errors.
3. **Portal Adapter** — Encapsulates terminal-specific portal URLs, navigation steps, selectors, session handling, and extraction operations.
4. **Browser Engine** — Owns the async Playwright lifecycle, context configuration, stealth-compatible browser settings, retries, and cleanup.
5. **Vision and Parsing Pipeline** — Converts screenshots or extracted portal text into structured, validated domain data.
6. **Domain Models** — Pydantic v2 request, response, error, and internal result models.

The dependency direction is inward: the gateway depends on the application service, the application service depends on adapter interfaces, and adapters depend on browser and parsing implementations. Portal-specific code must not leak into route handlers.

## 5. Input Contract

### Endpoint

`POST /v1/container/lookup`

### Request body

```json
{
  "terminal_code": "string",
  "container_id": "string"
}
```

Both fields are required strings. Validation must reject missing, blank, malformed, or overlong values with a controlled 4xx response. The service must normalize only where the target portal contract permits it; it must not silently change a container identifier.

### Supporting endpoints

- `GET /v1/terminals` returns the supported terminal registry.
- `GET /healthz` returns `{ "status": "ok" }` when the service is live.

## 6. Output Contract

Successful responses must conform to this exact JSON shape:

```json
{
  "container_id": "string",
  "terminal_name": "string",
  "status": "string",
  "fees_due": 0.0,
  "customs_hold": false,
  "last_free_day": "string",
  "location": "string"
}
```

Field meanings:

- `container_id`: The requested container identifier.
- `terminal_name`: Human-readable terminal name resolved from `terminal_code`.
- `status`: Normalized operational status from the portal.
- `fees_due`: Monetary amount due, represented as a JSON number and never negative.
- `customs_hold`: Whether a customs hold is active.
- `last_free_day`: Portal-provided date string in the adapter's documented canonical format.
- `location`: Current terminal location or movement location.

## 7. Runtime Modes

- **Live mode:** Uses the configured terminal adapter and async Playwright to retrieve current portal data.
- **Mock mode:** Automatically activates when no API key is supplied. It must be deterministic, clearly observable in logs/metrics, and return schema-valid fixture data suitable for local development and tests. Mock mode must never be mistaken for live data by internal telemetry.

Configuration is supplied through environment variables or an equivalent settings object. Secrets must not be hard-coded, logged, returned, or included in screenshots/artifacts.

## 8. Reliability and Error Handling

- Every external navigation, selector wait, extraction operation, and parsing call must have an explicit timeout.
- Retry only safe, idempotent browser operations, with bounded attempts and backoff.
- Always close Playwright pages, contexts, and browsers in success and failure paths.
- Translate validation, timeout, portal-unavailable, parsing, authentication, and unexpected failures into documented controlled responses.
- Install a top-level exception handler so no request produces an unhandled 500 crash. Unexpected failures may use a generic controlled 5xx envelope, but must not expose stack traces or secrets.
- Preserve a correlation ID across logs and error responses where applicable.

## 9. Stealth and Security Constraints

- Browser automation must run headlessly in production.
- Use stealth-compatible evasion for automation fingerprints and realistic browser context configuration, within applicable portal terms and policies.
- Do not bypass authentication, CAPTCHAs, access controls, or rate limits.
- Apply request-size limits, input validation, rate limiting, security headers, and authentication/authorization middleware as deployment requirements dictate.
- Redact credentials, tokens, personally identifiable information, and raw portal payloads from logs.

## 10. Testing and Acceptance Criteria

- Pydantic contract tests cover valid and invalid request/response data.
- Mock-mode tests run without network access or API credentials.
- Browser engine tests verify timeout, retry, cleanup, and adapter isolation behavior.
- Gateway integration tests verify the endpoint, controlled errors, middleware, and absence of unhandled exceptions.
- The full pytest suite must pass before release.

Any implementation that changes the endpoint, request fields, response fields, runtime mode semantics, or reliability/security constraints must update this specification through an explicit architecture review.
