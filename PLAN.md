# PortalConnect API — Implementation Plan

All tasks are atomic, testable milestones intended to take under two minutes each. Mark a task complete only after its acceptance check passes.

## Phase 1: Environment, Dependencies & Pydantic Data Models

- [x] **1.1** Create the Python 3.11 project layout and pytest configuration; verify the test runner starts successfully.
- [x] **1.2** Implement strict Pydantic v2 request, response, and error schemas; verify normalization, typing, and invalid-input rejection.
- [x] **1.3** Implement request and response Pydantic v2 models for the lookup contracts; verify valid serialization and invalid-input rejection.

## Phase 2: Stealth Browser Engine with Playwright

- [x] **2.1** Implement an async Playwright browser/context factory with headless defaults and centralized timeout settings; verify it can initialize and close cleanly.
- [x] **2.2** Add typed portal exceptions, explicit 15-second navigation/element timeouts, and exception-safe browser/context cleanup; verify failure-path cleanup.
- [x] **2.3** Add timeout translation and guaranteed page/context/browser cleanup; verify navigation and element timeout paths with focused tests.

## Phase 3: Vision & Structured Parsing Pipeline with Mock Fallbacks

- [x] **3.1** Define the structured extraction input/output boundary for screenshots or portal text; verify parser output maps to the response model.
- [x] **3.2** Implement deterministic mock mode when no API key is supplied; verify it works offline and is visibly marked in internal telemetry.
- [x] **3.3** Add parsing validation, malformed-data handling, and live/mock adapter selection; verify controlled failures and schema-valid fallback results.

## Phase 4: FastAPI Gateway, Security Middleware & Integration Tests

- [x] **4.1** Implement `POST /v1/container/lookup` with dependency-injected application services; verify the exact request and success response contracts.
- [x] **4.2** Add CORS middleware and global structured exception handlers for timeout, CAPTCHA, and unexpected failures; verify controlled responses for all expected failures.
- [x] **4.3** Add end-to-end integration tests for live-adapter stubs, mock fallback, timeouts, invalid input, and unexpected exceptions; verify the complete pytest suite passes with zero unhandled 500 crashes.
