# Antenna

Antenna is a local FastAPI web service that scans configured X/Twitter accounts, extracts YouTube URLs, enriches them with metadata, and provides a browser review queue.

## Run

```powershell
uv run uvicorn antenna.app:create_app --factory --reload
```

Or:

```powershell
uv run python -m antenna
```

Open `http://127.0.0.1:8000`.
