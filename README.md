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

When `OPENAI_API_KEY` is empty or `TEST_MODE=true`, extraction uses deterministic offline mock data. Set `API_KEY` in `.env` and send it as `X-API-Key` for protected lookup requests.

## API

- `GET /healthz` — returns `{ "status": "ok" }`.
- `GET /v1/terminals` — returns the supported terminal registry.
- `POST /v1/container/lookup` — accepts `terminal_code` and `container_id`; requires `X-API-Key`.

## Tests

```powershell
python -m pytest tests/
```

The suite uses mocked browser and OpenAI clients, so it does not require network access, API quotas, or a live portal.
