# council-dashboard

- `backend/` — FastAPI service (`mission.api`), worker (`mission.worker`), simulator, Meta agents, environment packages and tests.
- `frontend/` — Next.js static interface, built to `frontend/out` and served by the API.
- `start.bat` / `stop.bat` — Windows launcher. Requires `MODEL_API_KEY` in `backend/.env` and a built `frontend/out`.

See the repository [README](../README.md).
