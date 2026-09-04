# PortalConnect API — Project Progress

## Current State

- **Active Phase:** Phase 3 — Vision & Structured Parsing Pipeline with Mock Fallbacks
- **Current Task:** None
- **Overall Status:** MVP complete

## Completed Tasks

- **1.1 — Complete:** Created the Python 3.11 `src/portalconnect` package layout, pytest configuration in `pyproject.toml`, and a project-layout smoke test.
- **1.2 — Complete:** Implemented strict Pydantic v2 `LookupRequest`, `ContainerStatusResponse`, and `ErrorResponse` schemas with identifier normalization and extra-field rejection.
- **1.3 — Complete:** Added valid and invalid payload tests for `LookupRequest` and `ContainerStatusResponse`.
- **2.1 — Complete:** Implemented the async `BrowserService` with headless Chromium configuration, desktop user-agent/viewport, webdriver masking, portal form capture, base64 full-page screenshots, and cleanup.
- **2.2 — Complete:** Added `PortalTimeoutError`, `PortalUnavailableError`, and `CaptchaDetectedError`, explicit 15-second navigation/element waits, and safe `finally` cleanup for browser contexts and instances.
- **2.3 — Complete:** Added mocked timeout-path tests and translated Playwright-style timeout failures to `PortalTimeoutError` while verifying browser/context cleanup.
- **3.1 — Complete:** Implemented `VisionExtractor` with environment-backed OpenAI configuration, screenshot prompt construction, structured outputs, and parsed `ContainerStatusResponse` results.
- **3.2 — Complete:** Added deterministic mock fallback for missing `OPENAI_API_KEY` or `TEST_MODE=true`, returning schema-validated data without network calls.
- **3.3 — Complete:** Added parser tests covering mock execution and propagation of malformed structured output errors.
- **4.1 — Complete:** Added the FastAPI container lookup route with API-key authentication, terminal registry resolution, and browser-to-vision service coordination.
- **4.2 — Complete:** Added the FastAPI application entrypoint with router mounting, CORS middleware, and structured global handlers for portal timeout, CAPTCHA, and unhandled exceptions.
- **4.3 — Complete:** Added end-to-end `TestClient` coverage for mock-mode success, API-key failures, and malformed container IDs; verified the full test suite passes.

## Open Blockers

None recorded.

## Blockers / Notes

- **Resolved:** The last full-suite failure came from `tests/test_schemas.py` using `"ms cu1234567"` as a normalization fixture. Task 4.3 correctly enforces the strict `^[A-Z]{4}[0-9]{7}$` container-ID format, so the fixture was changed to `" mscu1234567 "` to test outer-whitespace stripping without an invalid internal space.
- **Verification:** `python -m pytest tests/` passes with **29 passed** and one non-blocking Starlette deprecation warning.

## Task Log

### 1.1

- **Implemented:** Created the package layers (`api`, `application`, `adapters`, `browser`, `domain`, and `parsing`), package metadata, pytest configuration, and layout smoke test.
- **Test outcome:** Passing — direct smoke-test invocation reported `1 passed`; Python compilation passed. The pytest executable is not installed locally, and installing dependencies remains task 1.2.
- **Immediate next task:** 1.3 — Continue with the next unchecked plan item.

### 1.3

- **Implemented:** Expanded `tests/test_schemas.py` with clean valid parsing assertions and invalid response payload coverage for strict typing and forbidden extra fields.
- **Test outcome:** Passing — `python -m pytest tests/test_schemas.py` (`9 passed`). The `pytest` executable name is not on the shell PATH, so the equivalent Python module invocation was used.
- **Immediate next task:** 2.1 — Implement the async Playwright browser/context factory.

### 2.1

- **Implemented:** Added `app/services/browser.py` and a mocked async browser test covering navigation, generic tracking input, stealth-compatible launch configuration, screenshot encoding, and resource cleanup.
- **Test outcome:** Passing — `python -m pytest tests/test_browser.py -q` (`1 passed`).
- **Immediate next task:** 2.2 — Add stealth-compatible context configuration and the portal adapter interface.

### 2.2

- **Implemented:** Enhanced `app/services/browser.py` with typed portal exceptions, 15-second `goto`, element visibility, and form-fill timeouts, plus cleanup guards that close resources after success or failure.
- **Test outcome:** Passing — `python -m pytest tests/test_browser.py -q` (`3 passed`).
- **Immediate next task:** 2.3 — Implement bounded navigation retries, timeout translation, and guaranteed page/context/browser cleanup.

### 2.3

- **Implemented:** Added unit coverage for navigation, element-wait, and form-fill timeouts; timeout failures now raise `PortalTimeoutError`, with cleanup verified for every path.
- **Test outcome:** Passing — `python -m pytest tests/test_browser.py` (`6 passed`).
- **Immediate next task:** 3.1 — Define the structured extraction input/output boundary.

### 3.1

- **Implemented:** Added `app/core/config.py` for `.env`-based settings and `app/services/parser.py` for async OpenAI vision extraction using a base64 PNG and terminal code.
- **Test outcome:** Passing — `python -m pytest tests/test_parser.py -q` (`1 passed`).
- **Immediate next task:** 3.2 — Implement deterministic mock mode when no API key is supplied.

### 3.2

- **Implemented:** Added `test_mode` settings, documented `TEST_MODE` in `.env.example`, and added an early deterministic `ContainerStatusResponse` fallback in `VisionExtractor`.
- **Test outcome:** Passing — `python -m pytest tests/test_parser.py -q` (`3 passed`), including assertions that the OpenAI client is not called.
- **Immediate next task:** 3.3 — Add parsing validation, malformed-data handling, and live/mock adapter selection.

### 3.3

- **Implemented:** Expanded `tests/test_parser.py` with mock-mode assertions and bad structured-data propagation coverage.
- **Test outcome:** Passing — `python -m pytest tests/test_parser.py` (`4 passed`). The literal `pytest` command is not on the shell PATH.
- **Immediate next task:** 4.1 — Implement `POST /v1/container/lookup` with dependency-injected application services.

### 4.1

- **Implemented:** Added `app/api/routes.py` with `POST /v1/container/lookup`, `X-API-Key` authentication, registry mappings for `la_pier_400` and `ny_red_hook`, and injected `BrowserService`/`VisionExtractor` dependencies.
- **Test outcome:** Passing — `python -m pytest tests/test_routes.py -q` (`2 passed`).
- **Immediate next task:** 4.2 — Add request limits, security headers, correlation IDs, rate limiting/authentication boundaries, and top-level exception handling.

### 4.2

- **Implemented:** Added `app/main.py` with the mounted router, permissive development CORS configuration, and `ErrorResponse` JSON handlers returning HTTP 408, 422, and 500.
- **Test outcome:** Passing — `python -m pytest tests/test_main.py -q` (`4 passed`); one existing Starlette deprecation warning remains.
- **Immediate next task:** 4.3 — Add end-to-end integration tests for live-adapter stubs, mock fallback, timeouts, invalid input, and unexpected exceptions.

### 4.3

- **Implemented:** Added `tests/test_api.py`, enforced 403 responses for missing/invalid API keys, and enforced standard container ID validation for 422 malformed-input responses.
- **Test outcome:** Passing — `python -m pytest tests/` (`29 passed`, 1 non-blocking deprecation warning).
- **Immediate next task:** None — MVP complete.

## MVP Status

All planned tasks are complete and the PortalConnect API MVP is complete.

## Final Verification Notes

- Added and verified `GET /v1/terminals` and `GET /healthz` per the expanded system specification.
- Added production `Dockerfile` and `README.md` with local setup, API, mock-mode, and test instructions.
- Final suite: `python -m pytest tests/` — **31 passed**, with one non-blocking Starlette deprecation warning.
- PLAN status: **12 checked, 0 unchecked**.
- Docker CLI is installed, but `docker build` could not run because the Docker Desktop Linux daemon is not running; no code failure was observed.

### 1.2

- **Implemented:** Added `app/models/schemas.py` with strict typed request, response, and error contracts; added focused schema validation tests.
- **Test outcome:** Passing — `python -m pytest tests/test_schemas.py -q` (`6 passed`).
- **Immediate next task:** 1.3 — Continue with the next unchecked plan item.
