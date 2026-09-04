# PortalConnect API

PortalConnect API is a headless FastAPI layer for extracting container status from legacy web portals.

## Stack

- Python 3.11+
- FastAPI and Uvicorn
- Async Playwright with headless Chromium
- Pydantic v2 and pydantic-settings
- OpenAI structured vision extraction
- pytest and pytest-asyncio

## Local setup

```powershell
python -m pip install -r requirements.txt
playwright install chromium
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

When `OPENAI_API_KEY` is empty, extraction uses the free DOM-table parser; `TEST_MODE=true` uses deterministic offline fixture data. Set `API_KEY` in `.env` and send it as `X-API-Key` for protected lookup requests.

## API

- `GET /healthz` — returns `{ "status": "ok" }`.
- `GET /v1/terminals` — returns the supported terminal registry.
- `POST /v1/container/lookup` — accepts `terminal_code` and `container_id`; requires `X-API-Key`.

## Tests

```powershell
python -m pytest tests/
```

The suite uses mocked browser and OpenAI clients, so it does not require network access, API quotas, or a live portal.

## Free deployment on Render

This repository includes a `render.yaml` Blueprint for zero-touch deployment on Render's free web-service tier. In the Render dashboard, choose **New → Blueprint**, connect this GitHub repository, and select the `main` branch. Render will detect `render.yaml`, build the Dockerfile, configure the service, and use `/healthz` as its health check.

The Blueprint sets `TEST_MODE=true` and a test API key, so the free deployment runs without OpenAI credentials. For production use, replace `API_KEY` with a secret value and disable test mode in the Render service environment.
